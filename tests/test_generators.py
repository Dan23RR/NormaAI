"""Unit tests for the SSE event generators (src/api/streaming/generators.py).

The three generators (``qa_stream_generator`` / ``gap_analysis_stream_generator``
/ ``monitor_stream_generator``) drive the Intelligence streaming endpoints. Each
one:

1. emits a ``PhaseChangeEvent(phase="draft")``
2. calls the real agent graph (``arun_qa`` / ``arun_gap_analysis`` /
   ``arun_monitor_check``)
3. chunks the answer/summary into ``TokenEvent``s (80-char chunks)
4. (qa only) emits ``CitationEvent``s
5. optionally runs the CoVe orchestrator (which emits its own ``DoneEvent`` and
   the generator ``return``s early), otherwise emits a final ``DoneEvent``
6. on any exception, emits a single non-recoverable ``ErrorEvent``

Every external dependency is mocked. The agent graph functions and the CoVe
orchestrator are imported *function-locally* inside generators.py, so they are
patched at their *source* modules (``src.agents.graph.arun_qa`` and
``src.agents.cove.orchestrator.CoVeOrchestrator``). No real network / LLM / DB /
model is ever touched.

asyncio_mode = "auto" (configured in pyproject.toml), so plain ``async def``
test methods run without an explicit marker.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.streaming.generators import (
    gap_analysis_stream_generator,
    monitor_stream_generator,
    qa_stream_generator,
)
from src.api.streaming.sse import (
    CitationEvent,
    DoneEvent,
    ErrorEvent,
    PhaseChangeEvent,
    TokenEvent,
)

# Patch targets (the names live in the *source* modules because generators.py
# imports them lazily inside each function body).
GRAPH_QA = "src.agents.graph.arun_qa"
GRAPH_GAP = "src.agents.graph.arun_gap_analysis"
GRAPH_MONITOR = "src.agents.graph.arun_monitor_check"
COVE_ORCH = "src.agents.cove.orchestrator.CoVeOrchestrator"


# ------------------------------------------------------------------ #
#  helpers                                                            #
# ------------------------------------------------------------------ #


def _fake_user(org_id: uuid.UUID | None = None):
    """A lightweight CurrentUser stand-in exposing only ``.org_id``."""
    user = MagicMock()
    user.org_id = org_id or uuid.uuid4()
    return user


async def _collect(agen):
    """Drain an async generator into a list of events."""
    return [event async for event in agen]


def _patch_cove(events):
    """Patch CoVeOrchestrator so its ``.run()`` async-generator yields ``events``.

    The orchestrator is constructed inside the generator as
    ``CoVeOrchestrator(indexer=..., config=...)`` and then driven via
    ``async for event in orchestrator.run(draft_state, task_type)``.
    """

    async def _run(*_args, **_kwargs):
        for ev in events:
            yield ev

    instance = MagicMock()
    instance.run = _run
    cls = MagicMock(return_value=instance)
    return patch(COVE_ORCH, cls), cls


# ------------------------------------------------------------------ #
#  qa_stream_generator - happy path                                  #
# ------------------------------------------------------------------ #


class TestQaStreamHappyPath:
    async def test_event_sequence_phase_tokens_citation_done(self):
        # Answer long enough to span two 80-char chunks.
        answer = "A" * 100
        result = {
            "answer": answer,
            "citations": [
                {
                    "celex": "32022L2464",
                    "reference": "Art. 19a",
                    "title": "CSRD",
                    "url": "https://eur-lex.europa.eu/eli/32022L2464",
                }
            ],
            "confidence_score": 0.91,
            "requires_expert_review": False,
        }
        org = uuid.uuid4()
        with patch(GRAPH_QA, AsyncMock(return_value=result)) as arun:
            events = await _collect(
                qa_stream_generator(
                    "Who reports under CSRD?",
                    {"sector": "mfg"},
                    _fake_user(org_id=org),
                    enable_cove=False,
                )
            )

        # First event is always the draft PhaseChange.
        assert isinstance(events[0], PhaseChangeEvent)
        assert events[0].phase == "draft"

        # Tokens: 100 chars / 80 -> two chunks, indices 0 and 1.
        tokens = [e for e in events if isinstance(e, TokenEvent)]
        assert len(tokens) == 2
        assert tokens[0].index == 0 and tokens[1].index == 1
        assert tokens[0].content == "A" * 80
        assert tokens[1].content == "A" * 20
        # Reassembled tokens reproduce the original answer.
        assert "".join(t.content for t in tokens) == answer

        # Exactly one citation, mapped from the result dict.
        citations = [e for e in events if isinstance(e, CitationEvent)]
        assert len(citations) == 1
        assert citations[0].celex == "32022L2464"
        assert citations[0].article == "Art. 19a"
        assert citations[0].title == "CSRD"
        assert citations[0].verified is False

        # Final DoneEvent, no CoVe.
        done = [e for e in events if isinstance(e, DoneEvent)]
        assert len(done) == 1
        assert done[0].cove_applied is False
        assert done[0].confidence_score == pytest.approx(0.91)
        assert done[0].requires_review is False
        # total_tokens = word count of the answer (one "word" of 100 'A's).
        assert done[0].total_tokens == len(answer.split())

        # No error.
        assert not [e for e in events if isinstance(e, ErrorEvent)]

        # org_id is forwarded to the agent as the stringified user's org_id.
        arun.assert_awaited_once()
        assert arun.await_args.kwargs["org_id"] == str(org)
        assert arun.await_args.kwargs["cove_enabled"] is False

    async def test_org_id_passed_as_string(self):
        org = uuid.uuid4()
        result = {"answer": "short", "citations": [], "confidence_score": 0.8}
        with patch(GRAPH_QA, AsyncMock(return_value=result)) as arun:
            await _collect(
                qa_stream_generator("q", None, _fake_user(org_id=org), enable_cove=False)
            )
        # First positional arg is the question; org_id is keyword and stringified.
        assert arun.await_args.kwargs["org_id"] == str(org)
        assert isinstance(arun.await_args.kwargs["org_id"], str)

    async def test_question_and_profile_forwarded(self):
        result = {"answer": "x", "citations": [], "confidence_score": 0.7}
        profile = {"sector": "finance"}
        with patch(GRAPH_QA, AsyncMock(return_value=result)) as arun:
            await _collect(
                qa_stream_generator("my question", profile, _fake_user(), enable_cove=False)
            )
        assert arun.await_args.args[0] == "my question"
        assert arun.await_args.args[1] == profile

    async def test_short_answer_single_chunk(self):
        result = {"answer": "tiny", "citations": [], "confidence_score": 0.5}
        with patch(GRAPH_QA, AsyncMock(return_value=result)):
            events = await _collect(qa_stream_generator("q", None, _fake_user(), enable_cove=False))
        tokens = [e for e in events if isinstance(e, TokenEvent)]
        assert len(tokens) == 1
        assert tokens[0].content == "tiny"
        assert tokens[0].index == 0

    async def test_empty_answer_emits_no_token_events(self):
        result = {"answer": "", "citations": [], "confidence_score": 0.6}
        with patch(GRAPH_QA, AsyncMock(return_value=result)):
            events = await _collect(qa_stream_generator("q", None, _fake_user(), enable_cove=False))
        assert not [e for e in events if isinstance(e, TokenEvent)]
        done = [e for e in events if isinstance(e, DoneEvent)][0]
        # Empty string -> 0 words.
        assert done.total_tokens == 0

    async def test_answer_falls_back_to_raw_response(self):
        # No "answer" key -> falls back to "raw_response".
        result = {"raw_response": "fallback text", "citations": [], "confidence_score": 0.6}
        with patch(GRAPH_QA, AsyncMock(return_value=result)):
            events = await _collect(qa_stream_generator("q", None, _fake_user(), enable_cove=False))
        tokens = [e for e in events if isinstance(e, TokenEvent)]
        assert "".join(t.content for t in tokens) == "fallback text"

    async def test_non_string_answer_yields_no_tokens_and_zero_total(self):
        # answer is a dict (neither "answer" nor "raw_response" -> str(result)
        # would be used, but here we force a non-str under "answer").
        result = {"answer": {"nested": "obj"}, "citations": [], "confidence_score": 0.6}
        with patch(GRAPH_QA, AsyncMock(return_value=result)):
            events = await _collect(qa_stream_generator("q", None, _fake_user(), enable_cove=False))
        assert not [e for e in events if isinstance(e, TokenEvent)]
        done = [e for e in events if isinstance(e, DoneEvent)][0]
        assert done.total_tokens == 0

    async def test_default_confidence_when_falsy(self):
        # confidence_score is 0 (falsy) -> code substitutes the 0.85 default.
        result = {"answer": "hi", "citations": [], "confidence_score": 0}
        with patch(GRAPH_QA, AsyncMock(return_value=result)):
            events = await _collect(qa_stream_generator("q", None, _fake_user(), enable_cove=False))
        done = [e for e in events if isinstance(e, DoneEvent)][0]
        assert done.confidence_score == pytest.approx(0.85)

    async def test_missing_confidence_uses_default(self):
        result = {"answer": "hi", "citations": []}
        with patch(GRAPH_QA, AsyncMock(return_value=result)):
            events = await _collect(qa_stream_generator("q", None, _fake_user(), enable_cove=False))
        done = [e for e in events if isinstance(e, DoneEvent)][0]
        assert done.confidence_score == pytest.approx(0.85)


# ------------------------------------------------------------------ #
#  qa_stream_generator - citation mapping edge cases                 #
# ------------------------------------------------------------------ #


class TestQaCitationMapping:
    async def test_celex_falls_back_to_reference(self):
        # No "celex" key -> uses "reference".
        result = {
            "answer": "x",
            "citations": [{"reference": "REF-123", "title": "Doc"}],
            "confidence_score": 0.7,
        }
        with patch(GRAPH_QA, AsyncMock(return_value=result)):
            events = await _collect(qa_stream_generator("q", None, _fake_user(), enable_cove=False))
        cit = [e for e in events if isinstance(e, CitationEvent)][0]
        # celex falls back to reference; article also reads "reference".
        assert cit.celex == "REF-123"
        assert cit.article == "REF-123"

    async def test_url_default_built_from_celex(self):
        result = {
            "answer": "x",
            "citations": [{"celex": "32024R1689"}],
            "confidence_score": 0.7,
        }
        with patch(GRAPH_QA, AsyncMock(return_value=result)):
            events = await _collect(qa_stream_generator("q", None, _fake_user(), enable_cove=False))
        cit = [e for e in events if isinstance(e, CitationEvent)][0]
        assert cit.url == "https://eur-lex.europa.eu/eli/32024R1689"

    async def test_urn_preserved(self):
        result = {
            "answer": "x",
            "citations": [{"celex": "32022L2464", "urn": "urn:nir:stato:legge:2024;1"}],
            "confidence_score": 0.7,
        }
        with patch(GRAPH_QA, AsyncMock(return_value=result)):
            events = await _collect(qa_stream_generator("q", None, _fake_user(), enable_cove=False))
        cit = [e for e in events if isinstance(e, CitationEvent)][0]
        assert cit.urn == "urn:nir:stato:legge:2024;1"

    async def test_title_falls_back_to_framework(self):
        result = {
            "answer": "x",
            "citations": [{"celex": "32022L2464", "framework": "CSRD"}],
            "confidence_score": 0.7,
        }
        with patch(GRAPH_QA, AsyncMock(return_value=result)):
            events = await _collect(qa_stream_generator("q", None, _fake_user(), enable_cove=False))
        cit = [e for e in events if isinstance(e, CitationEvent)][0]
        assert cit.title == "CSRD"

    async def test_malformed_citation_is_skipped_not_fatal(self):
        # A citation that is not a dict triggers the per-citation
        # try/except (cit.get -> AttributeError) and is silently skipped;
        # the well-formed one survives.
        result = {
            "answer": "x",
            "citations": ["not-a-dict", {"celex": "32022L2464"}],
            "confidence_score": 0.7,
        }
        with patch(GRAPH_QA, AsyncMock(return_value=result)):
            events = await _collect(qa_stream_generator("q", None, _fake_user(), enable_cove=False))
        citations = [e for e in events if isinstance(e, CitationEvent)]
        assert len(citations) == 1
        assert citations[0].celex == "32022L2464"
        # The stream still completes normally.
        assert any(isinstance(e, DoneEvent) for e in events)

    async def test_no_citations_means_no_citation_events(self):
        result = {"answer": "x", "citations": [], "confidence_score": 0.7}
        with patch(GRAPH_QA, AsyncMock(return_value=result)):
            events = await _collect(qa_stream_generator("q", None, _fake_user(), enable_cove=False))
        assert not [e for e in events if isinstance(e, CitationEvent)]


# ------------------------------------------------------------------ #
#  qa_stream_generator - CoVe enabled path                           #
# ------------------------------------------------------------------ #


class TestQaCoveEnabled:
    async def test_cove_events_passthrough_and_own_done(self):
        # When CoVe is enabled and succeeds, the generator yields the draft
        # phase + tokens, then forwards every CoVe event, then RETURNS - so
        # the orchestrator's own DoneEvent is the only DoneEvent and the
        # generator does NOT emit its own.
        cove_done = DoneEvent(
            total_tokens=5,
            confidence_score=0.97,
            requires_review=False,
            cove_applied=True,
            revised_text="VERIFIED answer.",
        )
        cove_events = [
            PhaseChangeEvent(phase="planning", message="planning..."),
            PhaseChangeEvent(phase="verification", message="verifying..."),
            cove_done,
        ]
        result = {"answer": "draft answer", "citations": [], "confidence_score": 0.5}

        cove_patch, cls = _patch_cove(cove_events)
        with patch(GRAPH_QA, AsyncMock(return_value=result)), cove_patch:
            events = await _collect(
                qa_stream_generator("q", {"sector": "x"}, _fake_user(), enable_cove=True)
            )

        # CoVe phases are forwarded.
        phases = [e.phase for e in events if isinstance(e, PhaseChangeEvent)]
        assert phases == ["draft", "planning", "verification"]

        # Exactly one DoneEvent - the CoVe-emitted one - carrying revised_text.
        done = [e for e in events if isinstance(e, DoneEvent)]
        assert len(done) == 1
        assert done[0] is cove_done
        assert done[0].cove_applied is True
        assert done[0].revised_text == "VERIFIED answer."

        # Orchestrator was constructed with config enabled=True.
        cls.assert_called_once()
        config = cls.call_args.kwargs["config"]
        assert config.enabled is True

    async def test_cove_enabled_forwarded_to_agent(self):
        result = {"answer": "x", "citations": [], "confidence_score": 0.5}
        cove_patch, _cls = _patch_cove(
            [
                DoneEvent(
                    total_tokens=1, confidence_score=0.9, requires_review=False, cove_applied=True
                )
            ]
        )
        with patch(GRAPH_QA, AsyncMock(return_value=result)) as arun, cove_patch:
            await _collect(qa_stream_generator("q", None, _fake_user(), enable_cove=True))
        assert arun.await_args.kwargs["cove_enabled"] is True

    async def test_cove_failure_falls_back_to_normal_done(self):
        # If the CoVe block raises, it is caught/logged and the generator
        # falls through to emit its OWN final DoneEvent with cove_applied=True.
        result = {"answer": "draft", "citations": [], "confidence_score": 0.66}

        with (
            patch(GRAPH_QA, AsyncMock(return_value=result)),
            patch(COVE_ORCH, side_effect=RuntimeError("cove construction failed")),
        ):
            events = await _collect(qa_stream_generator("q", None, _fake_user(), enable_cove=True))

        done = [e for e in events if isinstance(e, DoneEvent)]
        assert len(done) == 1
        # cove_applied reflects the *request* flag even on fallback.
        assert done[0].cove_applied is True
        assert done[0].confidence_score == pytest.approx(0.66)
        # No fatal ErrorEvent - the fallback is graceful.
        assert not [e for e in events if isinstance(e, ErrorEvent)]
        # Draft tokens were still emitted before the fallback.
        assert [e for e in events if isinstance(e, TokenEvent)]


# ------------------------------------------------------------------ #
#  qa_stream_generator - error handling                              #
# ------------------------------------------------------------------ #


class TestQaErrorHandling:
    async def test_agent_exception_emits_single_error_event(self):
        with patch(GRAPH_QA, AsyncMock(side_effect=RuntimeError("graph exploded"))):
            events = await _collect(qa_stream_generator("q", None, _fake_user(), enable_cove=False))
        # The draft phase was emitted before the failure.
        assert any(isinstance(e, PhaseChangeEvent) for e in events)
        errors = [e for e in events if isinstance(e, ErrorEvent)]
        assert len(errors) == 1
        assert errors[0].recoverable is False
        assert "graph exploded" in errors[0].message
        # No DoneEvent on a fatal failure.
        assert not [e for e in events if isinstance(e, DoneEvent)]

    async def test_import_error_path_is_caught(self):
        # Force the lazy ``from src.agents.graph import arun_qa`` to fail.
        import builtins

        real_import = builtins.__import__

        def boom(name, *args, **kwargs):
            if name == "src.agents.graph":
                raise ImportError("no graph here")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=boom):
            events = await _collect(qa_stream_generator("q", None, _fake_user(), enable_cove=False))
        errors = [e for e in events if isinstance(e, ErrorEvent)]
        assert len(errors) == 1
        assert errors[0].recoverable is False


# ------------------------------------------------------------------ #
#  gap_analysis_stream_generator                                     #
# ------------------------------------------------------------------ #


class TestGapAnalysisStream:
    async def test_happy_path_phase_tokens_done(self):
        summary = "S" * 90  # two 80-char chunks
        result = {
            "summary": summary,
            "confidence_score": 0.82,
            "requires_expert_review": True,
        }
        with patch(GRAPH_GAP, AsyncMock(return_value=result)) as arun:
            events = await _collect(
                gap_analysis_stream_generator(
                    "CSRD", {"sector": "x"}, _fake_user(), enable_cove=False
                )
            )

        assert isinstance(events[0], PhaseChangeEvent)
        assert events[0].phase == "draft"
        # The draft message embeds the framework name.
        assert "CSRD" in events[0].message

        tokens = [e for e in events if isinstance(e, TokenEvent)]
        assert "".join(t.content for t in tokens) == summary

        # Gap analysis emits NO citation events.
        assert not [e for e in events if isinstance(e, CitationEvent)]

        done = [e for e in events if isinstance(e, DoneEvent)][0]
        assert done.cove_applied is False
        assert done.confidence_score == pytest.approx(0.82)
        assert done.requires_review is True

        # framework forwarded positionally, org_id stringified.
        assert arun.await_args.args[0] == "CSRD"
        assert isinstance(arun.await_args.kwargs["org_id"], str)

    async def test_summary_falls_back_to_answer(self):
        result = {"answer": "answer-as-summary", "confidence_score": 0.7}
        with patch(GRAPH_GAP, AsyncMock(return_value=result)):
            events = await _collect(
                gap_analysis_stream_generator("CSDDD", {}, _fake_user(), enable_cove=False)
            )
        tokens = [e for e in events if isinstance(e, TokenEvent)]
        assert "".join(t.content for t in tokens) == "answer-as-summary"

    async def test_default_requires_review_true(self):
        # Gap analysis defaults requires_review to True when absent.
        result = {"summary": "s", "confidence_score": 0.8}
        with patch(GRAPH_GAP, AsyncMock(return_value=result)):
            events = await _collect(
                gap_analysis_stream_generator("CSRD", {}, _fake_user(), enable_cove=False)
            )
        done = [e for e in events if isinstance(e, DoneEvent)][0]
        assert done.requires_review is True

    async def test_default_confidence_080(self):
        result = {"summary": "s", "confidence_score": 0}
        with patch(GRAPH_GAP, AsyncMock(return_value=result)):
            events = await _collect(
                gap_analysis_stream_generator("CSRD", {}, _fake_user(), enable_cove=False)
            )
        done = [e for e in events if isinstance(e, DoneEvent)][0]
        assert done.confidence_score == pytest.approx(0.80)

    async def test_cove_enabled_passthrough_and_early_return(self):
        cove_done = DoneEvent(
            total_tokens=3,
            confidence_score=0.93,
            requires_review=False,
            cove_applied=True,
            revised_text="revised gap",
        )
        cove_patch, cls = _patch_cove(
            [PhaseChangeEvent(phase="validation", message="validating"), cove_done]
        )
        result = {"summary": "draft summary", "confidence_score": 0.5}
        with patch(GRAPH_GAP, AsyncMock(return_value=result)), cove_patch:
            events = await _collect(
                gap_analysis_stream_generator(
                    "CSRD", {"sector": "x"}, _fake_user(), enable_cove=True
                )
            )
        done = [e for e in events if isinstance(e, DoneEvent)]
        assert len(done) == 1
        assert done[0] is cove_done
        # Orchestrator built once with config enabled=True.
        cls.assert_called_once()
        assert cls.call_args.kwargs["config"].enabled is True

    async def test_cove_failure_falls_back(self):
        result = {"summary": "draft", "confidence_score": 0.6}
        with (
            patch(GRAPH_GAP, AsyncMock(return_value=result)),
            patch(COVE_ORCH, side_effect=RuntimeError("boom")),
        ):
            events = await _collect(
                gap_analysis_stream_generator("CSRD", {}, _fake_user(), enable_cove=True)
            )
        done = [e for e in events if isinstance(e, DoneEvent)]
        assert len(done) == 1
        assert done[0].cove_applied is True
        assert not [e for e in events if isinstance(e, ErrorEvent)]

    async def test_agent_exception_emits_error_event(self):
        with patch(GRAPH_GAP, AsyncMock(side_effect=ValueError("gap failed"))):
            events = await _collect(
                gap_analysis_stream_generator("CSRD", {}, _fake_user(), enable_cove=False)
            )
        errors = [e for e in events if isinstance(e, ErrorEvent)]
        assert len(errors) == 1
        assert errors[0].recoverable is False
        assert "gap failed" in errors[0].message


# ------------------------------------------------------------------ #
#  monitor_stream_generator                                          #
# ------------------------------------------------------------------ #


class TestMonitorStream:
    async def test_happy_path_phase_tokens_done(self):
        summary = "M" * 85
        result = {
            "impact_summary": summary,
            "confidence_score": 0.88,
            "requires_expert_review": False,
        }
        with patch(GRAPH_MONITOR, AsyncMock(return_value=result)) as arun:
            events = await _collect(
                monitor_stream_generator(
                    "New AI Act amendment", {"sector": "x"}, _fake_user(), enable_cove=False
                )
            )

        assert isinstance(events[0], PhaseChangeEvent)
        assert events[0].phase == "draft"

        tokens = [e for e in events if isinstance(e, TokenEvent)]
        assert "".join(t.content for t in tokens) == summary

        # Monitor emits NO citation events.
        assert not [e for e in events if isinstance(e, CitationEvent)]

        done = [e for e in events if isinstance(e, DoneEvent)][0]
        assert done.cove_applied is False
        assert done.confidence_score == pytest.approx(0.88)
        assert done.requires_review is False

        assert arun.await_args.args[0] == "New AI Act amendment"
        assert isinstance(arun.await_args.kwargs["org_id"], str)

    async def test_summary_falls_back_to_answer(self):
        result = {"answer": "answer-impact", "confidence_score": 0.7}
        with patch(GRAPH_MONITOR, AsyncMock(return_value=result)):
            events = await _collect(
                monitor_stream_generator("change", {}, _fake_user(), enable_cove=False)
            )
        tokens = [e for e in events if isinstance(e, TokenEvent)]
        assert "".join(t.content for t in tokens) == "answer-impact"

    async def test_default_confidence_090(self):
        result = {"impact_summary": "s", "confidence_score": 0}
        with patch(GRAPH_MONITOR, AsyncMock(return_value=result)):
            events = await _collect(
                monitor_stream_generator("change", {}, _fake_user(), enable_cove=False)
            )
        done = [e for e in events if isinstance(e, DoneEvent)][0]
        assert done.confidence_score == pytest.approx(0.90)

    async def test_default_requires_review_false(self):
        result = {"impact_summary": "s", "confidence_score": 0.8}
        with patch(GRAPH_MONITOR, AsyncMock(return_value=result)):
            events = await _collect(
                monitor_stream_generator("change", {}, _fake_user(), enable_cove=False)
            )
        done = [e for e in events if isinstance(e, DoneEvent)][0]
        assert done.requires_review is False

    async def test_cove_enabled_passthrough_and_early_return(self):
        cove_done = DoneEvent(
            total_tokens=2,
            confidence_score=0.95,
            requires_review=True,
            cove_applied=True,
            revised_text="revised impact",
        )
        cove_patch, cls = _patch_cove([cove_done])
        result = {"impact_summary": "draft impact", "confidence_score": 0.5}
        with patch(GRAPH_MONITOR, AsyncMock(return_value=result)), cove_patch:
            events = await _collect(
                monitor_stream_generator("change", {"sector": "x"}, _fake_user(), enable_cove=True)
            )
        done = [e for e in events if isinstance(e, DoneEvent)]
        assert len(done) == 1
        assert done[0] is cove_done
        assert done[0].revised_text == "revised impact"
        cls.assert_called_once()

    async def test_cove_failure_falls_back(self):
        result = {"impact_summary": "draft", "confidence_score": 0.6}
        with (
            patch(GRAPH_MONITOR, AsyncMock(return_value=result)),
            patch(COVE_ORCH, side_effect=RuntimeError("boom")),
        ):
            events = await _collect(
                monitor_stream_generator("change", {}, _fake_user(), enable_cove=True)
            )
        done = [e for e in events if isinstance(e, DoneEvent)]
        assert len(done) == 1
        assert done[0].cove_applied is True
        assert not [e for e in events if isinstance(e, ErrorEvent)]

    async def test_agent_exception_emits_error_event(self):
        with patch(GRAPH_MONITOR, AsyncMock(side_effect=RuntimeError("monitor down"))):
            events = await _collect(
                monitor_stream_generator("change", {}, _fake_user(), enable_cove=False)
            )
        errors = [e for e in events if isinstance(e, ErrorEvent)]
        assert len(errors) == 1
        assert errors[0].recoverable is False
        assert "monitor down" in errors[0].message


# ------------------------------------------------------------------ #
#  cross-cutting: draft phase always emitted first                   #
# ------------------------------------------------------------------ #


class TestDraftPhaseAlwaysFirst:
    @pytest.mark.parametrize(
        "generator, graph_target, args",
        [
            (qa_stream_generator, GRAPH_QA, ("q", None)),
            (gap_analysis_stream_generator, GRAPH_GAP, ("CSRD", {})),
            (monitor_stream_generator, GRAPH_MONITOR, ("change", {})),
        ],
    )
    async def test_first_event_is_draft_phase(self, generator, graph_target, args):
        result = {
            "answer": "x",
            "summary": "x",
            "impact_summary": "x",
            "citations": [],
            "confidence_score": 0.7,
        }
        with patch(graph_target, AsyncMock(return_value=result)):
            events = await _collect(generator(*args, _fake_user(), enable_cove=False))
        assert isinstance(events[0], PhaseChangeEvent)
        assert events[0].phase == "draft"
