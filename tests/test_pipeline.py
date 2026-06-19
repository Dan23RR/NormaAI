"""Tests for the IngestionPipeline orchestration (src/pipeline.py).

The pipeline wires together the EUR-Lex SPARQL client, the legal/contextual
chunkers, the document processor and the Qdrant HybridIndexer. None of those
heavy collaborators belong in a unit test, so every one is patched *where it is
imported* (``src.pipeline.*``). These tests therefore exercise pure
orchestration logic:

- seed() happy path with EUR-Lex enabled, chunk enrichment and indexing
- the temporal-metadata population (effective_date / superseded_by)
- per-document download error / too-short-HTML handling and stats aggregation
- the empty-corpus path (no chunks -> indexed = 0, indexer.index NOT called)
- update() amendment + new-legislation flow
- process_document() success / no-text / no-chunks branches and org_id passthrough
- stats() with a healthy and an unavailable indexer
- the main() CLI --action dispatch (seed / update / stats)

No real network, Qdrant, model or DB is touched.
"""

import sys
from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest

import src.nlp.chunking.legal_chunker as legal_chunker_mod
import src.pipeline as pipeline_mod
from src.pipeline import IngestionPipeline


# --------------------------------------------------------------------------- #
# Lightweight stand-ins for the real collaborator data structures.
# --------------------------------------------------------------------------- #
@dataclass
class FakeReg:
    """Minimal stand-in for RegulationMetadata."""

    celex: str
    framework: str = "CSRD"
    title: str = "A regulation title that is reasonably long for slicing"
    date_document: str | None = None
    is_in_force: bool | None = None


@dataclass
class FakeChunk:
    """Minimal stand-in for a LegalChunk (anything with .text/.metadata)."""

    text: str
    metadata: dict = field(default_factory=dict)


@dataclass
class FakeContextChunk:
    """Minimal stand-in for a ContextualChunk."""

    text: str
    contextualized_text: str = ""
    metadata: dict = field(default_factory=dict)


def make_settings():
    """A MagicMock settings object exposing the attributes pipeline reads."""
    s = MagicMock()
    s.eurlex_sparql_endpoint = "http://sparql.test"
    s.qdrant_host = "localhost"
    s.qdrant_port = 6333
    s.embedding_model = "test-model"
    s.embedding_dimension = 768
    s.embedding_batch_size = 32
    s.data_source = "eurlex"
    return s


@pytest.fixture
def patched_pipeline():
    """Build an IngestionPipeline with all heavy collaborators replaced.

    Yields (pipeline, mocks) where mocks is a dict of the patched instances so
    tests can configure return values and assert call patterns.
    """
    settings = make_settings()

    eurlex = MagicMock(name="EurLexClient")
    indexer = MagicMock(name="HybridIndexer")
    ctx_chunker = MagicMock(name="ContextualChunker")
    doc_processor = MagicMock(name="UnifiedDocumentProcessor")

    # ContextualChunker.enrich_single returns a fresh ContextualChunk whose
    # metadata starts empty (the real one does), so the pipeline's
    # ctx.metadata.update(chunk.metadata) merge can be observed.
    def _enrich_single(text, framework="", article="", section=""):
        return FakeContextChunk(
            text=text,
            contextualized_text=f"[{framework}]\n{text}",
            metadata={"enriched": True},
        )

    ctx_chunker.enrich_single.side_effect = _enrich_single

    with (
        patch.object(pipeline_mod, "get_settings", return_value=settings),
        patch.object(pipeline_mod, "EurLexClient", return_value=eurlex),
        patch.object(pipeline_mod, "HybridIndexer", return_value=indexer),
        patch.object(pipeline_mod, "ContextualChunker", return_value=ctx_chunker),
        patch.object(pipeline_mod, "UnifiedDocumentProcessor", return_value=doc_processor),
    ):
        p = IngestionPipeline()
        yield (
            p,
            {
                "settings": settings,
                "eurlex": eurlex,
                "indexer": indexer,
                "ctx_chunker": ctx_chunker,
                "doc_processor": doc_processor,
            },
        )


# --------------------------------------------------------------------------- #
# __init__
# --------------------------------------------------------------------------- #
class TestInit:
    def test_wires_collaborators_from_settings(self, patched_pipeline):
        p, m = patched_pipeline
        # The constructed instances are exactly the patched mocks.
        assert p.eurlex is m["eurlex"]
        assert p.indexer is m["indexer"]
        assert p.contextual_chunker is m["ctx_chunker"]
        assert p.doc_processor is m["doc_processor"]

    def test_eurlex_constructed_with_endpoint_and_delay(self):
        settings = make_settings()
        with (
            patch.object(pipeline_mod, "get_settings", return_value=settings),
            patch.object(pipeline_mod, "EurLexClient") as mock_eclient_cls,
            patch.object(pipeline_mod, "HybridIndexer"),
            patch.object(pipeline_mod, "ContextualChunker"),
            patch.object(pipeline_mod, "UnifiedDocumentProcessor"),
        ):
            IngestionPipeline()
        mock_eclient_cls.assert_called_once_with(endpoint="http://sparql.test", request_delay=1.5)


# --------------------------------------------------------------------------- #
# seed()
# --------------------------------------------------------------------------- #
class TestSeed:
    def _good_html(self):
        # Must exceed the 500-char content gate.
        return "<html><body>" + ("x" * 600) + "</body></html>"

    def test_happy_path_indexes_enriched_chunks(self, patched_pipeline):
        p, m = patched_pipeline
        reg = FakeReg(celex="32022L2464", framework="CSRD")
        m["eurlex"].crawl_all_core_frameworks.return_value = [reg]
        m["eurlex"].download_full_text_html.return_value = self._good_html()
        m["indexer"].index_contextual_chunks.return_value = 3

        produced = [FakeChunk("c1", {"framework": "CSRD"})] * 3
        with patch.object(pipeline_mod, "EURLexHTMLChunker") as mock_chunker_cls:
            mock_chunker_cls.return_value.chunk_html.return_value = produced
            stats = p.seed(recreate_collection=True)

        # setup_collection invoked with recreate flag passthrough.
        m["indexer"].setup_collection.assert_called_once_with(recreate=True)

        # Each chunk enriched once; indexer indexed once.
        assert m["ctx_chunker"].enrich_single.call_count == 3
        m["indexer"].index_contextual_chunks.assert_called_once()

        assert stats["action"] == "seed"
        assert stats["data_source"] == "eurlex"
        assert stats["eurlex"]["success"] == 1
        assert stats["eurlex"]["failed"] == 0
        assert stats["eurlex"]["total_chunks"] == 3
        assert stats["chunks_indexed"] == 3
        assert stats["total_downloads_success"] == 1
        assert stats["contextual_enrichment"] is True
        assert "timestamp" in stats
        assert isinstance(stats["frameworks"], list)

    def test_temporal_metadata_populated_from_reg(self, patched_pipeline):
        """effective_date set from date_document; superseded_by set when not in force."""
        p, m = patched_pipeline
        reg = FakeReg(
            celex="32022L2464",
            framework="CSRD",
            date_document="2022-12-16",
            is_in_force=False,
        )
        m["eurlex"].crawl_all_core_frameworks.return_value = [reg]
        m["eurlex"].download_full_text_html.return_value = self._good_html()
        m["indexer"].index_contextual_chunks.return_value = 1

        chunk = FakeChunk("body", {"framework": "CSRD"})
        with patch.object(pipeline_mod, "EURLexHTMLChunker") as mock_chunker_cls:
            mock_chunker_cls.return_value.chunk_html.return_value = [chunk]
            p.seed()

        assert chunk.metadata["effective_date"] == "2022-12-16"
        assert chunk.metadata["superseded_by"] == "not_in_force"

    def test_in_force_reg_not_marked_superseded(self, patched_pipeline):
        p, m = patched_pipeline
        reg = FakeReg(
            celex="32024R1689",
            framework="AI_ACT",
            date_document="2024-06-13",
            is_in_force=True,
        )
        m["eurlex"].crawl_all_core_frameworks.return_value = [reg]
        m["eurlex"].download_full_text_html.return_value = self._good_html()
        m["indexer"].index_contextual_chunks.return_value = 1

        chunk = FakeChunk("body", {"framework": "AI_ACT"})
        with patch.object(pipeline_mod, "EURLexHTMLChunker") as mock_chunker_cls:
            mock_chunker_cls.return_value.chunk_html.return_value = [chunk]
            p.seed()

        assert chunk.metadata["effective_date"] == "2024-06-13"
        assert "superseded_by" not in chunk.metadata

    def test_failed_download_counted_and_skipped(self, patched_pipeline):
        p, m = patched_pipeline
        reg = FakeReg(celex="32022L2464")
        m["eurlex"].crawl_all_core_frameworks.return_value = [reg]
        m["eurlex"].download_full_text_html.return_value = None  # download failure
        m["indexer"].index_contextual_chunks.return_value = 0

        with patch.object(pipeline_mod, "EURLexHTMLChunker") as mock_chunker_cls:
            stats = p.seed()
            # chunker never constructed because we 'continue' before chunking
            mock_chunker_cls.return_value.chunk_html.assert_not_called()

        assert stats["eurlex"]["failed"] == 1
        assert stats["eurlex"]["success"] == 0
        assert stats["eurlex"]["total_chunks"] == 0
        assert stats["total_downloads_failed"] == 1

    def test_too_short_html_counted_as_failed(self, patched_pipeline):
        p, m = patched_pipeline
        reg = FakeReg(celex="32022L2464")
        m["eurlex"].crawl_all_core_frameworks.return_value = [reg]
        m["eurlex"].download_full_text_html.return_value = "tiny"  # < 500 chars
        m["indexer"].index_contextual_chunks.return_value = 0

        with patch.object(pipeline_mod, "EURLexHTMLChunker") as mock_chunker_cls:
            stats = p.seed()
            mock_chunker_cls.return_value.chunk_html.assert_not_called()

        assert stats["eurlex"]["failed"] == 1
        assert stats["eurlex"]["success"] == 0

    def test_empty_corpus_does_not_call_indexer(self, patched_pipeline):
        """No regulations crawled -> no chunks -> indexer.index NOT called, indexed=0."""
        p, m = patched_pipeline
        m["eurlex"].crawl_all_core_frameworks.return_value = []

        stats = p.seed()

        m["indexer"].index_contextual_chunks.assert_not_called()
        assert stats["chunks_indexed"] == 0
        assert stats["total_chunks"] == 0
        assert m["ctx_chunker"].enrich_single.call_count == 0

    def test_mixed_success_and_failure_aggregation(self, patched_pipeline):
        p, m = patched_pipeline
        good = FakeReg(celex="32022L2464", framework="CSRD")
        bad = FakeReg(celex="32099X9999", framework="CSRD")
        m["eurlex"].crawl_all_core_frameworks.return_value = [good, bad]

        # First reg downloads fine, second returns None.
        m["eurlex"].download_full_text_html.side_effect = [self._good_html(), None]
        m["indexer"].index_contextual_chunks.return_value = 2

        with patch.object(pipeline_mod, "EURLexHTMLChunker") as mock_chunker_cls:
            mock_chunker_cls.return_value.chunk_html.return_value = [
                FakeChunk("a", {"framework": "CSRD"}),
                FakeChunk("b", {"framework": "CSRD"}),
            ]
            stats = p.seed()

        assert stats["eurlex"]["success"] == 1
        assert stats["eurlex"]["failed"] == 1
        assert stats["eurlex"]["total_chunks"] == 2
        assert stats["total_downloads_success"] == 1
        assert stats["total_downloads_failed"] == 1

    def test_enriched_metadata_merges_original(self, patched_pipeline):
        """ctx.metadata.update(chunk.metadata) should carry original metadata through."""
        p, m = patched_pipeline
        reg = FakeReg(celex="32022L2464", framework="CSRD")
        m["eurlex"].crawl_all_core_frameworks.return_value = [reg]
        m["eurlex"].download_full_text_html.return_value = self._good_html()
        m["indexer"].index_contextual_chunks.return_value = 1

        chunk = FakeChunk("body", {"framework": "CSRD", "article_number": "Art. 19a"})
        with patch.object(pipeline_mod, "EURLexHTMLChunker") as mock_chunker_cls:
            mock_chunker_cls.return_value.chunk_html.return_value = [chunk]
            p.seed()

        # Grab the list handed to the indexer.
        indexed_arg = m["indexer"].index_contextual_chunks.call_args.args[0]
        assert len(indexed_arg) == 1
        merged = indexed_arg[0].metadata
        # Original metadata merged on top of the enrich stub's {"enriched": True}.
        assert merged["framework"] == "CSRD"
        assert merged["article_number"] == "Art. 19a"
        assert merged["enriched"] is True

    def test_normattiva_disabled_when_source_eurlex(self, patched_pipeline):
        """data_source='eurlex' must not trigger the Normattiva branch."""
        p, m = patched_pipeline
        m["eurlex"].crawl_all_core_frameworks.return_value = []

        with patch.object(p, "seed_normattiva") as seed_norm:
            stats = p.seed()
            seed_norm.assert_not_called()
        assert stats["normattiva"]["success"] == 0
        assert stats["normattiva"]["total_chunks"] == 0


# --------------------------------------------------------------------------- #
# seed() with Normattiva enabled (seed_normattiva is patched out)
# --------------------------------------------------------------------------- #
class TestSeedNormattiva:
    def test_normattiva_branch_extends_chunks(self, patched_pipeline):
        p, m = patched_pipeline
        m["settings"].data_source = "both"
        m["eurlex"].crawl_all_core_frameworks.return_value = []
        m["indexer"].index_contextual_chunks.return_value = 5

        norm_chunks = [
            FakeChunk(f"n{i}", {"framework": "GDPR", "source": "normattiva"}) for i in range(5)
        ]
        with patch.object(p, "seed_normattiva", return_value=norm_chunks) as seed_norm:
            stats = p.seed()
            seed_norm.assert_called_once()

        # 5 normattiva chunks enriched then indexed.
        assert m["ctx_chunker"].enrich_single.call_count == 5
        assert stats["normattiva"]["total_chunks"] == 5
        assert stats["chunks_indexed"] == 5
        assert stats["data_source"] == "both"

    def test_normattiva_only_skips_eurlex_crawl(self, patched_pipeline):
        p, m = patched_pipeline
        m["settings"].data_source = "normattiva"
        m["indexer"].index_contextual_chunks.return_value = 0

        with patch.object(p, "seed_normattiva", return_value=[]) as seed_norm:
            stats = p.seed()
            seed_norm.assert_called_once()

        m["eurlex"].crawl_all_core_frameworks.assert_not_called()
        assert stats["eurlex"]["success"] == 0


# --------------------------------------------------------------------------- #
# update()
# --------------------------------------------------------------------------- #
class TestUpdate:
    def test_update_indexes_new_legislation(self, patched_pipeline):
        p, m = patched_pipeline
        m["eurlex"].check_for_new_amendments.return_value = ["a1", "a2"]
        new_reg = FakeReg(celex="32025L0794", framework="CSRD")
        m["eurlex"].fetch_recent_legislation.return_value = [new_reg]
        m["eurlex"].download_full_text_html.return_value = "<html>" + ("y" * 600) + "</html>"
        m["indexer"].index_contextual_chunks.return_value = 4

        with patch.object(pipeline_mod, "EURLexHTMLChunker") as mock_chunker_cls:
            mock_chunker_cls.return_value.chunk_html.return_value = [
                FakeChunk("u1", {"framework": "CSRD"}),
            ]
            stats = p.update(days_back=14)

        m["eurlex"].fetch_recent_legislation.assert_called_once_with(days_back=14)
        assert stats["action"] == "update"
        assert stats["amendments_found"] == 2
        assert stats["new_legislation"] == 1
        assert stats["new_chunks_indexed"] == 4
        m["indexer"].index_contextual_chunks.assert_called_once()

    def test_update_no_new_content_does_not_index(self, patched_pipeline):
        p, m = patched_pipeline
        m["eurlex"].check_for_new_amendments.return_value = []
        m["eurlex"].fetch_recent_legislation.return_value = []

        stats = p.update()

        m["indexer"].index_contextual_chunks.assert_not_called()
        assert stats["new_chunks_indexed"] == 0
        assert stats["amendments_found"] == 0
        assert stats["new_legislation"] == 0

    def test_update_skips_short_html(self, patched_pipeline):
        p, m = patched_pipeline
        m["eurlex"].check_for_new_amendments.return_value = []
        m["eurlex"].fetch_recent_legislation.return_value = [FakeReg(celex="3X")]
        m["eurlex"].download_full_text_html.return_value = "short"  # < 500

        with patch.object(pipeline_mod, "EURLexHTMLChunker") as mock_chunker_cls:
            stats = p.update()
            mock_chunker_cls.return_value.chunk_html.assert_not_called()

        m["indexer"].index_contextual_chunks.assert_not_called()
        assert stats["new_legislation"] == 1
        assert stats["new_chunks_indexed"] == 0

    def test_update_framework_fallback_unknown(self, patched_pipeline):
        """A reg with falsy framework falls back to 'UNKNOWN' for the chunker."""
        p, m = patched_pipeline
        m["eurlex"].check_for_new_amendments.return_value = []
        reg = FakeReg(celex="32025L0001", framework="")
        m["eurlex"].fetch_recent_legislation.return_value = [reg]
        m["eurlex"].download_full_text_html.return_value = "<html>" + ("z" * 600) + "</html>"
        m["indexer"].index_contextual_chunks.return_value = 1

        with patch.object(pipeline_mod, "EURLexHTMLChunker") as mock_chunker_cls:
            mock_chunker_cls.return_value.chunk_html.return_value = [FakeChunk("t", {})]
            p.update()

        # framework="" -> "UNKNOWN" in the EURLexHTMLChunker(celex=..., framework=...)
        _, kwargs = mock_chunker_cls.call_args
        assert kwargs["framework"] == "UNKNOWN"
        assert kwargs["celex"] == "32025L0001"


# --------------------------------------------------------------------------- #
# process_document()
# --------------------------------------------------------------------------- #
class TestProcessDocument:
    def test_success_indexes_with_org_id(self, patched_pipeline):
        p, m = patched_pipeline
        m["doc_processor"].process.return_value = {
            "markdown": "Some extracted regulatory text.",
            "metadata": {"processor": "docling"},
            "tables": [{"a": 1}],
        }
        m["indexer"].index_contextual_chunks.return_value = 2

        # process_document re-imports EURLexHTMLChunker from the source module,
        # so it must be patched there (not on pipeline_mod).
        with patch.object(legal_chunker_mod, "EURLexHTMLChunker") as mock_chunker_cls:
            mock_chunker_cls.return_value.chunk_html.return_value = [
                FakeChunk("c1", {"framework": "GDPR"}),
                FakeChunk("c2", {"framework": "GDPR"}),
            ]
            result = p.process_document("/tmp/report.pdf", framework="GDPR", org_id="org-123")

        assert result["status"] == "success"
        assert result["engine"] == "docling"
        assert result["framework"] == "GDPR"
        assert result["chunks_created"] == 2
        assert result["chunks_indexed"] == 2
        assert result["tables_found"] == 1
        assert result["chars_extracted"] == len("Some extracted regulatory text.")

        # org_id is forwarded to the indexer (SEC-01 tenant scoping).
        _, kwargs = m["indexer"].index_contextual_chunks.call_args
        assert kwargs["org_id"] == "org-123"

    def test_no_text_returns_error(self, patched_pipeline):
        p, m = patched_pipeline
        m["doc_processor"].process.return_value = {
            "markdown": "",
            "metadata": {"processor": "dots_ocr", "error": "boom"},
        }

        result = p.process_document("/tmp/blank.pdf")

        assert result["status"] == "error"
        assert result["engine"] == "dots_ocr"
        assert result["error"] == "boom"
        m["indexer"].index_contextual_chunks.assert_not_called()

    def test_chunking_no_results_returns_warning(self, patched_pipeline):
        p, m = patched_pipeline
        m["doc_processor"].process.return_value = {
            "markdown": "text present",
            "metadata": {"processor": "docling"},
        }

        with patch.object(legal_chunker_mod, "EURLexHTMLChunker") as mock_chunker_cls:
            mock_chunker_cls.return_value.chunk_html.return_value = []  # no chunks
            result = p.process_document("/tmp/x.pdf", framework="CSRD")

        assert result["status"] == "warning"
        assert result["engine"] == "docling"
        assert result["chars_extracted"] == len("text present")
        m["indexer"].index_contextual_chunks.assert_not_called()

    def test_default_org_id_is_none(self, patched_pipeline):
        """Without org_id the indexer receives org_id=None (the documented leak risk)."""
        p, m = patched_pipeline
        m["doc_processor"].process.return_value = {
            "markdown": "text",
            "metadata": {"processor": "docling"},
        }
        m["indexer"].index_contextual_chunks.return_value = 1

        with patch.object(legal_chunker_mod, "EURLexHTMLChunker") as mock_chunker_cls:
            mock_chunker_cls.return_value.chunk_html.return_value = [FakeChunk("c", {})]
            p.process_document("/tmp/x.pdf")

        _, kwargs = m["indexer"].index_contextual_chunks.call_args
        assert kwargs["org_id"] is None

    def test_missing_processor_metadata_defaults(self, patched_pipeline):
        p, m = patched_pipeline
        m["doc_processor"].process.return_value = {
            "markdown": "",
            "metadata": {},  # no 'processor', no 'error'
        }
        result = p.process_document("/tmp/x.pdf")
        assert result["status"] == "error"
        assert result["engine"] == "none"
        assert result["error"] == "Unknown"


# --------------------------------------------------------------------------- #
# stats()
# --------------------------------------------------------------------------- #
class TestStats:
    def test_stats_healthy(self, patched_pipeline):
        p, m = patched_pipeline
        m["indexer"].get_collection_stats.return_value = {"points": 1234}

        result = p.stats()

        assert result["qdrant"] == {"points": 1234}
        assert isinstance(result["tracked_frameworks"], list)
        assert result["tracked_regulations"] >= 1
        # tracked_regulations is the total count across all frameworks.
        assert result["tracked_regulations"] == sum(
            len(v) for v in pipeline_mod.CORE_FRAMEWORKS.values()
        )

    def test_stats_indexer_unavailable(self, patched_pipeline):
        p, m = patched_pipeline
        m["indexer"].get_collection_stats.side_effect = RuntimeError("qdrant down")

        result = p.stats()

        assert result["qdrant"] == {"status": "unavailable"}
        # Framework counts still reported even when Qdrant is unreachable.
        assert result["tracked_regulations"] >= 1


# --------------------------------------------------------------------------- #
# close()
# --------------------------------------------------------------------------- #
class TestClose:
    def test_close_delegates_to_eurlex(self, patched_pipeline):
        p, m = patched_pipeline
        p.close()
        m["eurlex"].close.assert_called_once()


# --------------------------------------------------------------------------- #
# main() CLI dispatch
# --------------------------------------------------------------------------- #
class TestMainDispatch:
    def _run_main(self, argv):
        """Patch IngestionPipeline so main() drives a stub, and run with argv."""
        fake_pipeline = MagicMock(name="IngestionPipeline-instance")
        fake_pipeline.seed.return_value = {"action": "seed"}
        fake_pipeline.update.return_value = {"action": "update"}
        fake_pipeline.stats.return_value = {"action": "stats"}
        with (
            patch.object(pipeline_mod, "IngestionPipeline", return_value=fake_pipeline),
            patch.object(sys, "argv", argv),
        ):
            pipeline_mod.main()
        return fake_pipeline

    def test_main_seed_dispatch(self):
        fp = self._run_main(["pipeline", "--action", "seed", "--recreate"])
        fp.seed.assert_called_once_with(recreate_collection=True)
        fp.update.assert_not_called()
        fp.close.assert_called_once()

    def test_main_seed_without_recreate(self):
        fp = self._run_main(["pipeline", "--action", "seed"])
        fp.seed.assert_called_once_with(recreate_collection=False)

    def test_main_update_dispatch(self):
        fp = self._run_main(["pipeline", "--action", "update", "--days-back", "30"])
        fp.update.assert_called_once_with(days_back=30)
        fp.seed.assert_not_called()
        fp.close.assert_called_once()

    def test_main_update_default_days_back(self):
        fp = self._run_main(["pipeline", "--action", "update"])
        fp.update.assert_called_once_with(days_back=7)

    def test_main_stats_dispatch(self):
        fp = self._run_main(["pipeline", "--action", "stats"])
        fp.stats.assert_called_once_with()
        fp.close.assert_called_once()

    def test_main_closes_even_on_action_error(self):
        """The finally: block must call close() even if the action raises."""
        fake_pipeline = MagicMock()
        fake_pipeline.seed.side_effect = RuntimeError("seed exploded")
        with (
            patch.object(pipeline_mod, "IngestionPipeline", return_value=fake_pipeline),
            patch.object(sys, "argv", ["pipeline", "--action", "seed"]),
            pytest.raises(RuntimeError, match="seed exploded"),
        ):
            pipeline_mod.main()
        fake_pipeline.close.assert_called_once()

    def test_main_requires_action(self):
        with (
            patch.object(pipeline_mod, "IngestionPipeline"),
            patch.object(sys, "argv", ["pipeline"]),
            pytest.raises(SystemExit),
        ):
            pipeline_mod.main()

    def test_main_rejects_invalid_action(self):
        with (
            patch.object(pipeline_mod, "IngestionPipeline"),
            patch.object(sys, "argv", ["pipeline", "--action", "bogus"]),
            pytest.raises(SystemExit),
        ):
            pipeline_mod.main()
