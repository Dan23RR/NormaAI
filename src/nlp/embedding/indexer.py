"""
Qdrant Hybrid Indexer — Dense + BM25 sparse vectors for EU regulations.

Implements hybrid search with Reciprocal Rank Fusion (RRF):
- Dense vectors: FastEmbed (paraphrase-multilingual-mpnet-base-v2, 768 dim) for semantic similarity
- Sparse vectors: BM25-style term frequency for keyword matching
- RRF fusion: combines both rankings without tuning weights

Why hybrid:
- Dense catches "sustainability reporting obligations" ≈ "CSRD compliance requirements"
- Sparse catches exact terms: "Article 29", "CELEX 32022L2464", "€10M threshold"
- RRF is robust and doesn't require weight calibration
"""

import hashlib
import logging
import math
import os
from collections import Counter
from datetime import UTC, datetime

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    IsEmptyCondition,
    MatchValue,
    NamedSparseVector,
    NamedVector,
    PayloadField,
    PointStruct,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

logger = logging.getLogger(__name__)


def _text_to_sparse_vector(text: str, vocab_size: int = 30000) -> SparseVector:
    """
    Convert text to a BM25-style sparse vector.

    Uses term hashing to avoid maintaining a global vocabulary.
    Each term is hashed to a fixed index in [0, vocab_size).
    Value = TF * IDF approximation (log(1 + tf)).

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
        idx = int(hashlib.md5(word.encode()).hexdigest(), 16) % vocab_size
        tf_score = math.log(1 + count)
        index_values[idx] = index_values.get(idx, 0.0) + tf_score

    # Sort by index for deterministic output
    sorted_items = sorted(index_values.items())
    indices = [item[0] for item in sorted_items]
    values = [item[1] for item in sorted_items]

    return SparseVector(indices=indices, values=values)


class HybridIndexer:
    """
    Manages the Qdrant collection for EU regulatory documents.

    Collection schema:
    - Vector "dense": 768-dim BGE embeddings (semantic)
    - Vector "bm25": sparse term-frequency vectors (keyword)
    - Payload: celex, framework, chunk_type, article_number, section_title, text,
               effective_date, superseded_by, content_hash, indexed_at, org_id
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
    ):
        self.client = QdrantClient(host=qdrant_host, port=qdrant_port)
        self.COLLECTION_NAME = collection_name or self.DEFAULT_COLLECTION_NAME
        self.embedding_model_name = embedding_model
        self.embedding_dim = embedding_dim
        self._embedder = None  # Lazy init

    @property
    def embedder(self):
        """Lazy-load embedding model (avoids import overhead if not needed)."""
        if self._embedder is None:
            from fastembed import TextEmbedding

            # In the read-only production image the model is baked at build time
            # under FASTEMBED_CACHE_DIR; pin the same dir so fastembed loads it
            # offline instead of trying (and failing) to download to a read-only
            # FS. fastembed caches by $HOME otherwise, which differs build (root)
            # vs runtime (normaai). Unset locally -> None -> fastembed default.
            cache_dir = os.getenv("FASTEMBED_CACHE_DIR") or None
            self._embedder = TextEmbedding(
                model_name=self.embedding_model_name, cache_dir=cache_dir
            )
        return self._embedder

    def setup_collection(self, recreate: bool = False) -> None:
        """Create or verify the hybrid collection exists."""
        collections = [c.name for c in self.client.get_collections().collections]

        if self.COLLECTION_NAME in collections:
            if recreate:
                logger.warning("recreating_collection: %s", self.COLLECTION_NAME)
                self.client.delete_collection(self.COLLECTION_NAME)
            else:
                logger.info("collection_exists: %s", self.COLLECTION_NAME)
                return

        self.client.create_collection(
            collection_name=self.COLLECTION_NAME,
            vectors_config={
                "dense": VectorParams(
                    size=self.embedding_dim,
                    distance=Distance.COSINE,
                )
            },
            sparse_vectors_config={"bm25": SparseVectorParams()},
        )

        # Create payload indices for metadata filtering
        self.client.create_payload_index(
            collection_name=self.COLLECTION_NAME,
            field_name="framework",
            field_schema="keyword",
        )
        self.client.create_payload_index(
            collection_name=self.COLLECTION_NAME,
            field_name="celex",
            field_schema="keyword",
        )
        self.client.create_payload_index(
            collection_name=self.COLLECTION_NAME,
            field_name="chunk_type",
            field_schema="keyword",
        )
        self.client.create_payload_index(
            collection_name=self.COLLECTION_NAME,
            field_name="effective_date",
            field_schema="keyword",
        )
        self.client.create_payload_index(
            collection_name=self.COLLECTION_NAME,
            field_name="superseded_by",
            field_schema="keyword",
        )
        self.client.create_payload_index(
            collection_name=self.COLLECTION_NAME,
            field_name="content_hash",
            field_schema="keyword",
        )
        self.client.create_payload_index(
            collection_name=self.COLLECTION_NAME,
            field_name="org_id",
            field_schema="keyword",
        )

        logger.info(f"Created hybrid collection {self.COLLECTION_NAME}")

    def index_chunks(
        self,
        chunks: list,
        batch_size: int = 32,
        org_id: str | None = None,
    ) -> int:
        """
        Index a list of LegalChunk objects into Qdrant.

        Processes embeddings in small batches to avoid OOM errors.
        At 768-dim, batch_size=32 uses ~200MB RAM.

        Args:
            chunks: List of LegalChunk objects
            batch_size: Number of chunks to embed per batch
            org_id: Optional organization ID for multi-tenant isolation

        Returns number of chunks indexed.
        """
        total_indexed = 0
        total_chunks = len(chunks)

        for batch_start in range(0, total_chunks, batch_size):
            batch_end = min(batch_start + batch_size, total_chunks)
            batch_chunks = chunks[batch_start:batch_end]

            # Generate dense embeddings for THIS BATCH ONLY (avoids OOM)
            batch_texts = [c.text for c in batch_chunks]
            batch_dense = list(self.embedder.embed(batch_texts))

            points = []
            for i, (chunk, dense_vec) in enumerate(zip(batch_chunks, batch_dense, strict=False)):
                global_idx = batch_start + i

                # Create unique ID from celex + global chunk index
                point_id = int(
                    hashlib.md5(
                        f"{chunk.metadata.get('celex', '')}_{global_idx}".encode()
                    ).hexdigest()[:16],
                    16,
                )

                # Generate sparse BM25 vector
                sparse_vec = _text_to_sparse_vector(chunk.text)

                # Compute content hash for deduplication
                content_hash = hashlib.sha256(chunk.text.encode()).hexdigest()

                point = PointStruct(
                    id=point_id,
                    vector={
                        "dense": dense_vec.tolist()
                        if hasattr(dense_vec, "tolist")
                        else list(dense_vec),
                        "bm25": sparse_vec,
                    },
                    payload={
                        "text": chunk.text,
                        "celex": chunk.metadata.get("celex", ""),
                        "framework": chunk.metadata.get("framework", ""),
                        "chunk_type": chunk.metadata.get("chunk_type", ""),
                        "article_number": chunk.metadata.get("article_number", ""),
                        "section_title": chunk.metadata.get("section_title", ""),
                        "hierarchy": chunk.metadata.get("hierarchy", ""),
                        "char_count": chunk.metadata.get("char_count", 0),
                        "effective_date": chunk.metadata.get("effective_date", None),
                        "superseded_by": chunk.metadata.get("superseded_by", None),
                        "content_hash": content_hash,
                        "indexed_at": datetime.now(UTC).isoformat(),
                        "org_id": org_id,
                    },
                )
                points.append(point)

            # Upload batch to Qdrant
            self.client.upsert(
                collection_name=self.COLLECTION_NAME,
                points=points,
            )
            total_indexed += len(points)

            # Progress logging
            progress = (batch_end / total_chunks) * 100
            logger.info(
                f"  Indexed batch {batch_start}-{batch_end} "
                f"({total_indexed}/{total_chunks} chunks, {progress:.0f}%)"
            )

        logger.info(f"Indexing complete: {total_indexed} chunks into {self.COLLECTION_NAME}")
        return total_indexed

    def index_contextual_chunks(
        self,
        chunks: list,
        batch_size: int = 32,
        org_id: str | None = None,
    ) -> int:
        """
        Index ContextualChunk objects — embeds contextualized_text, stores original text.

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
        total_indexed = 0
        total_chunks = len(chunks)

        for batch_start in range(0, total_chunks, batch_size):
            batch_end = min(batch_start + batch_size, total_chunks)
            batch_chunks = chunks[batch_start:batch_end]

            # Embed the CONTEXTUALIZED text (with regulatory prefix)
            batch_texts = [getattr(c, "contextualized_text", c.text) for c in batch_chunks]
            batch_dense = list(self.embedder.embed(batch_texts))

            points = []
            for i, (chunk, dense_vec) in enumerate(zip(batch_chunks, batch_dense, strict=False)):
                global_idx = batch_start + i

                point_id = int(
                    hashlib.md5(
                        f"{chunk.metadata.get('celex', '')}_{global_idx}".encode()
                    ).hexdigest()[:16],
                    16,
                )

                # Sparse vector uses ORIGINAL text (exact keyword matching)
                original_text = getattr(chunk, "text", "")
                sparse_vec = _text_to_sparse_vector(original_text)

                # Compute content hash for deduplication
                content_hash = hashlib.sha256(original_text.encode()).hexdigest()

                point = PointStruct(
                    id=point_id,
                    vector={
                        "dense": dense_vec.tolist()
                        if hasattr(dense_vec, "tolist")
                        else list(dense_vec),
                        "bm25": sparse_vec,
                    },
                    payload={
                        "text": original_text,
                        "celex": chunk.metadata.get("celex", ""),
                        "framework": chunk.metadata.get("framework", ""),
                        "chunk_type": chunk.metadata.get("chunk_type", ""),
                        "article_number": chunk.metadata.get("article_number", ""),
                        "section_title": chunk.metadata.get("section_title", ""),
                        "hierarchy": chunk.metadata.get("hierarchy", ""),
                        "char_count": chunk.metadata.get("char_count", len(original_text)),
                        "has_context": chunk.metadata.get("has_context", False),
                        "effective_date": chunk.metadata.get("effective_date", None),
                        "superseded_by": chunk.metadata.get("superseded_by", None),
                        "content_hash": content_hash,
                        "indexed_at": datetime.now(UTC).isoformat(),
                        "org_id": org_id,
                    },
                )
                points.append(point)

            self.client.upsert(
                collection_name=self.COLLECTION_NAME,
                points=points,
            )
            total_indexed += len(points)

            progress = (batch_end / total_chunks) * 100
            logger.info(
                f"  Indexed batch {batch_start}-{batch_end} "
                f"({total_indexed}/{total_chunks} contextual chunks, {progress:.0f}%)"
            )

        logger.info(
            f"Contextual indexing complete: {total_indexed} chunks into {self.COLLECTION_NAME}"
        )
        return total_indexed

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
        fall back to legacy on any incompatibility.
        """
        name = getattr(query_vector, "name", None)
        vector = getattr(query_vector, "vector", query_vector)

        # Try modern API first (qdrant-client >= 1.12)
        if name is not None and hasattr(self.client, "query_points"):
            try:
                response = self.client.query_points(
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
            return self.client.search(
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
    ) -> list[dict]:
        """
        Hybrid search with Reciprocal Rank Fusion.

        Runs dense + sparse search separately, then fuses rankings.
        Compatible with qdrant-client v1.7+ (search) and v1.12+ (query_points).

        Args:
            query: Search query text
            limit: Max number of results to return
            framework_filter: Filter to a specific framework (str) or multiple (list[str])
            chunk_type_filter: Filter to a specific chunk type
            rrf_k: RRF constant (default 60)
            include_superseded: If False (default), exclude chunks superseded by newer regulations
            org_id: If provided, filter to chunks belonging to this org or shared (org_id is null)
        """
        # Generate query vectors
        query_dense = list(self.embedder.embed([query]))[0]
        query_sparse = _text_to_sparse_vector(query)

        # Build filter
        search_filter = self._build_filter(
            framework_filter,
            chunk_type_filter,
            include_superseded=include_superseded,
            org_id=org_id,
            allow_all_orgs=allow_all_orgs,
        )

        dense_vec = query_dense.tolist() if hasattr(query_dense, "tolist") else list(query_dense)

        # Dense search
        dense_results = self._search_compat(
            collection_name=self.COLLECTION_NAME,
            query_vector=NamedVector(name="dense", vector=dense_vec),
            query_filter=search_filter,
            limit=limit * 3,
            with_payload=True,
        )

        # Sparse search
        sparse_results = self._search_compat(
            collection_name=self.COLLECTION_NAME,
            query_vector=NamedSparseVector(name="bm25", vector=query_sparse),
            query_filter=search_filter,
            limit=limit * 3,
            with_payload=True,
        )

        # RRF fusion
        fused = self._reciprocal_rank_fusion(dense_results, sparse_results, k=rrf_k)

        # Get top results with payloads
        results = []
        seen_ids = set()
        all_results_map = {}
        for r in dense_results + sparse_results:
            all_results_map[r.id] = r

        for point_id, rrf_score in fused[:limit]:
            if point_id in seen_ids:
                continue
            seen_ids.add(point_id)

            if point_id in all_results_map:
                r = all_results_map[point_id]
                payload = r.payload if hasattr(r, "payload") else {}
                results.append(
                    {
                        "id": r.id,
                        "score": rrf_score,
                        "text": payload.get("text", ""),
                        "celex": payload.get("celex", ""),
                        "framework": payload.get("framework", ""),
                        "chunk_type": payload.get("chunk_type", ""),
                        "article_number": payload.get("article_number", ""),
                        "section_title": payload.get("section_title", ""),
                    }
                )

        return results

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
    def _build_filter(
        framework: str | list[str] | None = None,
        chunk_type: str | None = None,
        include_superseded: bool = False,
        org_id: str | None = None,
        allow_all_orgs: bool = False,
    ) -> Filter | None:
        """Build Qdrant filter from optional parameters.

        Temporal filtering: by default excludes superseded chunks (where
        superseded_by is not null). Pass include_superseded=True to include them.

        Multi-tenant filtering: if org_id is provided, returns only chunks
        belonging to that org OR shared chunks (org_id is null).

        Framework filtering: accepts a single string or a list of strings.
        A list uses OR logic (match any of the provided frameworks).
        """
        conditions = []
        if framework:
            if isinstance(framework, list) and len(framework) > 1:
                # OR filter: match any of the listed frameworks
                conditions.append(
                    Filter(
                        should=[
                            FieldCondition(key="framework", match=MatchValue(value=fw))
                            for fw in framework
                        ]
                    )
                )
            else:
                fw_val = framework[0] if isinstance(framework, list) else framework
                conditions.append(FieldCondition(key="framework", match=MatchValue(value=fw_val)))
        if chunk_type:
            conditions.append(FieldCondition(key="chunk_type", match=MatchValue(value=chunk_type)))

        # Temporal: exclude superseded chunks by default. is_empty (not is_null)
        # because in-force chunks leave superseded_by unset and Qdrant drops null
        # payload keys — is_null would match nothing and filter out the corpus.
        if not include_superseded:
            conditions.append(IsEmptyCondition(is_empty=PayloadField(key="superseded_by")))

        # Multi-tenant isolation — FAIL-CLOSED (mirrors the DB's RLS posture).
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

    def delete_org_chunks(self, org_id: str) -> None:
        """Delete every chunk owned by an org (GDPR Art. 17 erasure).

        Scoped strictly to the org's own documents — the shared regulatory
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

    def get_collection_stats(self) -> dict:
        """Get collection info for monitoring."""
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
        return stats
