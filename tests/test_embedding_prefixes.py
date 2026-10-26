"""Model-specific input prefixes of the dense embedder (e5: "query: " / "passage: ").

The multilingual e5 models are trained with "query: " in front of search queries
and "passage: " in front of documents. FastEmbed does not add them, so the
indexer does (src.nlp.embedding.indexer.EMBEDDING_PREFIXES). This file pins:

- the prefix table: e5 gets both prefixes, the default mpnet and unknown models none;
- every dense call site applies them - indexing (plain and contextual chunks)
  and hybrid_search - while the payload and the BM25 vectors keep the raw text;
- stored_passage_text rebuilds from a payload exactly the text the indexer
  embedded, which is what scripts/reembed_collection.py embeds with a new model;
- the components that build an indexer from settings (seed pipeline, retrieve
  node fallback) pass the configured collection, model and dimension.

No Qdrant and no model download: QdrantClient is patched and the embedder is a
fake that records the texts it receives.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

import src.pipeline as pipeline_mod
from src.nlp.chunking.contextual_chunker import ContextualChunker
from src.nlp.chunking.legal_chunker import EURLexHTMLChunker
from src.nlp.embedding.indexer import (
    EMBEDDING_PREFIXES,
    HybridIndexer,
    _text_to_sparse_vector,
    embedding_prefixes,
    indexer_kwargs_from_settings,
    stored_passage_text,
)

INDEXER_PATH = "src.nlp.embedding.indexer.QdrantClient"
E5 = "intfloat/multilingual-e5-large"
MPNET = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"


# --------------------------------------------------------------------------- #
#  Test doubles                                                               #
# --------------------------------------------------------------------------- #


class RecordingEmbedder:
    """Stand-in for fastembed.TextEmbedding: one list of texts per embed() call."""

    def __init__(self, dim: int = 4):
        self.dim = dim
        self.calls: list[list[str]] = []

    def embed(self, texts):
        self.calls.append(list(texts))
        for _ in texts:
            yield [0.5] * self.dim


def make_indexer(model: str | None = None, client: MagicMock | None = None) -> HybridIndexer:
    """A HybridIndexer for ``model`` (None = the constructor default) with a fake embedder."""
    kwargs: dict = {"embedding_dim": 4}
    if model is not None:
        kwargs["embedding_model"] = model
    with patch(INDEXER_PATH, return_value=client if client is not None else MagicMock()):
        idx = HybridIndexer(**kwargs)
    idx._embedder = RecordingEmbedder()
    return idx


def make_chunk(text: str, contextualized_text: str | None = None):
    ns = SimpleNamespace(text=text, metadata={"celex": "32022L2464", "framework": "CSRD"})
    if contextualized_text is not None:
        ns.contextualized_text = contextualized_text
    return ns


def upserted_points(client: MagicMock) -> list:
    return [p for call in client.upsert.call_args_list for p in call.kwargs["points"]]


# --------------------------------------------------------------------------- #
#  The prefix table                                                           #
# --------------------------------------------------------------------------- #


class TestPrefixTable:
    @pytest.mark.parametrize(
        "model",
        [E5, "intfloat/multilingual-e5-base", "intfloat/multilingual-e5-small"],
    )
    def test_e5_models_get_query_and_passage_prefixes(self, model):
        assert embedding_prefixes(model) == ("query: ", "passage: ")

    def test_lookup_ignores_case_like_fastembed(self):
        # FastEmbed loads "intfloat/Multilingual-E5-Large" as e5-large: the prefixes
        # must not silently disappear because of the spelling.
        assert embedding_prefixes("intfloat/Multilingual-E5-Large") == ("query: ", "passage: ")

    @pytest.mark.parametrize(
        "model",
        [MPNET, "BAAI/bge-small-en-v1.5", "intfloat/multilingual-e5-large-instruct", "", None],
    )
    def test_other_models_get_no_prefix(self, model):
        assert embedding_prefixes(model) == ("", "")

    def test_table_keys_are_lower_case(self):
        assert all(name == name.lower() for name in EMBEDDING_PREFIXES)

    def test_indexer_takes_the_prefixes_of_its_model(self):
        e5 = make_indexer(E5)
        assert (e5.query_prefix, e5.passage_prefix) == ("query: ", "passage: ")
        default = make_indexer()  # constructor default = mpnet
        assert (default.query_prefix, default.passage_prefix) == ("", "")


# --------------------------------------------------------------------------- #
#  Indexing: every passage is embedded behind the passage prefix              #
# --------------------------------------------------------------------------- #


class TestIndexingPrefixes:
    def test_e5_plain_chunks_are_embedded_as_passages(self):
        client = MagicMock()
        idx = make_indexer(E5, client)

        idx.index_chunks([make_chunk("Article 22 due diligence"), make_chunk("Article 29")])

        assert idx._embedder.calls == [["passage: Article 22 due diligence", "passage: Article 29"]]
        points = upserted_points(client)
        # The prefix is for the dense model only: payload and BM25 keep the raw text.
        assert [p.payload["text"] for p in points] == ["Article 22 due diligence", "Article 29"]
        assert points[0].vector["bm25"] == _text_to_sparse_vector("Article 22 due diligence")
        assert points[0].vector["dense"] == [0.5] * 4

    def test_e5_contextual_chunks_prefix_the_contextualized_text(self):
        client = MagicMock()
        idx = make_indexer(E5, client)
        chunk = make_chunk("Original text", contextualized_text="[CSRD | Art. 5]\nOriginal text")

        idx.index_contextual_chunks([chunk])

        assert idx._embedder.calls == [["passage: [CSRD | Art. 5]\nOriginal text"]]
        point = upserted_points(client)[0]
        assert point.payload["text"] == "Original text"
        assert point.vector["bm25"] == _text_to_sparse_vector("Original text")

    def test_e5_reindex_act_embeds_passages(self):
        # The seed path (reindex_act -> index_contextual_chunks) is covered too.
        idx = make_indexer(E5)
        idx.reindex_act("32022L2464", "EN", [make_chunk("t", contextualized_text="[CSRD]\nt")])
        assert idx._embedder.calls == [["passage: [CSRD]\nt"]]

    def test_e5_prefix_applied_in_every_batch(self):
        idx = make_indexer(E5)
        idx.index_chunks([make_chunk(f"chunk {i}") for i in range(3)], batch_size=2)
        assert idx._embedder.calls == [
            ["passage: chunk 0", "passage: chunk 1"],
            ["passage: chunk 2"],
        ]

    def test_mpnet_passages_are_embedded_unchanged(self):
        idx = make_indexer(MPNET)
        idx.index_chunks([make_chunk("Article 22 due diligence")])
        idx.index_contextual_chunks([make_chunk("t", contextualized_text="[CSRD]\nt")])
        assert idx._embedder.calls == [["Article 22 due diligence"], ["[CSRD]\nt"]]


# --------------------------------------------------------------------------- #
#  Search: the query is embedded behind the query prefix                      #
# --------------------------------------------------------------------------- #


class TestSearchPrefixes:
    def test_e5_query_is_embedded_with_query_prefix(self):
        idx = make_indexer(E5)
        with patch.object(idx, "_search_compat", side_effect=[[], []]) as mock_sc:
            idx.hybrid_search("obblighi di rendicontazione", limit=5)

        assert idx._embedder.calls == [["query: obblighi di rendicontazione"]]
        dense_qv = mock_sc.call_args_list[0].kwargs["query_vector"]
        sparse_qv = mock_sc.call_args_list[1].kwargs["query_vector"]
        assert dense_qv.name == "dense" and dense_qv.vector == [0.5] * 4
        # BM25 searches the raw query: "query:" must not become a search term.
        assert sparse_qv.vector == _text_to_sparse_vector("obblighi di rendicontazione")

    def test_mpnet_query_is_embedded_unchanged(self):
        idx = make_indexer(MPNET)
        with patch.object(idx, "_search_compat", side_effect=[[], []]):
            idx.hybrid_search("sustainability reporting")
        assert idx._embedder.calls == [["sustainability reporting"]]

    def test_default_model_query_is_embedded_unchanged(self):
        idx = make_indexer()
        with patch.object(idx, "_search_compat", side_effect=[[], []]):
            idx.hybrid_search("q")
        assert idx._embedder.calls == [["q"]]

    def test_numpy_vectors_become_plain_lists(self):
        # FastEmbed yields numpy arrays; Qdrant points and queries need lists.
        idx = make_indexer(E5)
        idx._embedder = SimpleNamespace(
            embed=lambda texts: (np.array([0.25, 0.75], dtype=np.float32) for _ in texts)
        )
        assert idx.embed_query("q") == [0.25, 0.75]
        assert idx.embed_passages(["a", "b"]) == [[0.25, 0.75], [0.25, 0.75]]


# --------------------------------------------------------------------------- #
#  stored_passage_text: the text a stored point was embedded from             #
# --------------------------------------------------------------------------- #

SEED_HTML = """<html><body>
<p>CHAPTER II</p><p>REPORTING OBLIGATIONS</p>
<p>Article 19a</p><p>Sustainability reporting</p>
<p>1. Large undertakings shall include in the management report information necessary
to understand the undertaking's impacts on sustainability matters.</p>
<p>2. The information referred to in paragraph 1 shall contain a brief description of
the business model and strategy of the undertaking.</p>
</body></html>"""


def seed_enriched_chunks() -> list:
    """Chunks as the seed builds them: real chunker + IngestionPipeline._enrich."""
    chunks = EURLexHTMLChunker(celex="32013L0034", framework="CSRD", lang="EN").chunk_html(
        SEED_HTML
    )
    pipeline = pipeline_mod.IngestionPipeline.__new__(pipeline_mod.IngestionPipeline)
    pipeline.contextual_chunker = ContextualChunker()
    return pipeline._enrich(chunks)


class TestStoredPassageText:
    def test_rebuilds_exactly_what_the_seed_embedded(self):
        # Drift guard: chunker -> pipeline enrichment -> indexer -> stored payload.
        # If the enrichment starts using another field, this fails and
        # stored_passage_text must follow.
        client = MagicMock()
        idx = make_indexer(E5, client)
        enriched = seed_enriched_chunks()
        assert enriched

        idx.reindex_act("32013L0034", "EN", enriched)

        embedded = [text for call in idx._embedder.calls for text in call]
        payloads = [p.payload for p in upserted_points(client)]
        assert embedded == [idx.passage_prefix + stored_passage_text(p) for p in payloads]
        # The comparison is meaningful: the header (act, article, chapter) is there.
        assert embedded[0].startswith(
            "passage: [Corporate Sustainability Reporting Directive (EU) 2022/2464 | Art. 19a |"
        )
        assert all(p["has_context"] is True for p in payloads)

    def test_plain_points_rebuild_to_their_text(self):
        client = MagicMock()
        idx = make_indexer(MPNET, client)
        idx.index_chunks([make_chunk("Bare text")])

        payload = upserted_points(client)[0].payload
        assert "has_context" not in payload
        assert stored_passage_text(payload) == "Bare text" == idx._embedder.calls[0][0]

    def test_missing_header_fields_give_the_bare_text(self):
        # Qdrant drops null payload keys; enrich_single with no parts returns the text.
        assert stored_passage_text({"text": "t", "has_context": True}) == "t"
        assert stored_passage_text({"has_context": False}) == ""


# --------------------------------------------------------------------------- #
#  Indexers built from settings use the configured collection and model       #
# --------------------------------------------------------------------------- #


def e5_settings(**extra) -> SimpleNamespace:
    return SimpleNamespace(
        qdrant_host="qdrant",
        qdrant_port=6334,
        embedding_model=E5,
        embedding_dimension=1024,
        qdrant_collection="eu_regulations_e5",
        **extra,
    )


class TestIndexerFollowsSettings:
    def test_kwargs_from_settings(self):
        settings = e5_settings()
        assert indexer_kwargs_from_settings(settings) == {
            "qdrant_host": "qdrant",
            "qdrant_port": 6334,
            "embedding_model": E5,
            "embedding_dim": 1024,
            "collection_name": "eu_regulations_e5",
        }
        with patch(INDEXER_PATH) as client_cls:
            idx = HybridIndexer(**indexer_kwargs_from_settings(settings))
        client_cls.assert_called_once_with(host="qdrant", port=6334)
        assert idx.COLLECTION_NAME == "eu_regulations_e5"
        assert (idx.embedding_model_name, idx.embedding_dim) == (E5, 1024)
        assert (idx.query_prefix, idx.passage_prefix) == ("query: ", "passage: ")

    def test_seed_pipeline_uses_the_configured_collection_and_model(self):
        settings = e5_settings(eurlex_sparql_endpoint="http://sparql.test")
        with (
            patch.object(pipeline_mod, "get_settings", return_value=settings),
            patch.object(pipeline_mod, "EurLexClient"),
            patch.object(pipeline_mod, "HybridIndexer") as indexer_cls,
            patch.object(pipeline_mod, "ContextualChunker"),
            patch.object(pipeline_mod, "UnifiedDocumentProcessor"),
        ):
            pipeline_mod.IngestionPipeline()
        indexer_cls.assert_called_once_with(**indexer_kwargs_from_settings(settings))

    def test_retrieve_node_fallback_uses_the_configured_collection_and_model(self):
        from src.agents import nodes

        settings = e5_settings()
        fake_indexer = MagicMock()
        fake_indexer.hybrid_search.return_value = []
        with (
            patch("src.api.app_state.app_state.indexer", None),
            patch("src.config.get_settings", return_value=settings),
            patch("src.nlp.embedding.indexer.HybridIndexer", return_value=fake_indexer) as cls,
        ):
            out = nodes.retrieve_node({"query": "What does the CSRD require?"})

        cls.assert_called_once_with(**indexer_kwargs_from_settings(settings))
        assert out == {"retrieved_chunks": []}
