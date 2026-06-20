"""Tests for the background acquisition scheduler.

``AcquisitionScheduler`` is a self-contained asyncio scheduler with no DB
dependency. With ``None`` clients every acquisition path takes its no-op
early-return branch, so these tests exercise the lifecycle and stats surface
without any network/LLM/DB access. asyncio_mode is "auto" in this repo, so bare
``async def test_...`` functions run on the event loop.
"""

import asyncio
from unittest.mock import MagicMock, patch

from src.crawler.scheduler import AcquisitionScheduler


# --------------------------------------------------------------------------- #
# __init__ defaults
# --------------------------------------------------------------------------- #
class TestInit:
    def test_defaults(self):
        sched = AcquisitionScheduler()
        assert sched.normattiva is None
        assert sched.eurlex is None
        assert sched.interval_hours == 6
        assert sched.initial_delay_seconds == 30
        assert sched._task is None
        assert sched._running is False
        assert sched._last_run is None
        assert sched._cycle_count == 0
        assert sched._error_count == 0

    def test_custom_params(self):
        normattiva = MagicMock()
        eurlex = MagicMock()
        sched = AcquisitionScheduler(
            normattiva_client=normattiva,
            eurlex_client=eurlex,
            interval_hours=12,
            initial_delay_seconds=0,
        )
        assert sched.normattiva is normattiva
        assert sched.eurlex is eurlex
        assert sched.interval_hours == 12
        assert sched.initial_delay_seconds == 0


# --------------------------------------------------------------------------- #
# get_stats() shape
# --------------------------------------------------------------------------- #
class TestGetStats:
    def test_initial_stats_shape(self):
        sched = AcquisitionScheduler(interval_hours=8)
        stats = sched.get_stats()
        assert stats == {
            "running": False,
            "cycle_count": 0,
            "error_count": 0,
            "last_run": None,
            "interval_hours": 8,
        }

    def test_stats_reflect_internal_counters(self):
        sched = AcquisitionScheduler()
        # Simulate a couple of completed cycles + one error.
        sched._running = True
        sched._cycle_count = 3
        sched._error_count = 1
        stats = sched.get_stats()
        assert stats["running"] is True
        assert stats["cycle_count"] == 3
        assert stats["error_count"] == 1
        # last_run still None -> serialized as None, not an exception.
        assert stats["last_run"] is None

    async def test_last_run_serialized_after_cycle(self):
        # _run_cycle sets _last_run to a datetime; get_stats must isoformat it.
        sched = AcquisitionScheduler()
        await sched._run_cycle()
        stats = sched.get_stats()
        assert isinstance(stats["last_run"], str)
        # isoformat strings contain a 'T' separator.
        assert "T" in stats["last_run"]


# --------------------------------------------------------------------------- #
# start()/stop() lifecycle
# --------------------------------------------------------------------------- #
class TestLifecycle:
    async def test_start_sets_running_and_creates_task(self):
        # Large initial delay so the background loop parks in sleep and never
        # runs a cycle during the test; we only assert the started state.
        sched = AcquisitionScheduler(initial_delay_seconds=1000)
        await sched.start()
        try:
            assert sched._running is True
            assert sched._task is not None
            assert isinstance(sched._task, asyncio.Task)
            assert not sched._task.done()
        finally:
            await sched.stop()

    async def test_stop_drains_task_and_clears_running(self):
        sched = AcquisitionScheduler(initial_delay_seconds=1000)
        await sched.start()
        task = sched._task
        await sched.stop()
        assert sched._running is False
        # stop() awaited the task to completion (it was cancelled out of sleep).
        assert task.done()

    async def test_start_is_idempotent(self):
        sched = AcquisitionScheduler(initial_delay_seconds=1000)
        await sched.start()
        try:
            first_task = sched._task
            # Second start() should warn and NOT replace the running task.
            await sched.start()
            assert sched._task is first_task
        finally:
            await sched.stop()

    async def test_stop_without_start_is_noop(self):
        sched = AcquisitionScheduler()
        # Never started: _running is False, stop() returns immediately.
        await sched.stop()
        assert sched._running is False
        assert sched._task is None

    async def test_stop_cancels_task_blocked_in_initial_delay(self):
        # The loop is parked in `await asyncio.sleep(initial_delay_seconds)`.
        # stop() flips _running False, then wait_for(timeout=10) succeeds because
        # cancellation propagates; assert no exception escapes and task is done.
        sched = AcquisitionScheduler(initial_delay_seconds=1000)
        await sched.start()
        # Yield control so the background loop actually enters the sleep.
        await asyncio.sleep(0)
        await sched.stop()
        assert sched._task.done()
        # Cancellation inside _background_loop is swallowed -> no exception.
        assert sched._task.exception() is None

    async def test_full_cycle_runs_with_zero_delay(self):
        # With None clients a cycle is a fast no-op. Use initial_delay 0 so the
        # loop runs at least one cycle, then stop it before the long interval
        # sleep matters (interval sleep is cancelled by stop()).
        sched = AcquisitionScheduler(initial_delay_seconds=0, interval_hours=6)
        await sched.start()
        # Give the loop event-loop turns to complete one no-op cycle.
        for _ in range(50):
            if sched._cycle_count >= 1:
                break
            await asyncio.sleep(0)
        await sched.stop()
        assert sched._cycle_count >= 1
        assert sched._error_count == 0
        # A completed cycle stamps _last_run.
        assert sched._last_run is not None


# --------------------------------------------------------------------------- #
# run_once() with None clients
# --------------------------------------------------------------------------- #
class TestRunOnceNoneClients:
    async def test_run_once_all(self):
        sched = AcquisitionScheduler()
        stats = await sched.run_once("all")
        assert stats["source"] == "all"
        assert "timestamp" in stats
        assert stats["eurlex"] == {"regulations_found": 0, "chunks_indexed": 0}
        assert stats["normattiva"] == {"regulations_found": 0, "chunks_indexed": 0}

    async def test_run_once_default_is_all(self):
        sched = AcquisitionScheduler()
        stats = await sched.run_once()  # default source="all"
        assert stats["source"] == "all"
        assert "eurlex" in stats
        assert "normattiva" in stats

    async def test_run_once_eurlex_only(self):
        sched = AcquisitionScheduler()
        stats = await sched.run_once("eurlex")
        assert stats["source"] == "eurlex"
        assert stats["eurlex"] == {"regulations_found": 0, "chunks_indexed": 0}
        # normattiva branch not taken -> key absent.
        assert "normattiva" not in stats

    async def test_run_once_normattiva_only(self):
        sched = AcquisitionScheduler()
        stats = await sched.run_once("normattiva")
        assert stats["source"] == "normattiva"
        assert stats["normattiva"] == {"regulations_found": 0, "chunks_indexed": 0}
        assert "eurlex" not in stats

    async def test_run_once_unknown_source_no_branches(self):
        # An unrecognized source matches neither ("all","eurlex") nor
        # ("all","normattiva"); the result carries only timestamp + source.
        sched = AcquisitionScheduler()
        stats = await sched.run_once("garbage")
        assert stats["source"] == "garbage"
        assert "timestamp" in stats
        assert "eurlex" not in stats
        assert "normattiva" not in stats


# --------------------------------------------------------------------------- #
# _run_cycle() with None clients
# --------------------------------------------------------------------------- #
class TestRunCycleNoneClients:
    async def test_run_cycle_zero_counts(self):
        sched = AcquisitionScheduler()
        stats = await sched._run_cycle()
        # cycle index is _cycle_count + 1 (1-based for display).
        assert stats["cycle"] == 1
        assert stats["eurlex"] == {"regulations_found": 0, "chunks_indexed": 0}
        assert stats["normattiva"] == {"regulations_found": 0, "chunks_indexed": 0}
        assert "timestamp" in stats
        assert "elapsed_seconds" in stats
        assert stats["elapsed_seconds"] >= 0.0

    async def test_run_cycle_sets_last_run(self):
        sched = AcquisitionScheduler()
        assert sched._last_run is None
        await sched._run_cycle()
        assert sched._last_run is not None

    async def test_run_cycle_does_not_increment_cycle_count_itself(self):
        # _run_cycle reports cycle = _cycle_count + 1 but does NOT mutate the
        # counter; the background loop is what increments _cycle_count.
        sched = AcquisitionScheduler()
        await sched._run_cycle()
        assert sched._cycle_count == 0
        stats = await sched._run_cycle()
        assert stats["cycle"] == 1  # still 1, counter untouched


# --------------------------------------------------------------------------- #
# _acquire_eurlex() / _acquire_normattiva()
# --------------------------------------------------------------------------- #
class TestAcquireEurlex:
    async def test_none_client_early_return(self):
        sched = AcquisitionScheduler()  # eurlex is None
        result = await sched._acquire_eurlex()
        assert result == {"regulations_found": 0, "chunks_indexed": 0}

    async def test_empty_client_no_regulations(self):
        # MagicMock client whose query methods return [] -> no downloads, no
        # indexing. Avoids touching the real HybridIndexer / chunkers (the
        # in-force refresh is stubbed so it neither builds a real indexer nor
        # hits Qdrant).
        client = MagicMock()
        client.check_for_new_amendments.return_value = []
        client.fetch_recent_legislation.return_value = []
        sched = AcquisitionScheduler(eurlex_client=client)

        with (
            patch("src.nlp.embedding.indexer.HybridIndexer"),
            patch(
                "src.pipeline.refresh_in_force_status",
                return_value={
                    "checked": 0,
                    "superseded_regulations": 0,
                    "superseded_chunks": 0,
                },
            ),
        ):
            result = await sched._acquire_eurlex()

        assert result == {
            "regulations_found": 0,
            "amendments_found": 0,
            "superseded_chunks": 0,
            "chunks_indexed": 0,
        }
        # The client was actually consulted with the CORE_FRAMEWORKS celex list.
        client.check_for_new_amendments.assert_called_once()
        called_arg = client.check_for_new_amendments.call_args.args[0]
        assert isinstance(called_arg, list)
        assert len(called_arg) > 0  # CORE_FRAMEWORKS is non-empty
        client.fetch_recent_legislation.assert_called_once_with(days_back=1)
        # No legislation -> download_full_text_html never called.
        client.download_full_text_html.assert_not_called()

    async def test_amendments_counted_but_no_legislation(self):
        # Amendments present but zero new legislation -> still no chunks/indexing.
        client = MagicMock()
        client.check_for_new_amendments.return_value = [object(), object()]
        client.fetch_recent_legislation.return_value = []
        sched = AcquisitionScheduler(eurlex_client=client)

        with (
            patch("src.nlp.embedding.indexer.HybridIndexer"),
            patch(
                "src.pipeline.refresh_in_force_status",
                return_value={
                    "checked": 0,
                    "superseded_regulations": 0,
                    "superseded_chunks": 0,
                },
            ),
        ):
            result = await sched._acquire_eurlex()

        assert result["regulations_found"] == 0
        assert result["amendments_found"] == 2
        assert result["chunks_indexed"] == 0
        client.download_full_text_html.assert_not_called()

    async def test_superseded_chunks_surfaced_from_refresh(self):
        # The in-force refresh result is surfaced in the cycle stats.
        client = MagicMock()
        client.check_for_new_amendments.return_value = []
        client.fetch_recent_legislation.return_value = []
        sched = AcquisitionScheduler(eurlex_client=client)

        with (
            patch("src.nlp.embedding.indexer.HybridIndexer"),
            patch(
                "src.pipeline.refresh_in_force_status",
                return_value={
                    "checked": 8,
                    "superseded_regulations": 1,
                    "superseded_chunks": 12,
                },
            ) as mock_refresh,
        ):
            result = await sched._acquire_eurlex()

        assert result["superseded_chunks"] == 12
        mock_refresh.assert_called_once()

    async def test_client_raising_is_caught_and_reported(self):
        # The broad try/except wraps the whole body; an exploding client method
        # yields the error fallback dict rather than propagating.
        client = MagicMock()
        client.check_for_new_amendments.side_effect = RuntimeError("sparql down")
        sched = AcquisitionScheduler(eurlex_client=client)

        result = await sched._acquire_eurlex()

        assert result["regulations_found"] == 0
        assert result["chunks_indexed"] == 0
        assert "error" in result
        assert "sparql down" in result["error"]


class TestAcquireNormattiva:
    async def test_none_client_early_return(self):
        sched = AcquisitionScheduler()  # normattiva is None
        result = await sched._acquire_normattiva()
        assert result == {"regulations_found": 0, "chunks_indexed": 0}

    async def test_empty_client_no_regulations(self):
        client = MagicMock()
        client.fetch_recent_publications.return_value = []
        sched = AcquisitionScheduler(normattiva_client=client)

        result = await sched._acquire_normattiva()

        assert result == {"regulations_found": 0, "chunks_indexed": 0}
        client.fetch_recent_publications.assert_called_once_with(days_back=1)
        client.download_full_text_html.assert_not_called()

    async def test_client_raising_is_caught_and_reported(self):
        client = MagicMock()
        client.fetch_recent_publications.side_effect = ValueError("boom")
        sched = AcquisitionScheduler(normattiva_client=client)

        result = await sched._acquire_normattiva()

        assert result["regulations_found"] == 0
        assert result["chunks_indexed"] == 0
        assert "error" in result
        assert "boom" in result["error"]


# --------------------------------------------------------------------------- #
# run_once() wiring with mock clients
# --------------------------------------------------------------------------- #
class TestRunOnceWithMockClients:
    async def test_run_once_all_with_empty_clients(self):
        eurlex = MagicMock()
        eurlex.check_for_new_amendments.return_value = []
        eurlex.fetch_recent_legislation.return_value = []
        normattiva = MagicMock()
        normattiva.fetch_recent_publications.return_value = []

        sched = AcquisitionScheduler(normattiva_client=normattiva, eurlex_client=eurlex)
        stats = await sched.run_once("all")

        assert stats["source"] == "all"
        assert stats["eurlex"]["regulations_found"] == 0
        assert stats["eurlex"]["chunks_indexed"] == 0
        assert stats["normattiva"]["regulations_found"] == 0
        assert stats["normattiva"]["chunks_indexed"] == 0
        # 'all' triggers both sources.
        eurlex.fetch_recent_legislation.assert_called_once()
        normattiva.fetch_recent_publications.assert_called_once()

    async def test_run_once_eurlex_skips_normattiva_client(self):
        eurlex = MagicMock()
        eurlex.check_for_new_amendments.return_value = []
        eurlex.fetch_recent_legislation.return_value = []
        normattiva = MagicMock()
        normattiva.fetch_recent_publications.return_value = []

        sched = AcquisitionScheduler(normattiva_client=normattiva, eurlex_client=eurlex)
        stats = await sched.run_once("eurlex")

        assert "normattiva" not in stats
        # normattiva client must not have been touched for an eurlex-only run.
        normattiva.fetch_recent_publications.assert_not_called()
        eurlex.fetch_recent_legislation.assert_called_once()
