"""Unit tests for the Hybrid Search (Qdrant) indexer.

Tests cover:
- Sparse vector generation (_text_to_sparse_vector — module-level helper)
- Reciprocal Rank Fusion (HybridIndexer._reciprocal_rank_fusion)
- Query filter construction (HybridIndexer._build_filter)
- Determinism and hash properties

NOTE 2026-04-28: realigned to actual indexer.py API.
- _text_to_sparse_vector is a module-level function, not a class method.
- _reciprocal_rank_fusion has no top_k param (caller slices the result).
- RRF returns list[tuple[id, score]] sorted desc, not list[dict].
- _build_filter default behavior excludes superseded chunks (always returns
  a Filter with at least the IsNullCondition); temporal filtering is on by
  design for legal RAG correctness.
"""

from unittest.mock import MagicMock

from src.nlp.embedding.indexer import (
    HybridIndexer,
    _text_to_sparse_vector,
)

# ------------------------------------------------------------------ #
#  Sparse Vector Tests                                                #
# ------------------------------------------------------------------ #


class TestSparseVectorGeneration:
    """Test the hash-based sparse vector used for BM25-like retrieval."""

    def test_deterministic_output(self):
        """Same input should always produce same sparse vector."""
        v1 = _text_to_sparse_vector("Article 19a of the CSRD directive")
        v2 = _text_to_sparse_vector("Article 19a of the CSRD directive")
        assert v1.indices == v2.indices
        assert v1.values == v2.values

    def test_different_text_different_vectors(self):
        """Different inputs should produce different sparse vectors."""
        v1 = _text_to_sparse_vector("CSRD sustainability reporting")
        v2 = _text_to_sparse_vector("GDPR data protection regulation")
        assert v1.indices != v2.indices

    def test_empty_text_returns_empty_vector(self):
        """Empty text should return a valid but empty sparse vector."""
        v = _text_to_sparse_vector("")
        assert len(v.indices) == 0
        assert len(v.values) == 0

    def test_indices_within_vocab_size(self):
        """All indices should be within [0, vocab_size)."""
        vocab_size = 30000
        v = _text_to_sparse_vector(
            "The CSRD directive requires large companies to report sustainability",
            vocab_size=vocab_size,
        )
        for idx in v.indices:
            assert 0 <= idx < vocab_size

    def test_term_frequency_affects_values(self):
        """Repeated terms should have higher values in the sparse vector."""
        v_single = _text_to_sparse_vector("CSRD")
        v_repeated = _text_to_sparse_vector("CSRD CSRD CSRD")
        # The hash for "csrd" should have a higher value when repeated
        if v_single.indices and v_repeated.indices:
            common = set(v_single.indices) & set(v_repeated.indices)
            if common:
                idx = list(common)[0]
                val_single = v_single.values[v_single.indices.index(idx)]
                val_repeated = v_repeated.values[v_repeated.indices.index(idx)]
                assert val_repeated >= val_single


# ------------------------------------------------------------------ #
#  Reciprocal Rank Fusion Tests                                       #
# ------------------------------------------------------------------ #


class TestReciprocalRankFusion:
    """Test the RRF merge of dense and sparse search results.

    Real signature: _reciprocal_rank_fusion(dense, sparse, k=60) -> list[tuple[id, score]]
    Sorted by score desc. Caller slices to top_k externally.
    """

    def test_rrf_basic_merge(self):
        """RRF should merge two lists, favoring items ranked highly in both."""
        # Mock dense results: doc_a at rank 1, doc_b at rank 2
        dense_results = [
            MagicMock(id="doc_a", score=0.95, payload={"text": "a"}),
            MagicMock(id="doc_b", score=0.80, payload={"text": "b"}),
        ]
        # Mock sparse results: doc_b at rank 1, doc_c at rank 2
        sparse_results = [
            MagicMock(id="doc_b", score=0.90, payload={"text": "b"}),
            MagicMock(id="doc_c", score=0.70, payload={"text": "c"}),
        ]

        merged = HybridIndexer._reciprocal_rank_fusion(dense_results, sparse_results, k=60)

        # Result is list[tuple[id, score]] sorted desc
        assert len(merged) == 3  # union of {doc_a, doc_b, doc_c}
        result_ids = [doc_id for doc_id, _ in merged]
        assert "doc_b" in result_ids
        # doc_b appears in both lists -> should rank first
        assert merged[0][0] == "doc_b"

    def test_rrf_empty_lists(self):
        """RRF with empty lists should return empty."""
        merged = HybridIndexer._reciprocal_rank_fusion([], [], k=60)
        assert merged == []

    def test_rrf_single_list(self):
        """RRF with one empty list should still return results from the other."""
        dense_results = [
            MagicMock(id="doc_a", score=0.95, payload={"text": "a"}),
        ]
        merged = HybridIndexer._reciprocal_rank_fusion(dense_results, [], k=60)
        assert len(merged) == 1
        assert merged[0][0] == "doc_a"

    def test_rrf_caller_can_slice_top_k(self):
        """Caller is responsible for top_k slicing; verify result is fully sorted."""
        dense = [
            MagicMock(id=f"d{i}", score=0.9 - i * 0.1, payload={"text": f"d{i}"}) for i in range(10)
        ]
        sparse = [
            MagicMock(id=f"s{i}", score=0.9 - i * 0.1, payload={"text": f"s{i}"}) for i in range(10)
        ]

        merged = HybridIndexer._reciprocal_rank_fusion(dense, sparse, k=60)
        # Union of 20 distinct ids -> 20 results
        assert len(merged) == 20
        # Verify sorted by score desc
        scores = [score for _, score in merged]
        assert scores == sorted(scores, reverse=True)
        # Caller can slice: merged[:5] gives top 5
        top5 = merged[:5]
        assert len(top5) == 5


# ------------------------------------------------------------------ #
#  Filter Construction Tests                                          #
# ------------------------------------------------------------------ #


class TestFilterConstruction:
    """Test Qdrant filter construction for multi-tenant hybrid search.

    Real signature: _build_filter(framework=None, chunk_type=None,
                                   include_superseded=False, org_id=None)
    By design: temporal filter (exclude superseded) is ALWAYS active by default
    -> the function never returns None when called with defaults.
    To get an unfiltered query you must pass include_superseded=True
    AND no other constraints.
    """

    def test_framework_filter(self):
        """Should create a filter that matches the specified framework."""
        f = HybridIndexer._build_filter(framework="CSRD")
        assert f is not None
        # Should contain at least 2 must conditions: framework + superseded null
        assert len(f.must) >= 2

    def test_default_filter_excludes_superseded(self):
        """Default behavior must filter out superseded chunks (legal correctness)."""
        f = HybridIndexer._build_filter()
        assert f is not None
        # At least one IsNullCondition on superseded_by must be present
        assert len(f.must) >= 1

    def test_no_filter_only_with_allow_all_orgs(self):
        """Truly unconstrained filter requires the explicit admin escape hatch.

        Fail-closed contract: by default (no org context) the search is scoped
        to shared chunks, so _build_filter returns a filter even when otherwise
        unconstrained. Only allow_all_orgs=True yields None.
        """
        assert HybridIndexer._build_filter(include_superseded=True, allow_all_orgs=True) is None

    def test_fail_closed_shared_only_without_org(self):
        """No org context -> filter restricts to shared chunks (never all tenants)."""
        f = HybridIndexer._build_filter(include_superseded=True)  # org_id None, no escape hatch
        assert f is not None
        # The single condition must be the shared-only (org_id is null) guard.
        assert len(f.must) == 1

    def test_org_scoped_filter_includes_shared(self):
        """With an org_id, results = that org's chunks OR shared (org_id null)."""
        f = HybridIndexer._build_filter(include_superseded=True, org_id="org-123")
        assert f is not None
        # One 'must' wrapping a 'should' of [org match, org_id is null].
        assert len(f.must) == 1

    def test_include_superseded_param(self):
        """Passing include_superseded=False (default) keeps temporal filter on."""
        f = HybridIndexer._build_filter(include_superseded=False)
        assert f is not None
