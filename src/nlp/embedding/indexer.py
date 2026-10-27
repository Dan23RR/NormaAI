"""
Qdrant Hybrid Indexer - Dense + BM25 sparse vectors for EU regulations.

Implements hybrid search with Reciprocal Rank Fusion (RRF):
- Dense vectors: FastEmbed (EMBEDDING_MODEL, default paraphrase-multilingual-mpnet-base-v2,
  768 dim) for semantic similarity; models trained with input prefixes (e5: "query: " /
  "passage: ") get them from EMBEDDING_PREFIXES
- Sparse vectors: hashed term frequencies with Qdrant's IDF modifier (BM25-style)
- RRF fusion: combines both rankings without tuning weights

Why hybrid:
- Dense catches "sustainability reporting obligations" ≈ "CSRD compliance requirements"
- Sparse catches exact terms: "Article 29", "CELEX 32022L2464", "€10M threshold"
- RRF is robust and doesn't require weight calibration

Point ids are deterministic (UUID5 of celex|lang|article|chunk_index|sha1(text))
so re-indexing an act overwrites its chunks instead of duplicating them, and
``reindex_act`` replaces one act (CELEX + language) atomically enough for a
seed: delete its points, then upsert the new ones. A dedicated metadata point
(``CORPUS_META_ID``) records when the corpus was built and from which acts.
"""

import hashlib
import logging
import math
import os
import threading
import uuid
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    IsEmptyCondition,
    MatchValue,
    Modifier,
    NamedSparseVector,
    NamedVector,
    PayloadField,
    PointStruct,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from src.nlp.chunking.contextual_chunker import ContextualChunker

logger = logging.getLogger(__name__)

# One lock for every indexer, so the dense model is built once per process even
# when the first questions arrive together. Two concurrent builds also race on
# the download progress bars: in the live golden run of 2026-10-27 the first
# question failed with "type object 'tqdm' has no attribute '_lock'".
_EMBEDDER_LOCK = threading.Lock()


def _is_timeout(error: BaseException | None) -> bool:
    """True when a request timed out, however the Qdrant client wrapped it."""
    seen: set[int] = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, TimeoutError | httpx.TimeoutException):
            return True
        error = getattr(error, "source", None) or error.__cause__ or error.__context__
    return False


def _once_more_on_timeout(call: Callable[..., Any], **kwargs: Any) -> Any:
    """``call(**kwargs)``, sent a second time when the first request times out.

    In the live golden run of 2026-10-27 one slow answer from a busy Qdrant
    failed a whole question; a single retry absorbs such a blip.
    """
    try:
        return call(**kwargs)
    except Exception as e:
        if not _is_timeout(e):
            raise
        logger.warning("qdrant_timeout_retry: %s", e)
        return call(**kwargs)


# ─── Deterministic ids ───────────────────────────────────────────────
# Fixed namespace so the same (act, language, article, position, text) always
# maps to the same Qdrant point id across machines and re-seeds.
NORMAAI_ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "normaai.org")
CORPUS_META_KEY = "normaai-corpus-meta"
CORPUS_META_ID = str(uuid.uuid5(NORMAAI_ID_NAMESPACE, CORPUS_META_KEY))
CORPUS_META_KIND = "corpus_meta"
# The meta point is never a search hit: it carries a sentinel org_id (so the
# fail-closed tenant filter drops it) AND hybrid_search excludes its kind.
CORPUS_META_ORG = "__corpus_meta__"

# Named vectors of every point (scripts/reembed_collection.py copies them by name).
DENSE_VECTOR = "dense"
SPARSE_VECTOR = "bm25"

# Payload fields with a keyword index (filtering / per-act deletes).
PAYLOAD_INDEX_FIELDS: tuple[str, ...] = (
    "framework",
    "frameworks",
    "celex",
    "lang",
    "chunk_type",
    "effective_date",
    "superseded_by",
    "content_hash",
    "org_id",
)


def point_id_key(
    celex: str,
    lang: str,
    article: str,
    chunk_index: int,
    text: str,
    org_id: str | None = None,
) -> str:
    """The string that is hashed into a point id.

    ``celex|lang|article|chunk_index|sha1(text)[:12]``. Tenant uploads
    (``org_id`` set) get the org prefixed so two tenants uploading the same
    document can never overwrite each other's points.
    """
    digest = hashlib.sha1(text.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
    key = f"{celex}|{lang}|{article}|{chunk_index}|{digest}"
    return f"{org_id}|{key}" if org_id else key


def make_point_id(
    celex: str,
    lang: str,
    article: str,
    chunk_index: int,
    text: str,
    org_id: str | None = None,
) -> str:
    """Deterministic Qdrant point id (UUID5 string) for a chunk."""
    return str(
        uuid.uuid5(
            NORMAAI_ID_NAMESPACE,
            point_id_key(celex, lang, article, chunk_index, text, org_id=org_id),
        )
    )


def _text_to_sparse_vector(text: str, vocab_size: int = 30000) -> SparseVector:
    """
    Convert text to a hashed term-frequency sparse vector.

    Uses term hashing to avoid maintaining a global vocabulary.
    Each term is hashed to a fixed index in [0, vocab_size).
    Value = log(1 + tf). The IDF side of BM25 is NOT computed here: the
    collection's sparse vector config carries ``Modifier.IDF``, so Qdrant
    weights every query term by its corpus-wide inverse document frequency at
    search time (and keeps it current as points are added or removed).

    Hash collisions are handled by summing values at the same index,
    ensuring all indices are unique (required by Qdrant).
    """
    words = text.lower().split()
    if not words:
        return SparseVector(indices=[], values=[])

    word_counts = Counter(words)

    # Aggregate by index to guarantee uniqueness (handles hash collisions)
    index_values: dict[int, float] = {}
    for word, count in word_counts.items():
        idx = int(hashlib.md5(word.encode(), usedforsecurity=False).hexdigest(), 16) % vocab_size
        tf_score = math.log(1 + count)
        index_values[idx] = index_values.get(idx, 0.0) + tf_score

    # Sort by index for deterministic output
    sorted_items = sorted(index_values.items())
    indices = [item[0] for item in sorted_items]
    values = [item[1] for item in sorted_items]

    return SparseVector(indices=indices, values=values)


# ─── What the dense model sees ───────────────────────────────────────
# Some dense models are trained with a marker in front of every input and lose
# accuracy without it: the multilingual e5 models expect "query: " before a
# search query and "passage: " before a document. FastEmbed does not add them
# (in 0.4.2 query_embed / passage_embed just call embed), so the indexer does,
# in embed_query and embed_passages. Keys are lower-case because FastEmbed
# matches model names case-insensitively. A model that is not listed (the
# default paraphrase-multilingual-mpnet-base-v2 included) gets no prefix.
# Editing an entry changes the vectors of that model: re-embed afterwards.
EMBEDDING_PREFIXES: dict[str, tuple[str, str]] = {
    # (query_prefix, passage_prefix). multilingual-e5-large-instruct uses another
    # format ("Instruct: ...\nQuery: " on queries only) and is deliberately absent.
    "intfloat/multilingual-e5-small": ("query: ", "passage: "),
    "intfloat/multilingual-e5-base": ("query: ", "passage: "),
    "intfloat/multilingual-e5-large": ("query: ", "passage: "),
}


def embedding_prefixes(model_name: str) -> tuple[str, str]:
    """``(query_prefix, passage_prefix)`` of a dense model; ``("", "")`` when it needs none."""
    return EMBEDDING_PREFIXES.get(str(model_name or "").lower(), ("", ""))


def passage_text(chunk: Any, contextual: bool) -> str:
    """The text whose dense vector represents a chunk, before the model's passage prefix.

    A contextual chunk is embedded through its ``contextualized_text`` (the
    ContextualChunker "[framework | article | section]" header + the text), a
    plain chunk through its ``text``. The payload and the sparse vector always
    keep the original text.
    """
    text: str = getattr(chunk, "contextualized_text", chunk.text) if contextual else chunk.text
    return text


def stored_passage_text(payload: dict[str, Any]) -> str:
    """Rebuild, from a stored point's payload, the text ``passage_text`` gave for it.

    Only the original text is stored. Every indexing path (seed, update, upload,
    scheduler) builds contextual chunks with ContextualChunker.enrich_single from
    the chunk's framework / article_number / section_title, which the payload
    records, and marks them ``has_context``; any other point was embedded on its
    bare text. Used to re-embed a collection with another model without
    re-downloading the corpus (scripts/reembed_collection.py). The header is
    rebuilt with today's ContextualChunker, as a fresh seed would build it. Like
    passage_text, the result carries no model prefix: embed it with embed_passages.
    """
    text = payload.get("text") or ""
    if not payload.get("has_context"):
        return text
    return (
        ContextualChunker()
        .enrich_single(
            text=text,
            framework=payload.get("framework") or "",
            article=payload.get("article_number") or "",
            section=payload.get("section_title") or "",
        )
        .contextualized_text
    )


def _vector_to_list(vector: Any) -> list[float]:
    """A FastEmbed vector (numpy array) or any sequence of floats, as a plain list."""
    values: list[float] = vector.tolist() if hasattr(vector, "tolist") else list(vector)
    return values


def indexer_kwargs_from_settings(settings: Any) -> dict[str, Any]:
    """``HybridIndexer`` arguments from the application settings.

    Every component that reads or writes the corpus must use the same Qdrant
    server, collection, dense model and dimension, or queries are embedded in
    another vector space than the documents: build it with
    ``HybridIndexer(**indexer_kwargs_from_settings(settings))``.
    """
    return {
        "qdrant_host": settings.qdrant_host,
        "qdrant_port": settings.qdrant_port,
        "embedding_model": settings.embedding_model,
        "embedding_dim": settings.embedding_dimension,
        "collection_name": settings.qdrant_collection,
    }


class HybridIndexer:
    """
    Manages the Qdrant collection for EU regulatory documents.

    Collection schema:
    - Vector "dense": embedding_dim multilingual embeddings, 768 by default (semantic)
    - Vector "bm25": sparse hashed term-frequency vectors, IDF modifier (keyword)
    - Payload: text, celex, source_celex, framework, frameworks, lang, article,
               paragraph, title, eli, url, consolidated_as_of, chunk_index,
               chunk_type, article_number, section_title, hierarchy, char_count,
               effective_date, superseded_by, content_hash, indexed_at, org_id
    - One metadata point (CORPUS_META_ID) with kind="corpus_meta"
    """

    DEFAULT_COLLECTION_NAME = "eu_regulations"

    def __init__(
        self,
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        # Multilingual default (IT+EN corpus/queries); see config.py / ADR-005.
        embedding_model: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
        embedding_dim: int = 768,
        collection_name: str | None = None,
        qdrant_timeout: int | None = None,
    ):
        # qdrant_timeout: seconds per request (None = qdrant-client's default). Long
        # batch jobs on a busy machine need more, e.g. scripts/reembed_collection.py.
        self.client = (
            QdrantClient(host=qdrant_host, port=qdrant_port)
            if qdrant_timeout is None
            else QdrantClient(host=qdrant_host, port=qdrant_port, timeout=qdrant_timeout)
        )
        self.COLLECTION_NAME = collection_name or self.DEFAULT_COLLECTION_NAME
        self.embedding_model_name = embedding_model
        self.embedding_dim = embedding_dim
        # Input markers the dense model was trained with ("" for most models).
        self.query_prefix, self.passage_prefix = embedding_prefixes(embedding_model)
        self._embedder = None  # Lazy init
        # None = not checked yet; set by setup_collection on an existing collection.
        self.sparse_idf_enabled: bool | None = None

    @property
    def embedder(self):
        """Lazy-load embedding model (avoids import overhead if not needed).

        Built under _EMBEDDER_LOCK, so concurrent first calls share one build.
        """
        if self._embedder is None:
            with _EMBEDDER_LOCK:
                if self._embedder is None:
                    from fastembed import TextEmbedding

                    # In the read-only production image the model is baked at build
                    # time under FASTEMBED_CACHE_DIR; pin the same dir so fastembed
                    # loads it offline instead of trying (and failing) to download to
                    # a read-only FS. fastembed caches by $HOME otherwise, which
                    # differs build (root) vs runtime (normaai). Unset locally ->
                    # None -> fastembed default.
                    cache_dir = os.getenv("FASTEMBED_CACHE_DIR") or None
                    self._embedder = TextEmbedding(
                        model_name=self.embedding_model_name, cache_dir=cache_dir
                    )
        return self._embedder

    # ─── Dense embeddings ───────────────────────────────────────
    # The only two places that call the dense model: everything indexed goes
    # through embed_passages, every search through embed_query, so the model's
    # prefixes are applied on both sides or on neither.

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        """Dense vectors for documents, each text embedded behind the passage prefix."""
        vectors = self.embedder.embed([f"{self.passage_prefix}{text}" for text in texts])
        return [_vector_to_list(vector) for vector in vectors]

    def embed_query(self, query: str) -> list[float]:
        """Dense vector for a search query, embedded behind the query prefix."""
        return _vector_to_list(list(self.embedder.embed([f"{self.query_prefix}{query}"]))[0])

    # ─── Collection lifecycle ───────────────────────────────────

    def setup_collection(self, recreate: bool = False) -> None:
        """Create the hybrid collection, or verify an existing one (idempotent).

        A fresh collection gets the sparse vectors with Qdrant's IDF modifier.
        An existing collection is left untouched (unless ``recreate``) and
        inspected: a missing IDF modifier, a dense size that does not match the
        configured embedding dimension, or a corpus built with another
        embedding model each log a clear warning telling the operator to
        re-create and reseed - the collection keeps serving in the meantime.
        """
        collections = [c.name for c in self.client.get_collections().collections]

        if self.COLLECTION_NAME in collections:
            if recreate:
                logger.warning("recreating_collection: %s", self.COLLECTION_NAME)
                self.client.delete_collection(self.COLLECTION_NAME)
            else:
                logger.info("collection_exists: %s", self.COLLECTION_NAME)
                self._verify_existing_collection()
                return

        self.client.create_collection(
            collection_name=self.COLLECTION_NAME,
            vectors_config={
                DENSE_VECTOR: VectorParams(
                    size=self.embedding_dim,
                    distance=Distance.COSINE,
                )
            },
            sparse_vectors_config={SPARSE_VECTOR: SparseVectorParams(modifier=Modifier.IDF)},
        )
        self.sparse_idf_enabled = True

        # Create payload indices for metadata filtering
        for field_name in PAYLOAD_INDEX_FIELDS:
            self.client.create_payload_index(
                collection_name=self.COLLECTION_NAME,
                field_name=field_name,
                field_schema="keyword",
            )

        logger.info(f"Created hybrid collection {self.COLLECTION_NAME} (sparse modifier: idf)")

    def _verify_existing_collection(self) -> None:
        """Compare an existing collection with the configuration; warn on drift."""
        reseed_hint = "re-create and reseed with: python -m src.pipeline --action seed --recreate"
        try:
            info = self.client.get_collection(self.COLLECTION_NAME)
            params = info.config.params
        except Exception as e:
            logger.warning("collection_verification_skipped: %s", e)
            return

        sparse_cfg = getattr(params, "sparse_vectors", None)
        bm25 = sparse_cfg.get(SPARSE_VECTOR) if isinstance(sparse_cfg, dict) else None
        modifier = getattr(bm25, "modifier", None)
        modifier_name = getattr(modifier, "value", modifier)
        self.sparse_idf_enabled = str(modifier_name).lower() == "idf"
        if not self.sparse_idf_enabled:
            logger.warning(
                "collection_sparse_modifier_missing: collection %s was created without the "
                "IDF modifier on the 'bm25' sparse vectors (found: %s). Keyword search works "
                "but is not IDF-weighted; %s",
                self.COLLECTION_NAME,
                modifier_name,
                reseed_hint,
            )

        dense_cfg = getattr(params, "vectors", None)
        dense = dense_cfg.get(DENSE_VECTOR) if isinstance(dense_cfg, dict) else None
        dense_size = getattr(dense, "size", None)
        if isinstance(dense_size, int) and dense_size != self.embedding_dim:
            logger.warning(
                "collection_dense_size_mismatch: collection %s has %d-dim dense vectors but "
                "EMBEDDING_DIMENSION=%d; %s",
                self.COLLECTION_NAME,
                dense_size,
                self.embedding_dim,
                reseed_hint,
            )

        meta = self.get_corpus_info()
        built_with = meta.get("embedding_model") if meta else None
        if built_with and built_with != self.embedding_model_name:
            logger.warning(
                "collection_embedding_model_mismatch: corpus was built with %s but "
                "EMBEDDING_MODEL=%s; vectors live in a model-specific space - %s",
                built_with,
                self.embedding_model_name,
                reseed_hint,
            )

    # ─── Indexing ───────────────────────────────────────────────

    def _build_point(
        self,
        chunk,
        dense_vec,
        fallback_index: int,
        org_id: str | None,
        contextual: bool,
    ) -> PointStruct:
        """Build the Qdrant point for a chunk (deterministic id + full payload)."""
        meta = getattr(chunk, "metadata", None) or {}
        text = getattr(chunk, "text", "") or ""
        celex = meta.get("celex", "") or ""
        lang = meta.get("lang") or "EN"
        article = meta.get("article") or meta.get("article_number") or ""
        chunk_index = meta.get("chunk_index")
        if not isinstance(chunk_index, int):
            chunk_index = fallback_index
        framework = meta.get("framework", "") or ""
        frameworks = meta.get("frameworks")
        if not frameworks:
            frameworks = [framework] if framework else []

        payload = {
            "text": text,
            "celex": celex,
            "source_celex": meta.get("source_celex") or celex,
            "framework": framework,
            "frameworks": list(frameworks),
            "lang": lang,
            "article": article,
            "paragraph": meta.get("paragraph"),
            "title": meta.get("title"),
            "eli": meta.get("eli"),
            "url": meta.get("url"),
            "consolidated_as_of": meta.get("consolidated_as_of"),
            "chunk_index": chunk_index,
            "chunk_type": meta.get("chunk_type", ""),
            "article_number": meta.get("article_number", "") or article,
            "section_title": meta.get("section_title", ""),
            "hierarchy": meta.get("hierarchy", ""),
            "part": meta.get("part"),
            "act_title": meta.get("act_title"),
            # Amending acts: the amended act's article quoted at the start of the
            # chunk, and that act (src/nlp/chunking/legal_chunker.py).
            "quoted_article": meta.get("quoted_article"),
            "amended_celex": meta.get("amended_celex"),
            "source": meta.get("source"),
            "char_count": meta.get("char_count", len(text)),
            "effective_date": meta.get("effective_date", None),
            "superseded_by": meta.get("superseded_by", None),
            "content_hash": hashlib.sha256(text.encode()).hexdigest(),
            "indexed_at": datetime.now(UTC).isoformat(),
            "org_id": org_id,
        }
        if contextual:
            payload["has_context"] = meta.get("has_context", False)

        return PointStruct(
            id=make_point_id(celex, lang, article, chunk_index, text, org_id=org_id),
            vector={
                DENSE_VECTOR: _vector_to_list(dense_vec),
                SPARSE_VECTOR: _text_to_sparse_vector(text),  # sparse always on the ORIGINAL text
            },
            payload=payload,
        )

    def _index(
        self,
        chunks: list,
        batch_size: int,
        org_id: str | None,
        contextual: bool,
    ) -> int:
        total_indexed = 0
        total_chunks = len(chunks)
        label = "contextual chunks" if contextual else "chunks"

        for batch_start in range(0, total_chunks, batch_size):
            batch_end = min(batch_start + batch_size, total_chunks)
            batch_chunks = chunks[batch_start:batch_end]

            # Dense embeddings for THIS BATCH ONLY (avoids OOM). Contextual
            # chunks embed the text behind its context header; the payload
            # keeps the original.
            batch_texts = [passage_text(c, contextual) for c in batch_chunks]
            batch_dense = self.embed_passages(batch_texts)

            points = [
                self._build_point(chunk, dense_vec, batch_start + i, org_id, contextual)
                for i, (chunk, dense_vec) in enumerate(zip(batch_chunks, batch_dense, strict=False))
            ]

            self.client.upsert(
                collection_name=self.COLLECTION_NAME,
                points=points,
            )
            total_indexed += len(points)

            progress = (batch_end / total_chunks) * 100
            logger.info(
                f"  Indexed batch {batch_start}-{batch_end} "
                f"({total_indexed}/{total_chunks} {label}, {progress:.0f}%)"
            )

        logger.info(f"Indexing complete: {total_indexed} {label} into {self.COLLECTION_NAME}")
        return total_indexed

    def index_chunks(
        self,
        chunks: list,
        batch_size: int = 32,
        org_id: str | None = None,
    ) -> int:
        """
        Index a list of LegalChunk objects into Qdrant.

        Processes embeddings in small batches to avoid OOM errors.
        At 768-dim, batch_size=32 uses ~200MB RAM. Point ids are deterministic,
        so indexing the same chunks twice overwrites instead of duplicating.

        Args:
            chunks: List of LegalChunk objects
            batch_size: Number of chunks to embed per batch
            org_id: Optional organization ID for multi-tenant isolation

        Returns number of chunks indexed.
        """
        return self._index(chunks, batch_size, org_id, contextual=False)

    def index_contextual_chunks(
        self,
        chunks: list,
        batch_size: int = 32,
        org_id: str | None = None,
    ) -> int:
        """
        Index ContextualChunk objects - embeds contextualized_text, stores original text.

        This is the recommended method for enterprise use. The contextual prefix
        improves retrieval accuracy by ~10-15% while preserving the original text
        for display to users.

        Args:
            chunks: List of ContextualChunk objects (with .text and .contextualized_text)
            batch_size: Number of chunks to embed per batch (default 32, ~200MB RAM)
            org_id: Optional organization ID for multi-tenant isolation

        Returns:
            Number of chunks indexed
        """
        return self._index(chunks, batch_size, org_id, contextual=True)

    def delete_act_points(self, celex: str, lang: str | None = None) -> None:
        """Delete every shared-corpus point of an act (optionally one language).

        ``celex`` is the act's CELEX as stored in the payload (the original id,
        not the consolidated one), so re-seeding a newer consolidated text
        removes the previous version too. A falsy celex is a no-op - a bug can
        never wipe the collection. The metadata point is untouched.
        """
        if not celex:
            return
        must = [FieldCondition(key="celex", match=MatchValue(value=celex))]
        if lang:
            must.append(FieldCondition(key="lang", match=MatchValue(value=lang)))
        self.client.delete(
            collection_name=self.COLLECTION_NAME,
            points_selector=Filter(must=must),
        )
        logger.info(f"Deleted existing points for {celex} [{lang or 'all languages'}]")

    def reindex_act(
        self,
        celex: str,
        lang: str,
        chunks: list,
        batch_size: int = 32,
        org_id: str | None = None,
    ) -> int:
        """Replace the indexed chunks of one act + language with ``chunks``.

        Delete-then-upsert: stale chunks of a previous text version disappear,
        unchanged chunks keep their deterministic id. With no chunks nothing is
        deleted (an empty download must not erase a good index) and 0 is
        returned.
        """
        if not chunks:
            logger.warning(f"reindex_act: no chunks for {celex} [{lang}] - index left untouched")
            return 0
        self.delete_act_points(celex, lang)
        return self.index_contextual_chunks(chunks, batch_size=batch_size, org_id=org_id)

    # ─── Corpus metadata ────────────────────────────────────────

    def write_corpus_meta(
        self,
        acts: list[dict],
        corpus_as_of: str | None = None,
        embedding_model: str | None = None,
        extra: dict | None = None,
    ) -> dict:
        """Upsert the corpus metadata point and return its payload.

        ``acts`` is the list of indexed acts (dicts with celex, lang, chunks,
        source_celex, consolidated_as_of, ...). ``corpus_as_of`` defaults to
        today's UTC date: the law as published on EUR-Lex on the seed day.
        """
        now = datetime.now(UTC)
        payload = {
            "kind": CORPUS_META_KIND,
            "corpus_as_of": corpus_as_of or now.date().isoformat(),
            "acts": acts,
            "embedding_model": embedding_model or self.embedding_model_name,
            "built_at": now.isoformat(),
            "org_id": CORPUS_META_ORG,
        }
        if extra:
            payload.update(extra)
        # A placeholder unit vector: the point exists for its payload only and
        # is excluded from every search (sentinel org_id + kind filter).
        dense = [1.0] + [0.0] * (self.embedding_dim - 1)
        self.client.upsert(
            collection_name=self.COLLECTION_NAME,
            points=[
                PointStruct(
                    id=CORPUS_META_ID,
                    vector={
                        DENSE_VECTOR: dense,
                        SPARSE_VECTOR: SparseVector(indices=[], values=[]),
                    },
                    payload=payload,
                )
            ],
        )
        logger.info(
            f"Corpus metadata written: as_of={payload['corpus_as_of']} "
            f"acts={len(acts)} model={payload['embedding_model']}"
        )
        return payload

    def get_corpus_info(self) -> dict | None:
        """Payload of the corpus metadata point, or None when it is missing.

        Never raises: an unreachable Qdrant or a collection seeded before the
        metadata point existed both yield None, so callers can treat "unknown"
        uniformly.
        """
        try:
            records = self.client.retrieve(
                collection_name=self.COLLECTION_NAME,
                ids=[CORPUS_META_ID],
                with_payload=True,
                with_vectors=False,
            )
        except Exception as e:
            logger.warning("corpus_meta_read_failed: %s", e)
            return None
        if not isinstance(records, list) or not records:
            return None
        payload = getattr(records[0], "payload", None)
        if not isinstance(payload, dict) or payload.get("kind") != CORPUS_META_KIND:
            return None
        return dict(payload)

    # ─── Search ─────────────────────────────────────────────────

    def _search_compat(
        self, collection_name: str, query_vector, query_filter, limit: int, with_payload: bool
    ):
        """
        Compatibility wrapper across qdrant-client versions.

        query_vector is a NamedVector / NamedSparseVector. The modern API
        (qdrant-client >= 1.12) wants query_points(query=<vector>, using=<name>):
        passing the Named* object straight to `query` raises
        ValueError("Unsupported query type"). The legacy .search() still accepts
        the Named* form. We extract (name, vector), try the modern API first, and
        fall back to legacy on any incompatibility. A request that times out is
        sent once more (_once_more_on_timeout).
        """
        name = getattr(query_vector, "name", None)
        vector = getattr(query_vector, "vector", query_vector)

        # Try modern API first (qdrant-client >= 1.12)
        if name is not None and hasattr(self.client, "query_points"):
            try:
                response = _once_more_on_timeout(
                    self.client.query_points,
                    collection_name=collection_name,
                    query=vector,
                    using=name,
                    query_filter=query_filter,
                    limit=limit,
                    with_payload=with_payload,
                )
                # query_points returns a QueryResponse with .points attribute
                return response.points if hasattr(response, "points") else response
            except (TypeError, AttributeError, ImportError, ValueError):
                pass

        # Fallback to legacy .search() API
        if hasattr(self.client, "search"):
            return _once_more_on_timeout(
                self.client.search,
                collection_name=collection_name,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=limit,
                with_payload=with_payload,
            )

        raise RuntimeError(
            "qdrant-client has neither .query_points() nor .search(). "
            "Install qdrant-client >= 1.7: pip install --upgrade qdrant-client"
        )

    def hybrid_search(
        self,
        query: str,
        limit: int = 10,
        framework_filter: str | list[str] | None = None,
        chunk_type_filter: str | None = None,
        rrf_k: int = 60,
        include_superseded: bool = False,
        org_id: str | None = None,
        allow_all_orgs: bool = False,
        lang_filter: str | list[str] | None = None,
        depth: int | None = None,
    ) -> list[dict]:
        """
        Hybrid search with Reciprocal Rank Fusion.

        Runs dense + sparse search separately, then fuses rankings.
        Compatible with qdrant-client v1.7+ (search) and v1.12+ (query_points).

        Args:
            query: Search query text
            limit: Max number of results to return
            depth: How many dense and how many sparse results enter the fusion
                (default 3 x limit). The fused order depends on it: a deeper
                fusion favours chunks both retrievers find over a chunk only one
                of them ranks high. With a fixed depth, a larger limit returns
                more of the same ranking (the reranker's candidates).
            framework_filter: Filter to a specific framework (str) or multiple (list[str])
            chunk_type_filter: Filter to a specific chunk type
            rrf_k: RRF constant (default 60)
            include_superseded: If False (default), exclude chunks superseded by newer regulations
            org_id: If provided, filter to chunks belonging to this org or shared (org_id is null)
            lang_filter: Restrict to one language ("IT") or several; None = all languages
        """
        # Generate query vectors (the model prefix is for the dense side only:
        # BM25 sees the raw query, as the documents' sparse vectors use raw text)
        dense_vec = self.embed_query(query)
        query_sparse = _text_to_sparse_vector(query)

        # Build filter (the corpus metadata point is never a hit)
        search_filter = self._with_meta_exclusion(
            self._build_filter(
                framework_filter,
                chunk_type_filter,
                include_superseded=include_superseded,
                org_id=org_id,
                allow_all_orgs=allow_all_orgs,
                lang=lang_filter,
            )
        )

        depth = max(depth or limit * 3, limit)

        # Dense search
        dense_results = self._search_compat(
            collection_name=self.COLLECTION_NAME,
            query_vector=NamedVector(name=DENSE_VECTOR, vector=dense_vec),
            query_filter=search_filter,
            limit=depth,
            with_payload=True,
        )

        # Sparse search
        sparse_results = self._search_compat(
            collection_name=self.COLLECTION_NAME,
            query_vector=NamedSparseVector(name=SPARSE_VECTOR, vector=query_sparse),
            query_filter=search_filter,
            limit=depth,
            with_payload=True,
        )

        # RRF fusion
        fused = self._reciprocal_rank_fusion(dense_results, sparse_results, k=rrf_k)

        # Get top results with payloads. Keep each retriever's RAW score so a
        # downstream consumer can gate on retrieval strength (e.g. abstain harder
        # when the best evidence is weak) - the RRF score alone hides that.
        results = []
        seen_ids = set()
        all_results_map = {}
        dense_score_map = {}
        sparse_score_map = {}
        for r in dense_results:
            all_results_map[r.id] = r
            dense_score_map[r.id] = getattr(r, "score", None)
        for r in sparse_results:
            all_results_map[r.id] = r
            sparse_score_map[r.id] = getattr(r, "score", None)

        for point_id, rrf_score in fused[:limit]:
            if point_id in seen_ids:
                continue
            seen_ids.add(point_id)

            if point_id in all_results_map:
                results.append(
                    self._result_dict(
                        all_results_map[point_id],
                        rrf_score,
                        dense_score_map.get(point_id),
                        sparse_score_map.get(point_id),
                    )
                )

        return results

    @staticmethod
    def _result_dict(
        point: Any,
        score: float | None,
        dense_score: float | None = None,
        sparse_score: float | None = None,
    ) -> dict:
        """A search result as the agents read it, from a Qdrant point."""
        payload = getattr(point, "payload", None) or {}
        return {
            "id": point.id,
            "score": score,
            "text": payload.get("text", ""),
            "celex": payload.get("celex", ""),
            "framework": payload.get("framework", ""),
            "chunk_type": payload.get("chunk_type", ""),
            "article_number": payload.get("article_number", ""),
            "section_title": payload.get("section_title", ""),
            # Additive provenance fields (None when a point predates them).
            "lang": payload.get("lang"),
            "article": payload.get("article") or payload.get("article_number", ""),
            "paragraph": payload.get("paragraph"),
            "title": payload.get("title"),
            "eli": payload.get("eli"),
            "url": payload.get("url"),
            "consolidated_as_of": payload.get("consolidated_as_of"),
            # Additive provenance for the citation verifier and the
            # prompt labels (src.agents.citation_verifier, llm).
            "source_celex": payload.get("source_celex"),
            "act_title": payload.get("act_title"),
            "frameworks": payload.get("frameworks"),
            "chunk_index": payload.get("chunk_index"),
            "part": payload.get("part"),  # "2" for the second part of a split unit
            "quoted_article": payload.get("quoted_article"),
            "amended_celex": payload.get("amended_celex"),
            # Additive: raw per-retriever cosine/BM25 score.
            # None = the chunk was not returned by that retriever.
            "dense_score": dense_score,
            "sparse_score": sparse_score,
        }

    def article_chunks(
        self, celex: str, article: str, lang: str | None = None, limit: int = 50
    ) -> list[dict]:
        """The shared, in-force chunks of one article of an act, in document order.

        No search: a filter on ``celex`` and ``article`` (and ``lang``). Used to
        find, in the consolidated text of an amended act, the article an amending
        act quotes (src/agents/quoted_articles.py). The results have the shape
        of hybrid_search's, with no score.
        """
        if not celex or not article:
            return []
        base = self._with_meta_exclusion(self._build_filter(lang=lang))  # shared corpus only
        must = list(base.must or []) + [
            FieldCondition(key="celex", match=MatchValue(value=celex)),
            FieldCondition(key="article", match=MatchValue(value=article)),
        ]
        records, _ = self.client.scroll(
            collection_name=self.COLLECTION_NAME,
            scroll_filter=Filter(must=must, must_not=base.must_not),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        records = sorted(records, key=lambda r: (r.payload or {}).get("chunk_index") or 0)
        return [self._result_dict(r, None) for r in records]

    @staticmethod
    def _reciprocal_rank_fusion(
        dense_results: list,
        sparse_results: list,
        k: int = 60,
    ) -> list[tuple]:
        """
        Combine dense and sparse rankings using RRF.
        Formula: RRF(d) = sum(1 / (k + rank_i(d))) for each ranking i
        """
        rrf_scores: dict = {}

        for rank, result in enumerate(dense_results, 1):
            rrf_scores[result.id] = rrf_scores.get(result.id, 0) + 1.0 / (k + rank)

        for rank, result in enumerate(sparse_results, 1):
            rrf_scores[result.id] = rrf_scores.get(result.id, 0) + 1.0 / (k + rank)

        return sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

    @staticmethod
    def _framework_condition(framework: str) -> Filter:
        """Match a framework on the primary ``framework`` key OR the ``frameworks`` list.

        An act listed under several frameworks (Omnibus I amends CSRD and
        CSDDD) is indexed once with ``framework`` = primary and ``frameworks`` =
        all of them; points indexed before ``frameworks`` existed still match
        via ``framework``.
        """
        return Filter(
            should=[
                FieldCondition(key="framework", match=MatchValue(value=framework)),
                FieldCondition(key="frameworks", match=MatchValue(value=framework)),
            ]
        )

    @staticmethod
    def _with_meta_exclusion(flt: Filter | None) -> Filter:
        """Add a must_not on the corpus metadata point to a (possibly None) filter."""
        exclusion = FieldCondition(key="kind", match=MatchValue(value=CORPUS_META_KIND))
        if flt is None:
            return Filter(must_not=[exclusion])
        return Filter(
            must=flt.must,
            should=flt.should,
            min_should=getattr(flt, "min_should", None),
            must_not=list(flt.must_not or []) + [exclusion],
        )

    @staticmethod
    def _build_filter(
        framework: str | list[str] | None = None,
        chunk_type: str | None = None,
        include_superseded: bool = False,
        org_id: str | None = None,
        allow_all_orgs: bool = False,
        lang: str | list[str] | None = None,
    ) -> Filter | None:
        """Build Qdrant filter from optional parameters.

        Temporal filtering: by default excludes superseded chunks (where
        superseded_by is not null). Pass include_superseded=True to include them.

        Multi-tenant filtering: if org_id is provided, returns only chunks
        belonging to that org OR shared chunks (org_id is null).

        Framework filtering: accepts a single string or a list of strings.
        A list uses OR logic (match any of the provided frameworks).

        Language filtering: a single code or a list (OR); None = every language.
        """
        conditions = []
        if framework:
            frameworks = framework if isinstance(framework, list) else [framework]
            if len(frameworks) > 1:
                # OR filter: match any of the listed frameworks
                conditions.append(
                    Filter(should=[HybridIndexer._framework_condition(fw) for fw in frameworks])
                )
            else:
                conditions.append(HybridIndexer._framework_condition(frameworks[0]))
        if chunk_type:
            conditions.append(FieldCondition(key="chunk_type", match=MatchValue(value=chunk_type)))
        if lang:
            langs = lang if isinstance(lang, list) else [lang]
            lang_conditions = [
                FieldCondition(key="lang", match=MatchValue(value=code.upper())) for code in langs
            ]
            if len(lang_conditions) > 1:
                conditions.append(Filter(should=lang_conditions))
            else:
                conditions.append(lang_conditions[0])

        # Temporal: exclude superseded chunks by default. is_empty (not is_null)
        # because in-force chunks leave superseded_by unset and Qdrant drops null
        # payload keys - is_null would match nothing and filter out the corpus.
        if not include_superseded:
            conditions.append(IsEmptyCondition(is_empty=PayloadField(key="superseded_by")))

        # Multi-tenant isolation - FAIL-CLOSED (mirrors the DB's RLS posture).
        # - org_id given      -> that org's private chunks + shared (org_id null)
        # - org_id None        -> shared-only (NEVER another tenant's private docs)
        # - allow_all_orgs     -> escape hatch for admin/seed/reindex paths ONLY
        # A forgotten org_id on a serving path must not leak cross-tenant data.
        if org_id is not None:
            conditions.append(
                Filter(
                    should=[
                        FieldCondition(key="org_id", match=MatchValue(value=org_id)),
                        IsEmptyCondition(is_empty=PayloadField(key="org_id")),
                    ]
                )
            )
        elif not allow_all_orgs:
            conditions.append(IsEmptyCondition(is_empty=PayloadField(key="org_id")))

        if conditions:
            return Filter(must=conditions)
        return None

    # ─── Maintenance ────────────────────────────────────────────

    def delete_org_chunks(self, org_id: str) -> None:
        """Delete every chunk owned by an org (GDPR Art. 17 erasure).

        Scoped strictly to the org's own documents - the shared regulatory
        corpus (org_id null) is never touched. A falsy org_id is a no-op so a
        bug can never wipe the shared corpus.
        """
        if not org_id:
            return
        self.client.delete(
            collection_name=self.COLLECTION_NAME,
            points_selector=Filter(
                must=[FieldCondition(key="org_id", match=MatchValue(value=org_id))]
            ),
        )

    def mark_superseded(self, celex: str, superseded_by: str) -> int:
        """Set ``superseded_by`` on every indexed chunk of a CELEX.

        This is the write side of temporal freshness: at seed time superseded_by
        is left unset for in-force regulations (so _build_filter's IsEmpty check
        keeps them), and this method flips it once a regulation is no longer in
        force - so the default retrieval filter stops serving repealed law as
        current. ``superseded_by`` is the successor CELEX when known, else a
        marker like ``"not_in_force"``.

        Both args must be truthy (a blank celex would match the whole corpus and
        a blank marker would not register as superseded under the IsEmpty filter)
        - either is a no-op. Returns the number of chunks updated.
        """
        if not celex or not superseded_by:
            return 0
        flt = Filter(must=[FieldCondition(key="celex", match=MatchValue(value=celex))])
        count = self.client.count(
            collection_name=self.COLLECTION_NAME, count_filter=flt, exact=True
        ).count
        if count:
            self.client.set_payload(
                collection_name=self.COLLECTION_NAME,
                payload={"superseded_by": superseded_by},
                points=flt,
            )
        return count

    def get_collection_stats(self) -> dict:
        """Get collection info for monitoring.

        ``points_count`` includes the corpus metadata point once a seed has
        written it (one point). ``sparse_idf`` reports whether the sparse
        vectors carry the IDF modifier (None = not verified yet).
        """
        info = self.client.get_collection(self.COLLECTION_NAME)
        stats = {
            "points_count": info.points_count,
            "status": info.status.value if hasattr(info.status, "value") else str(info.status),
        }
        # vectors_count removed in newer qdrant-client versions
        if hasattr(info, "vectors_count") and info.vectors_count is not None:
            stats["vectors_count"] = info.vectors_count
        # indexed_vectors_count available in newer versions
        if hasattr(info, "indexed_vectors_count") and info.indexed_vectors_count is not None:
            stats["indexed_vectors_count"] = info.indexed_vectors_count
        if self.sparse_idf_enabled is not None:
            stats["sparse_idf"] = self.sparse_idf_enabled
        return stats
