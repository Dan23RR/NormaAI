"""Unit tests for the Qdrant HybridIndexer collection lifecycle and search plumbing.

Complements tests/test_hybrid_search.py (which covers sparse-vector generation,
RRF and basic filter shape). This file targets the parts NOT exercised there:

- HybridIndexer.__init__ / lazy embedder property
- setup_collection (recreate True/False branches, collection-exists short-circuit,
  payload-index creation)
- index_chunks / index_contextual_chunks (point building, upsert calls,
  empty-input -> 0, contextualized_text vs original text)
- _search_compat (modern query_points path with NamedVector `using=`,
  legacy .search fallback, and the no-API RuntimeError)
- the IsEmptyCondition (NOT IsNullCondition) null-filter logic for
  superseded_by and org_id (the e6346c0 commit fix: missing-or-null keys)
- delete_org_chunks (falsy org_id no-op guard) and get_collection_stats

Every external dependency is mocked. No real Qdrant, no fastembed model download,
no network. The QdrantClient is patched where it is imported
(src.nlp.embedding.indexer.QdrantClient) so the constructor never opens a socket,
and the embedder is injected directly via the private _embedder slot to bypass the
lazy fastembed import.
"""

import hashlib
import logging
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from qdrant_client.models import (
    FieldCondition,
    Filter,
    IsEmptyCondition,
    Modifier,
    NamedSparseVector,
    NamedVector,
    PointStruct,
)

from src.nlp.embedding.indexer import (
    CORPUS_META_ID,
    CORPUS_META_KIND,
    CORPUS_META_ORG,
    NORMAAI_ID_NAMESPACE,
    PAYLOAD_INDEX_FIELDS,
    HybridIndexer,
    _text_to_sparse_vector,
    make_point_id,
    point_id_key,
)

INDEXER_PATH = "src.nlp.embedding.indexer.QdrantClient"


# --------------------------------------------------------------------------- #
#  Test doubles                                                               #
# --------------------------------------------------------------------------- #


class FakeEmbedder:
    """Stand-in for fastembed.TextEmbedding.

    embed(texts) yields one 4-dim list per input text, mimicking the generator
    fastembed returns. Each vector has a `.tolist()` is intentionally absent so
    we also exercise the `list(dense_vec)` branch in the point builder.
    """

    def __init__(self, dim: int = 4):
        self.dim = dim
        self.embed_calls = []

    def embed(self, texts):
        self.embed_calls.append(list(texts))
        for _ in texts:
            yield [0.0] * self.dim


def make_indexer(client: MagicMock, embedder=None, collection_name: str | None = None):
    """Build a HybridIndexer with QdrantClient patched out and a fake embedder."""
    with patch(INDEXER_PATH, return_value=client):
        idx = HybridIndexer(collection_name=collection_name)
    idx._embedder = embedder if embedder is not None else FakeEmbedder()
    return idx


def make_chunk(text="some text", metadata=None, contextualized_text=None):
    """Build a minimal chunk object compatible with index_* methods."""
    meta = {"celex": "32022L2464", "framework": "CSRD"}
    if metadata:
        meta.update(metadata)
    ns = SimpleNamespace(text=text, metadata=meta)
    if contextualized_text is not None:
        ns.contextualized_text = contextualized_text
    return ns


# --------------------------------------------------------------------------- #
#  __init__ / embedder                                                        #
# --------------------------------------------------------------------------- #


class TestConstruction:
    def test_constructor_does_not_open_socket(self):
        """QdrantClient is constructed with host/port; we patch it out."""
        client = MagicMock()
        with patch(INDEXER_PATH, return_value=client) as mock_client_cls:
            idx = HybridIndexer(qdrant_host="example", qdrant_port=1234)
        mock_client_cls.assert_called_once_with(host="example", port=1234)
        assert idx.client is client

    def test_default_collection_name(self):
        idx = make_indexer(MagicMock())
        assert idx.COLLECTION_NAME == HybridIndexer.DEFAULT_COLLECTION_NAME == "eu_regulations"

    def test_custom_collection_name_overrides_default(self):
        idx = make_indexer(MagicMock(), collection_name="custom_coll")
        assert idx.COLLECTION_NAME == "custom_coll"

    def test_embedder_lazy_loads_fastembed_only_once(self):
        """The embedder property imports fastembed lazily and caches the result."""
        client = MagicMock()
        with patch(INDEXER_PATH, return_value=client):
            idx = HybridIndexer()
        assert idx._embedder is None  # not built at construction time

        fake_te_instance = object()
        fake_te_cls = MagicMock(return_value=fake_te_instance)
        fake_module = SimpleNamespace(TextEmbedding=fake_te_cls)
        with patch.dict("sys.modules", {"fastembed": fake_module}):
            first = idx.embedder
            second = idx.embedder
        assert first is fake_te_instance
        assert second is fake_te_instance
        # Lazy import constructs the model exactly once (cached in _embedder).
        fake_te_cls.assert_called_once()


# --------------------------------------------------------------------------- #
#  setup_collection                                                           #
# --------------------------------------------------------------------------- #


def _collections_response(names):
    return SimpleNamespace(collections=[SimpleNamespace(name=n) for n in names])


class TestSetupCollection:
    def test_creates_collection_when_absent(self):
        client = MagicMock()
        client.get_collections.return_value = _collections_response([])
        idx = make_indexer(client)

        idx.setup_collection(recreate=False)

        client.create_collection.assert_called_once()
        kwargs = client.create_collection.call_args.kwargs
        assert kwargs["collection_name"] == "eu_regulations"
        assert "dense" in kwargs["vectors_config"]
        assert "bm25" in kwargs["sparse_vectors_config"]
        # One keyword payload index per filterable field (framework, frameworks,
        # celex, lang, chunk_type, effective_date, superseded_by, content_hash, org_id).
        assert client.create_payload_index.call_count == len(PAYLOAD_INDEX_FIELDS)
        indexed_fields = {
            c.kwargs["field_name"] for c in client.create_payload_index.call_args_list
        }
        assert {"superseded_by", "org_id", "celex", "lang"} <= indexed_fields
        client.delete_collection.assert_not_called()

    def test_existing_collection_without_recreate_short_circuits(self):
        client = MagicMock()
        client.get_collections.return_value = _collections_response(["eu_regulations"])
        idx = make_indexer(client)

        idx.setup_collection(recreate=False)

        # Already exists + recreate False -> early return, nothing created/deleted.
        client.delete_collection.assert_not_called()
        client.create_collection.assert_not_called()
        client.create_payload_index.assert_not_called()

    def test_existing_collection_with_recreate_deletes_then_creates(self):
        client = MagicMock()
        client.get_collections.return_value = _collections_response(["eu_regulations"])
        idx = make_indexer(client)

        idx.setup_collection(recreate=True)

        client.delete_collection.assert_called_once_with("eu_regulations")
        client.create_collection.assert_called_once()
        assert client.create_payload_index.call_count == len(PAYLOAD_INDEX_FIELDS)

    def test_uses_configured_embedding_dim_for_dense_vector(self):
        client = MagicMock()
        client.get_collections.return_value = _collections_response([])
        with patch(INDEXER_PATH, return_value=client):
            idx = HybridIndexer(embedding_dim=1024)
        idx._embedder = FakeEmbedder()

        idx.setup_collection()

        vectors_config = client.create_collection.call_args.kwargs["vectors_config"]
        assert vectors_config["dense"].size == 1024


# --------------------------------------------------------------------------- #
#  index_chunks / index_contextual_chunks                                     #
# --------------------------------------------------------------------------- #


class TestIndexChunks:
    def test_empty_input_returns_zero_and_no_upsert(self):
        client = MagicMock()
        idx = make_indexer(client)
        assert idx.index_chunks([]) == 0
        client.upsert.assert_not_called()

    def test_index_chunks_builds_points_and_upserts(self):
        client = MagicMock()
        embedder = FakeEmbedder()
        idx = make_indexer(client, embedder=embedder)

        chunks = [
            make_chunk(text="Article 19a sustainability reporting", metadata={"celex": "C1"}),
            make_chunk(text="Article 22 due diligence", metadata={"celex": "C2"}),
        ]
        n = idx.index_chunks(chunks, org_id="org-7")

        assert n == 2
        client.upsert.assert_called_once()
        points = client.upsert.call_args.kwargs["points"]
        assert len(points) == 2
        assert all(isinstance(p, PointStruct) for p in points)
        # Dense + sparse vectors present on each point.
        for p in points:
            assert set(p.vector.keys()) == {"dense", "bm25"}
            assert p.payload["org_id"] == "org-7"
            assert "content_hash" in p.payload
            assert "indexed_at" in p.payload
        # The embedder saw the raw chunk texts.
        assert embedder.embed_calls == [
            ["Article 19a sustainability reporting", "Article 22 due diligence"]
        ]

    def test_index_chunks_batches_and_upserts_per_batch(self):
        client = MagicMock()
        idx = make_indexer(client)
        chunks = [make_chunk(text=f"chunk {i}", metadata={"celex": f"C{i}"}) for i in range(5)]

        n = idx.index_chunks(chunks, batch_size=2)

        assert n == 5
        # 5 chunks / batch_size 2 -> 3 batches -> 3 upsert calls.
        assert client.upsert.call_count == 3
        batch_sizes = [len(c.kwargs["points"]) for c in client.upsert.call_args_list]
        assert batch_sizes == [2, 2, 1]

    def test_point_ids_unique_across_batches(self):
        """global_idx is folded into the id hash so duplicate celex still differ."""
        client = MagicMock()
        idx = make_indexer(client)
        chunks = [make_chunk(text=f"t{i}", metadata={"celex": "SAME"}) for i in range(4)]

        idx.index_chunks(chunks, batch_size=2)

        all_points = [p for call in client.upsert.call_args_list for p in call.kwargs["points"]]
        ids = [p.id for p in all_points]
        assert len(ids) == len(set(ids)) == 4

    def test_contextual_empty_returns_zero(self):
        client = MagicMock()
        idx = make_indexer(client)
        assert idx.index_contextual_chunks([]) == 0
        client.upsert.assert_not_called()

    def test_contextual_embeds_context_but_stores_original(self):
        """Dense embedding uses contextualized_text; payload + sparse use original."""
        client = MagicMock()
        embedder = FakeEmbedder()
        idx = make_indexer(client, embedder=embedder)

        chunk = make_chunk(
            text="Original article text",
            contextualized_text="CONTEXT PREFIX. Original article text",
            metadata={"celex": "CX", "has_context": True},
        )
        n = idx.index_contextual_chunks([chunk])

        assert n == 1
        # Embedder fed the contextualized text...
        assert embedder.embed_calls == [["CONTEXT PREFIX. Original article text"]]
        # ...but payload retains the ORIGINAL text for display.
        point = client.upsert.call_args.kwargs["points"][0]
        assert point.payload["text"] == "Original article text"
        assert point.payload["has_context"] is True

    def test_contextual_falls_back_to_text_when_no_contextualized(self):
        """getattr(c, 'contextualized_text', c.text) -> uses .text if absent."""
        client = MagicMock()
        embedder = FakeEmbedder()
        idx = make_indexer(client, embedder=embedder)

        chunk = make_chunk(text="plain text only", metadata={"celex": "CY"})
        # no contextualized_text attribute set
        assert not hasattr(chunk, "contextualized_text")

        idx.index_contextual_chunks([chunk])
        assert embedder.embed_calls == [["plain text only"]]


# --------------------------------------------------------------------------- #
#  _search_compat                                                             #
# --------------------------------------------------------------------------- #


class TestSearchCompat:
    def test_modern_query_points_uses_named_vector_using_param(self):
        """Modern API: query=<raw vector>, using=<name> (the NamedVector fix)."""
        client = MagicMock()
        # query_points returns a QueryResponse with .points
        response_points = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
        client.query_points.return_value = SimpleNamespace(points=response_points)
        idx = make_indexer(client)

        nv = NamedVector(name="dense", vector=[0.1, 0.2, 0.3])
        out = idx._search_compat(
            collection_name="eu_regulations",
            query_vector=nv,
            query_filter=None,
            limit=5,
            with_payload=True,
        )

        assert out == response_points
        client.query_points.assert_called_once()
        kw = client.query_points.call_args.kwargs
        # query gets the RAW vector, not the NamedVector object.
        assert kw["query"] == [0.1, 0.2, 0.3]
        assert kw["using"] == "dense"
        assert kw["limit"] == 5
        # Legacy .search must NOT be used when modern path succeeds.
        client.search.assert_not_called()

    def test_modern_path_extracts_name_from_sparse_named_vector(self):
        client = MagicMock()
        client.query_points.return_value = SimpleNamespace(points=[])
        idx = make_indexer(client)

        sparse = _text_to_sparse_vector("article 29 threshold")
        nsv = NamedSparseVector(name="bm25", vector=sparse)
        idx._search_compat(
            collection_name="eu_regulations",
            query_vector=nsv,
            query_filter=None,
            limit=3,
            with_payload=True,
        )
        kw = client.query_points.call_args.kwargs
        assert kw["using"] == "bm25"
        assert kw["query"] == sparse

    def test_falls_back_to_legacy_search_on_value_error(self):
        """If query_points raises ValueError('Unsupported query type'), fall back."""
        client = MagicMock()
        client.query_points.side_effect = ValueError("Unsupported query type")
        legacy_results = [SimpleNamespace(id="x")]
        client.search.return_value = legacy_results
        idx = make_indexer(client)

        nv = NamedVector(name="dense", vector=[0.5, 0.5])
        out = idx._search_compat(
            collection_name="eu_regulations",
            query_vector=nv,
            query_filter=None,
            limit=2,
            with_payload=True,
        )

        assert out is legacy_results
        # Legacy path receives the ORIGINAL NamedVector via query_vector=.
        kw = client.search.call_args.kwargs
        assert kw["query_vector"] is nv

    def test_response_without_points_attr_returned_as_is(self):
        """query_points returning a bare list (older shape) is returned directly."""
        client = MagicMock()
        bare = [SimpleNamespace(id=9)]
        client.query_points.return_value = bare
        idx = make_indexer(client)

        out = idx._search_compat(
            collection_name="eu_regulations",
            query_vector=NamedVector(name="dense", vector=[1.0]),
            query_filter=None,
            limit=1,
            with_payload=False,
        )
        assert out is bare

    def test_raises_when_no_search_api_available(self):
        """Neither query_points nor search -> explicit RuntimeError."""
        # A spec'd object exposes ONLY the listed attributes; everything else
        # raises AttributeError, so hasattr(...) is False for both APIs.
        client = MagicMock(spec=["get_collections"])
        idx = make_indexer(client)

        with pytest.raises(RuntimeError, match="neither .query_points"):
            idx._search_compat(
                collection_name="eu_regulations",
                query_vector=NamedVector(name="dense", vector=[1.0]),
                query_filter=None,
                limit=1,
                with_payload=True,
            )


# --------------------------------------------------------------------------- #
#  hybrid_search end-to-end (with mocked search compat)                       #
# --------------------------------------------------------------------------- #


class TestHybridSearch:
    def test_hybrid_search_fuses_dense_and_sparse(self):
        client = MagicMock()
        idx = make_indexer(client)

        dense = [
            SimpleNamespace(id="a", payload={"text": "ta", "celex": "C1", "framework": "CSRD"}),
            SimpleNamespace(id="b", payload={"text": "tb", "celex": "C2", "framework": "CSRD"}),
        ]
        sparse = [
            SimpleNamespace(id="b", payload={"text": "tb", "celex": "C2", "framework": "CSRD"}),
            SimpleNamespace(id="c", payload={"text": "tc", "celex": "C3", "framework": "DORA"}),
        ]
        # First _search_compat call = dense, second = sparse.
        with patch.object(idx, "_search_compat", side_effect=[dense, sparse]) as mock_sc:
            results = idx.hybrid_search("sustainability reporting", limit=10)

        assert mock_sc.call_count == 2
        # The first call must carry a NamedVector(name="dense"), second a sparse one.
        first_qv = mock_sc.call_args_list[0].kwargs["query_vector"]
        second_qv = mock_sc.call_args_list[1].kwargs["query_vector"]
        assert isinstance(first_qv, NamedVector) and first_qv.name == "dense"
        assert isinstance(second_qv, NamedSparseVector) and second_qv.name == "bm25"

        # Result dicts carry payload-derived fields; "b" (in both) ranks first.
        assert [r["id"] for r in results][0] == "b"
        assert results[0]["celex"] == "C2"
        assert all({"id", "score", "text", "celex", "framework"} <= set(r) for r in results)

    def test_depth_sets_how_many_results_enter_the_fusion(self):
        # Each retriever returns `depth` results, 3 x limit by default. With a fixed
        # depth a larger limit returns more of the same ranking: the reranker's
        # candidates start with the results of the search without reranker.
        idx = make_indexer(MagicMock())
        dense = [SimpleNamespace(id=f"c{i}", payload={"text": "t"}) for i in range(60)]
        sparse = [SimpleNamespace(id=f"c{i * 7 % 60}", payload={"text": "t"}) for i in range(60)]

        def search(**kwargs):
            ranked = dense if isinstance(kwargs["query_vector"], NamedVector) else sparse
            return ranked[: kwargs["limit"]]

        with patch.object(idx, "_search_compat", side_effect=search) as mock_sc:
            default = idx.hybrid_search("q", limit=10)
            assert [c.kwargs["limit"] for c in mock_sc.call_args_list] == [30, 30]
            small = idx.hybrid_search("q", limit=15, depth=45)
            large = idx.hybrid_search("q", limit=30, depth=45)
            assert [c.kwargs["limit"] for c in mock_sc.call_args_list[2:]] == [45, 45, 45, 45]
            idx.hybrid_search("q", limit=30, depth=5)
            assert mock_sc.call_args_list[-1].kwargs["limit"] == 30  # never below limit

        assert len(default) == 10
        assert len(large) == 30
        assert [r["id"] for r in large[:15]] == [r["id"] for r in small]

    def test_hybrid_search_exposes_raw_per_retriever_scores(self):
        # Additive dense_score / sparse_score let a downstream consumer gate on
        # retrieval strength. A chunk in both carries both; a chunk from only one
        # retriever carries None for the other. Existing keys are unchanged.
        client = MagicMock()
        idx = make_indexer(client)
        dense = [
            SimpleNamespace(id="a", score=0.82, payload={"text": "ta", "framework": "CSRD"}),
            SimpleNamespace(id="b", score=0.40, payload={"text": "tb", "framework": "CSRD"}),
        ]
        sparse = [
            SimpleNamespace(id="b", score=7.5, payload={"text": "tb", "framework": "CSRD"}),
            SimpleNamespace(id="c", score=3.1, payload={"text": "tc", "framework": "DORA"}),
        ]
        with patch.object(idx, "_search_compat", side_effect=[dense, sparse]):
            results = idx.hybrid_search("q", limit=10)

        by_id = {r["id"]: r for r in results}
        # "a": dense only.
        assert by_id["a"]["dense_score"] == pytest.approx(0.82)
        assert by_id["a"]["sparse_score"] is None
        # "b": both retrievers.
        assert by_id["b"]["dense_score"] == pytest.approx(0.40)
        assert by_id["b"]["sparse_score"] == pytest.approx(7.5)
        # "c": sparse only.
        assert by_id["c"]["dense_score"] is None
        assert by_id["c"]["sparse_score"] == pytest.approx(3.1)

    def test_hybrid_search_exposes_provenance_for_citation_verification(self):
        # The citation verifier reads the base act (source_celex) and the prompt
        # labels name the act; points that predate a field carry None.
        client = MagicMock()
        idx = make_indexer(client)
        payload = {
            "text": "t",
            "celex": "32024R1689",
            "source_celex": "02024R1689-20260727",
            "act_title": "Artificial Intelligence Act",
            "frameworks": ["AI_ACT"],
            "chunk_index": 12,
        }
        dense = [SimpleNamespace(id="a", payload=payload)]
        old = [SimpleNamespace(id="b", payload={"text": "old", "celex": "32016R0679"})]
        with patch.object(idx, "_search_compat", side_effect=[dense, old]):
            results = {r["id"]: r for r in idx.hybrid_search("q", limit=10)}
        assert results["a"]["source_celex"] == "02024R1689-20260727"
        assert results["a"]["act_title"] == "Artificial Intelligence Act"
        assert results["a"]["frameworks"] == ["AI_ACT"]
        assert results["a"]["chunk_index"] == 12
        assert results["b"]["source_celex"] is None and results["b"]["chunk_index"] is None

    def test_hybrid_search_respects_limit(self):
        client = MagicMock()
        idx = make_indexer(client)
        dense = [SimpleNamespace(id=f"d{i}", payload={"text": f"d{i}"}) for i in range(10)]
        sparse = [SimpleNamespace(id=f"s{i}", payload={"text": f"s{i}"}) for i in range(10)]
        with patch.object(idx, "_search_compat", side_effect=[dense, sparse]):
            results = idx.hybrid_search("query", limit=3)
        assert len(results) == 3

    def test_hybrid_search_passes_filter_to_both_calls(self):
        """The same built filter is handed to both the dense and sparse search."""
        client = MagicMock()
        idx = make_indexer(client)
        with patch.object(idx, "_search_compat", side_effect=[[], []]) as mock_sc:
            idx.hybrid_search("q", org_id="org-1")
        f1 = mock_sc.call_args_list[0].kwargs["query_filter"]
        f2 = mock_sc.call_args_list[1].kwargs["query_filter"]
        assert f1 is f2
        assert isinstance(f1, Filter)


# --------------------------------------------------------------------------- #
#  IsEmptyCondition (NOT IsNullCondition) - the e6346c0 fix                    #
# --------------------------------------------------------------------------- #


def _iter_conditions(flt):
    """Yield every leaf condition inside a (possibly nested) Filter."""
    for bucket in ("must", "should", "must_not"):
        for cond in getattr(flt, bucket, None) or []:
            if isinstance(cond, Filter):
                yield from _iter_conditions(cond)
            else:
                yield cond


class TestNullFilterUsesIsEmptyCondition:
    def test_superseded_filter_is_is_empty_condition(self):
        """Default temporal filter excludes superseded via IsEmptyCondition.

        Critical: it must be IsEmptyCondition (matches missing-or-null keys), not
        IsNullCondition. Qdrant drops null payload keys, so IsNullCondition would
        match nothing and filter out the whole in-force corpus (commit e6346c0).
        """
        f = HybridIndexer._build_filter(include_superseded=False, allow_all_orgs=True)
        empties = [c for c in _iter_conditions(f) if isinstance(c, IsEmptyCondition)]
        keys = {c.is_empty.key for c in empties}
        assert "superseded_by" in keys

    def test_org_shared_filter_is_is_empty_condition(self):
        """No org context -> shared-only guard uses IsEmptyCondition on org_id."""
        f = HybridIndexer._build_filter(include_superseded=True)  # org_id None
        empties = [c for c in _iter_conditions(f) if isinstance(c, IsEmptyCondition)]
        keys = {c.is_empty.key for c in empties}
        assert "org_id" in keys

    def test_org_scoped_should_contains_is_empty_for_shared(self):
        """With org_id: should = [match(org_id), IsEmpty(org_id)] (org OR shared)."""
        f = HybridIndexer._build_filter(include_superseded=True, org_id="org-42")
        empties = [c for c in _iter_conditions(f) if isinstance(c, IsEmptyCondition)]
        keys = {c.is_empty.key for c in empties}
        # The 'shared' arm of the org OR is an IsEmptyCondition on org_id.
        assert "org_id" in keys

    def test_module_does_not_import_is_null_condition(self):
        """Guard against regression: the fix replaced IsNullCondition entirely."""
        from src.nlp.embedding import indexer as indexer_mod

        assert not hasattr(indexer_mod, "IsNullCondition")
        assert hasattr(indexer_mod, "IsEmptyCondition")

    def test_allow_all_orgs_drops_org_guard_only(self):
        """allow_all_orgs escape hatch removes the org_id IsEmpty guard."""
        f = HybridIndexer._build_filter(include_superseded=True, allow_all_orgs=True)
        # include_superseded=True + allow_all_orgs=True + no framework -> no conditions.
        assert f is None

    def test_framework_list_uses_or_should_block(self):
        """A multi-framework list builds a nested should (OR) block."""
        f = HybridIndexer._build_filter(
            framework=["CSRD", "DORA"], include_superseded=True, allow_all_orgs=True
        )
        assert isinstance(f, Filter)
        nested = [c for c in f.must if isinstance(c, Filter)]
        assert nested, "expected a nested Filter(should=[...]) for the framework OR"
        assert len(nested[0].should) == 2


# --------------------------------------------------------------------------- #
#  delete_org_chunks / get_collection_stats                                   #
# --------------------------------------------------------------------------- #


class TestDeleteOrgChunks:
    def test_falsy_org_id_is_noop(self):
        """An empty org_id must never reach client.delete (corpus-wipe guard)."""
        client = MagicMock()
        idx = make_indexer(client)
        idx.delete_org_chunks("")
        client.delete.assert_not_called()

    def test_deletes_only_that_orgs_chunks(self):
        client = MagicMock()
        idx = make_indexer(client)
        idx.delete_org_chunks("org-9")
        client.delete.assert_called_once()
        selector = client.delete.call_args.kwargs["points_selector"]
        assert isinstance(selector, Filter)
        # Selector matches org_id == org-9 (and nothing about shared corpus).
        cond = selector.must[0]
        assert cond.key == "org_id"
        assert cond.match.value == "org-9"


class TestCollectionStats:
    def test_stats_basic_fields(self):
        client = MagicMock()
        info = SimpleNamespace(
            points_count=123,
            status=SimpleNamespace(value="green"),
            vectors_count=None,
            indexed_vectors_count=120,
        )
        client.get_collection.return_value = info
        idx = make_indexer(client)

        stats = idx.get_collection_stats()
        assert stats["points_count"] == 123
        assert stats["status"] == "green"
        # vectors_count is None -> omitted; indexed_vectors_count present -> kept.
        assert "vectors_count" not in stats
        assert stats["indexed_vectors_count"] == 120

    def test_stats_status_without_value_attr_stringified(self):
        client = MagicMock()
        info = SimpleNamespace(points_count=0, status="yellow")
        client.get_collection.return_value = info
        idx = make_indexer(client)
        stats = idx.get_collection_stats()
        assert stats["status"] == "yellow"


class TestMarkSuperseded:
    def test_marks_chunks_and_returns_count(self):
        client = MagicMock()
        client.count.return_value.count = 3
        idx = make_indexer(client)

        n = idx.mark_superseded("32022L2464", "32026L0470")

        assert n == 3
        client.set_payload.assert_called_once()
        kwargs = client.set_payload.call_args.kwargs
        assert kwargs["payload"] == {"superseded_by": "32026L0470"}
        assert kwargs["collection_name"] == idx.COLLECTION_NAME
        # the points selector filters on the target CELEX
        cond = kwargs["points"].must[0]
        assert cond.key == "celex"
        assert cond.match.value == "32022L2464"

    def test_zero_count_skips_set_payload(self):
        client = MagicMock()
        client.count.return_value.count = 0
        idx = make_indexer(client)

        n = idx.mark_superseded("32022L2464", "X")

        assert n == 0
        client.set_payload.assert_not_called()

    def test_falsy_args_are_noop(self):
        client = MagicMock()
        idx = make_indexer(client)

        assert idx.mark_superseded("", "X") == 0
        assert idx.mark_superseded("C1", "") == 0
        client.count.assert_not_called()
        client.set_payload.assert_not_called()


# --------------------------------------------------------------------------- #
#  Deterministic point ids                                                    #
# --------------------------------------------------------------------------- #


def _rich_chunk(text="1. Member States shall comply.", **overrides):
    meta = {
        "celex": "32022L2464",
        "source_celex": "02022L2464-20260318",
        "framework": "CSRD",
        "frameworks": ["CSRD", "CSDDD"],
        "lang": "IT",
        "article": "Art. 3",
        "paragraph": "1-2",
        "title": "Recepimento",
        "eli": "http://data.europa.eu/eli/dir/2022/2464/2026-03-18",
        "url": "https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02022L2464-20260318",
        "consolidated_as_of": "2026-03-18",
        "chunk_index": 7,
        "chunk_type": "article",
        "article_number": "Art. 3",
        "section_title": "CAPO I",
        "hierarchy": "CAPO I > Art. 3",
    }
    meta.update(overrides)
    return SimpleNamespace(text=text, metadata=meta, contextualized_text=f"[CSRD]\n{text}")


class TestDeterministicIds:
    def test_point_id_key_format(self):
        key = point_id_key("32022L2464", "EN", "Art. 5", 12, "some text")
        digest = hashlib.sha1(b"some text").hexdigest()[:12]
        assert key == f"32022L2464|EN|Art. 5|12|{digest}"

    def test_make_point_id_is_a_stable_uuid5(self):
        a = make_point_id("32022L2464", "EN", "Art. 5", 12, "some text")
        b = make_point_id("32022L2464", "EN", "Art. 5", 12, "some text")
        assert a == b
        assert uuid.UUID(a).version == 5
        expected = uuid.uuid5(
            NORMAAI_ID_NAMESPACE, point_id_key("32022L2464", "EN", "Art. 5", 12, "some text")
        )
        assert a == str(expected)

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"lang": "IT"},
            {"article": "Art. 6"},
            {"chunk_index": 13},
            {"text": "other text"},
            {"celex": "32024R1689"},
        ],
    )
    def test_any_component_changes_the_id(self, kwargs):
        base = {
            "celex": "32022L2464",
            "lang": "EN",
            "article": "Art. 5",
            "chunk_index": 12,
            "text": "t",
        }
        assert make_point_id(**base) != make_point_id(**{**base, **kwargs})

    def test_tenant_documents_never_collide_with_shared_or_other_tenants(self):
        shared = make_point_id("DOC_1", "EN", "", 0, "t")
        org_a = make_point_id("DOC_1", "EN", "", 0, "t", org_id="org-a")
        org_b = make_point_id("DOC_1", "EN", "", 0, "t", org_id="org-b")
        assert len({shared, org_a, org_b}) == 3

    def test_index_derives_id_from_chunk_metadata(self):
        client = MagicMock()
        idx = make_indexer(client)
        chunk = _rich_chunk()

        idx.index_contextual_chunks([chunk])
        idx.index_contextual_chunks([chunk])  # re-index: same id, no duplicate

        ids = [call.kwargs["points"][0].id for call in client.upsert.call_args_list]
        assert ids[0] == ids[1]
        assert ids[0] == make_point_id("32022L2464", "IT", "Art. 3", 7, chunk.text)

    def test_index_chunks_uses_same_id_scheme(self):
        client = MagicMock()
        idx = make_indexer(client)
        chunk = _rich_chunk()
        idx.index_chunks([chunk])
        point = client.upsert.call_args.kwargs["points"][0]
        assert point.id == make_point_id("32022L2464", "IT", "Art. 3", 7, chunk.text)

    def test_payload_carries_provenance_fields(self):
        client = MagicMock()
        idx = make_indexer(client)
        idx.index_contextual_chunks([_rich_chunk()])
        payload = client.upsert.call_args.kwargs["points"][0].payload
        assert payload["celex"] == "32022L2464"
        assert payload["source_celex"] == "02022L2464-20260318"
        assert payload["lang"] == "IT"
        assert payload["article"] == "Art. 3"
        assert payload["article_number"] == "Art. 3"
        assert payload["paragraph"] == "1-2"
        assert payload["title"] == "Recepimento"
        assert payload["eli"].endswith("/2022/2464/2026-03-18")
        assert payload["url"].startswith("https://eur-lex.europa.eu/legal-content/IT/")
        assert payload["consolidated_as_of"] == "2026-03-18"
        assert payload["chunk_index"] == 7
        assert payload["frameworks"] == ["CSRD", "CSDDD"]
        assert payload["framework"] == "CSRD"
        assert payload["org_id"] is None

    def test_legacy_chunks_without_new_metadata_still_index(self):
        """Minimal chunks (scheduler, tests) fall back to EN / position-based ids."""
        client = MagicMock()
        idx = make_indexer(client)
        chunks = [make_chunk(text=f"t{i}") for i in range(3)]
        idx.index_contextual_chunks(chunks)
        points = client.upsert.call_args.kwargs["points"]
        assert [p.payload["chunk_index"] for p in points] == [0, 1, 2]
        assert all(p.payload["lang"] == "EN" for p in points)
        assert all(p.payload["frameworks"] == ["CSRD"] for p in points)
        assert len({p.id for p in points}) == 3


# --------------------------------------------------------------------------- #
#  Per-act re-index                                                           #
# --------------------------------------------------------------------------- #


def _leaf_conditions(flt):
    for bucket in ("must", "should", "must_not"):
        for cond in getattr(flt, bucket, None) or []:
            if isinstance(cond, Filter):
                yield from _leaf_conditions(cond)
            else:
                yield cond


class TestReindexAct:
    def test_deletes_act_language_then_upserts(self):
        client = MagicMock()
        idx = make_indexer(client)
        chunks = [_rich_chunk(text=f"body {i}", chunk_index=i) for i in range(3)]

        n = idx.reindex_act("32022L2464", "IT", chunks)

        assert n == 3
        client.delete.assert_called_once()
        selector = client.delete.call_args.kwargs["points_selector"]
        matches = {
            c.key: c.match.value
            for c in _leaf_conditions(selector)
            if isinstance(c, FieldCondition)
        }
        assert matches == {"celex": "32022L2464", "lang": "IT"}
        # delete happens BEFORE the upsert
        order = [name for name, _args, _kwargs in client.method_calls]
        assert order.index("delete") < order.index("upsert")

    def test_empty_chunks_do_not_delete(self):
        client = MagicMock()
        idx = make_indexer(client)
        assert idx.reindex_act("32022L2464", "IT", []) == 0
        client.delete.assert_not_called()
        client.upsert.assert_not_called()

    def test_delete_act_points_without_lang_matches_all_languages(self):
        client = MagicMock()
        idx = make_indexer(client)
        idx.delete_act_points("32022L2464")
        selector = client.delete.call_args.kwargs["points_selector"]
        keys = [c.key for c in _leaf_conditions(selector) if isinstance(c, FieldCondition)]
        assert keys == ["celex"]

    def test_delete_act_points_falsy_celex_is_noop(self):
        client = MagicMock()
        idx = make_indexer(client)
        idx.delete_act_points("")
        client.delete.assert_not_called()


# --------------------------------------------------------------------------- #
#  Sparse IDF modifier + version-aware setup                                  #
# --------------------------------------------------------------------------- #


def _existing_collection_info(modifier=Modifier.IDF, dense_size=4):
    sparse = {"bm25": SimpleNamespace(modifier=modifier)}
    dense = {"dense": SimpleNamespace(size=dense_size)}
    params = SimpleNamespace(sparse_vectors=sparse, vectors=dense)
    return SimpleNamespace(config=SimpleNamespace(params=params))


class TestSparseIdfSetup:
    def test_new_collection_uses_idf_modifier(self):
        client = MagicMock()
        client.get_collections.return_value = _collections_response([])
        idx = make_indexer(client)

        idx.setup_collection()

        sparse_cfg = client.create_collection.call_args.kwargs["sparse_vectors_config"]
        assert sparse_cfg["bm25"].modifier == Modifier.IDF
        assert idx.sparse_idf_enabled is True

    def test_existing_idf_collection_verified_without_warning(self, caplog):
        client = MagicMock()
        client.get_collections.return_value = _collections_response(["eu_regulations"])
        client.get_collection.return_value = _existing_collection_info()
        client.retrieve.return_value = []
        with patch(INDEXER_PATH, return_value=client):
            idx = HybridIndexer(embedding_dim=4)
        idx._embedder = FakeEmbedder()

        with caplog.at_level(logging.WARNING, logger="src.nlp.embedding.indexer"):
            idx.setup_collection()

        assert idx.sparse_idf_enabled is True
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
        client.create_collection.assert_not_called()

    def test_existing_collection_without_idf_warns_operator(self, caplog):
        client = MagicMock()
        client.get_collections.return_value = _collections_response(["eu_regulations"])
        client.get_collection.return_value = _existing_collection_info(modifier=None)
        client.retrieve.return_value = []
        with patch(INDEXER_PATH, return_value=client):
            idx = HybridIndexer(embedding_dim=4)
        idx._embedder = FakeEmbedder()

        with caplog.at_level(logging.WARNING, logger="src.nlp.embedding.indexer"):
            idx.setup_collection()

        assert idx.sparse_idf_enabled is False
        messages = [r.getMessage() for r in caplog.records]
        assert any("IDF modifier" in m and "--recreate" in m for m in messages)
        # Idempotent: the existing collection is kept, not recreated.
        client.delete_collection.assert_not_called()
        client.create_collection.assert_not_called()
        assert idx.get_collection_stats.__self__ is idx  # sanity: method still bound

    def test_dense_size_mismatch_warns(self, caplog):
        client = MagicMock()
        client.get_collections.return_value = _collections_response(["eu_regulations"])
        client.get_collection.return_value = _existing_collection_info(dense_size=768)
        client.retrieve.return_value = []
        with patch(INDEXER_PATH, return_value=client):
            idx = HybridIndexer(embedding_dim=1024)
        idx._embedder = FakeEmbedder()

        with caplog.at_level(logging.WARNING, logger="src.nlp.embedding.indexer"):
            idx.setup_collection()

        assert any("768-dim" in r.getMessage() for r in caplog.records)

    def test_embedding_model_mismatch_warns(self, caplog):
        client = MagicMock()
        client.get_collections.return_value = _collections_response(["eu_regulations"])
        client.get_collection.return_value = _existing_collection_info()
        client.retrieve.return_value = [
            SimpleNamespace(payload={"kind": CORPUS_META_KIND, "embedding_model": "old/model"})
        ]
        with patch(INDEXER_PATH, return_value=client):
            idx = HybridIndexer(embedding_dim=4, embedding_model="new/model")
        idx._embedder = FakeEmbedder()

        with caplog.at_level(logging.WARNING, logger="src.nlp.embedding.indexer"):
            idx.setup_collection()

        assert any(
            "old/model" in r.getMessage() and "new/model" in r.getMessage() for r in caplog.records
        )

    def test_stats_report_sparse_idf_once_known(self):
        client = MagicMock()
        info = SimpleNamespace(points_count=5, status="green")
        client.get_collection.return_value = info
        idx = make_indexer(client)
        assert "sparse_idf" not in idx.get_collection_stats()
        idx.sparse_idf_enabled = True
        assert idx.get_collection_stats()["sparse_idf"] is True


# --------------------------------------------------------------------------- #
#  Corpus metadata point                                                      #
# --------------------------------------------------------------------------- #


class TestCorpusMeta:
    def test_meta_id_is_uuid5_of_fixed_key(self):
        assert str(uuid.uuid5(NORMAAI_ID_NAMESPACE, "normaai-corpus-meta")) == CORPUS_META_ID

    def test_write_corpus_meta_upserts_fixed_point(self):
        client = MagicMock()
        with patch(INDEXER_PATH, return_value=client):
            idx = HybridIndexer(embedding_dim=4, embedding_model="m/odel")
        acts = [{"celex": "32022L2464", "lang": "EN", "chunks": 10}]

        payload = idx.write_corpus_meta(acts, extra={"languages": ["EN"]})

        point = client.upsert.call_args.kwargs["points"][0]
        assert point.id == CORPUS_META_ID
        assert point.vector["dense"] == [1.0, 0.0, 0.0, 0.0]
        assert point.payload is payload or point.payload == payload
        assert payload["kind"] == CORPUS_META_KIND
        assert payload["acts"] == acts
        assert payload["embedding_model"] == "m/odel"
        assert payload["org_id"] == CORPUS_META_ORG
        assert payload["languages"] == ["EN"]
        assert len(payload["corpus_as_of"]) == 10  # ISO date
        assert payload["built_at"].startswith(payload["corpus_as_of"])

    def test_write_corpus_meta_honours_explicit_date_and_model(self):
        client = MagicMock()
        idx = make_indexer(client)
        payload = idx.write_corpus_meta([], corpus_as_of="2026-10-01", embedding_model="x")
        assert payload["corpus_as_of"] == "2026-10-01"
        assert payload["embedding_model"] == "x"

    def test_get_corpus_info_returns_payload(self):
        client = MagicMock()
        client.retrieve.return_value = [
            SimpleNamespace(payload={"kind": CORPUS_META_KIND, "corpus_as_of": "2026-10-23"})
        ]
        idx = make_indexer(client)
        info = idx.get_corpus_info()
        assert info == {"kind": CORPUS_META_KIND, "corpus_as_of": "2026-10-23"}
        kwargs = client.retrieve.call_args.kwargs
        assert kwargs["ids"] == [CORPUS_META_ID]
        assert kwargs["with_payload"] is True

    def test_get_corpus_info_none_when_missing(self):
        client = MagicMock()
        client.retrieve.return_value = []
        assert make_indexer(client).get_corpus_info() is None

    def test_get_corpus_info_none_on_error(self):
        client = MagicMock()
        client.retrieve.side_effect = RuntimeError("qdrant down")
        assert make_indexer(client).get_corpus_info() is None

    def test_get_corpus_info_ignores_foreign_point(self):
        client = MagicMock()
        client.retrieve.return_value = [SimpleNamespace(payload={"text": "not meta"})]
        assert make_indexer(client).get_corpus_info() is None

    def test_hybrid_search_never_returns_the_meta_point(self):
        client = MagicMock()
        idx = make_indexer(client)
        with patch.object(idx, "_search_compat", side_effect=[[], []]) as mock_sc:
            idx.hybrid_search("q", include_superseded=True, allow_all_orgs=True)
        flt = mock_sc.call_args_list[0].kwargs["query_filter"]
        assert isinstance(flt, Filter)
        excluded = [c for c in (flt.must_not or []) if isinstance(c, FieldCondition)]
        assert [(c.key, c.match.value) for c in excluded] == [("kind", CORPUS_META_KIND)]

    def test_meta_exclusion_keeps_existing_conditions(self):
        base = HybridIndexer._build_filter(framework="CSRD")
        flt = HybridIndexer._with_meta_exclusion(base)
        assert flt.must == base.must
        assert len(flt.must_not) == 1


# --------------------------------------------------------------------------- #
#  Filter extensions: language + multi-framework acts                         #
# --------------------------------------------------------------------------- #


class TestFilterExtensions:
    def test_lang_filter_single(self):
        f = HybridIndexer._build_filter(include_superseded=True, allow_all_orgs=True, lang="it")
        conds = [c for c in _leaf_conditions(f) if isinstance(c, FieldCondition)]
        assert [(c.key, c.match.value) for c in conds] == [("lang", "IT")]

    def test_lang_filter_list_is_or(self):
        f = HybridIndexer._build_filter(
            include_superseded=True, allow_all_orgs=True, lang=["EN", "IT"]
        )
        nested = [c for c in f.must if isinstance(c, Filter)]
        assert {c.match.value for c in nested[0].should} == {"EN", "IT"}

    def test_framework_matches_primary_or_frameworks_list(self):
        f = HybridIndexer._build_filter(
            framework="CSDDD", include_superseded=True, allow_all_orgs=True
        )
        arm = f.must[0]
        assert isinstance(arm, Filter)
        assert [(c.key, c.match.value) for c in arm.should] == [
            ("framework", "CSDDD"),
            ("frameworks", "CSDDD"),
        ]

    def test_hybrid_search_passes_lang_filter(self):
        client = MagicMock()
        idx = make_indexer(client)
        with patch.object(idx, "_search_compat", side_effect=[[], []]) as mock_sc:
            idx.hybrid_search("q", lang_filter="IT")
        flt = mock_sc.call_args_list[0].kwargs["query_filter"]
        keys = {c.key for c in _leaf_conditions(flt) if isinstance(c, FieldCondition)}
        assert "lang" in keys
