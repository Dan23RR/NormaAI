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
7. an agent result carrying ``error``/``error_code`` becomes a terminal,
   non-recoverable ``ErrorEvent`` (Italian message) with no tokens and no done;
   a CoVe failure is a recoverable ``ErrorEvent`` followed by a done with
   ``cove_applied=False`` / ``requires_review=True``

Every external dependency is mocked. The agent graph functions and the CoVe
orchestrator are imported *function-locally* inside generators.py, so they are
patched at their *source* modules (``src.agents.graph.arun_qa`` and
``src.agents.cove.orchestrator.CoVeOrchestrator``). No real network / LLM / DB /
model is ever touched.

asyncio_mode = "auto" (configured in pyproject.toml), so plain ``async def``
test methods run without an explicit marker.
"""

import json
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

# DoneEvent fields the generator fills from the answer itself (also on the
# CoVe orchestrator's own done): everything else is the orchestrator's.
_RESULT_FIELDS = {
    "verified_citations",
    "citations_total",
    "caveats",
    "related_frameworks",
    "abstention_reason",
    "corpus_as_of",
}


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
                    "quote_snippet": "large undertakings shall include",
                    # As the citation verifier left it (src.agents.citation_verifier).
                    "verified": True,
                    "official_quote": "Large undertakings shall include",
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
        # The verifier's verdict is passed through, with the OFFICIAL wording.
        assert citations[0].verified is True
        assert citations[0].quote == "Large undertakings shall include"
        # An explicit url in the result is kept as-is.
        assert citations[0].url == "https://eur-lex.europa.eu/eli/32022L2464"

        # Final DoneEvent, no CoVe.
        done = [e for e in events if isinstance(e, DoneEvent)]
        assert len(done) == 1
        assert done[0].cove_applied is False
        assert done[0].confidence_score == pytest.approx(0.91)
        assert done[0].requires_review is False
        assert (done[0].verified_citations, done[0].citations_total) == (1, 1)
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

    async def test_zero_confidence_is_reported_as_zero(self):
        # confidence_score 0 used to be rewritten to a 0.85 default. A zero
        # score is a real score: it stays 0.0 (and the LLM's own review flag
        # is honoured as-is).
        result = {"answer": "hi", "citations": [], "confidence_score": 0}
        with patch(GRAPH_QA, AsyncMock(return_value=result)):
            events = await _collect(qa_stream_generator("q", None, _fake_user(), enable_cove=False))
        done = [e for e in events if isinstance(e, DoneEvent)][0]
        assert done.confidence_score == 0.0

    async def test_missing_confidence_is_zero_and_forces_review(self):
        # Nothing scored this answer: no default may stand in. 0.0 + review.
        result = {"answer": "hi", "citations": []}
        with patch(GRAPH_QA, AsyncMock(return_value=result)):
            events = await _collect(qa_stream_generator("q", None, _fake_user(), enable_cove=False))
        done = [e for e in events if isinstance(e, DoneEvent)][0]
        assert done.confidence_score == 0.0
        assert done.requires_review is True

    async def test_unparseable_confidence_is_zero_and_forces_review(self):
        result = {"answer": "hi", "citations": [], "confidence_score": "high"}
        with patch(GRAPH_QA, AsyncMock(return_value=result)):
            events = await _collect(qa_stream_generator("q", None, _fake_user(), enable_cove=False))
        done = [e for e in events if isinstance(e, DoneEvent)][0]
        assert done.confidence_score == 0.0
        assert done.requires_review is True

    async def test_requires_review_reflects_result_flag(self):
        result = {
            "answer": "hi",
            "citations": [],
            "confidence_score": 0.95,
            "requires_expert_review": True,
        }
        with patch(GRAPH_QA, AsyncMock(return_value=result)):
            events = await _collect(qa_stream_generator("q", None, _fake_user(), enable_cove=False))
        done = [e for e in events if isinstance(e, DoneEvent)][0]
        assert done.requires_review is True
        assert done.confidence_score == pytest.approx(0.95)


# ------------------------------------------------------------------ #
#  qa_stream_generator - agent returned an error dict (no exception)  #
# ------------------------------------------------------------------ #


class TestQaAgentErrorResult:
    """The graph never raises: LLM/retrieval failures come back as a dict with
    ``error``/``error_code``. These must become a terminal ``error`` event with
    an Italian message - never streamed as tokens, never followed by ``done``."""

    @pytest.mark.parametrize(
        "error_code, snippet",
        [
            ("llm_timeout", "tempo massimo"),
            ("llm_circuit_open", "non disponibile"),
            ("llm_provider_error", "errore"),
            ("retrieval_unavailable", "Qdrant"),
        ],
    )
    async def test_error_dict_emits_terminal_error_event(self, error_code, snippet):
        result = {
            "error": "LLM error (gemini): upstream boom",
            "error_code": error_code,
            "confidence_score": 0.0,
            "requires_expert_review": True,
        }
        with patch(GRAPH_QA, AsyncMock(return_value=result)):
            events = await _collect(qa_stream_generator("q", None, _fake_user(), enable_cove=True))

        errors = [e for e in events if isinstance(e, ErrorEvent)]
        assert len(errors) == 1
        assert errors[0].recoverable is False
        assert errors[0].error_code == error_code
        assert snippet.lower() in errors[0].message.lower()
        # The upstream English message is not leaked to the client.
        assert "upstream boom" not in errors[0].message
        # No tokens, no done: the error payload is not an answer.
        assert not [e for e in events if isinstance(e, TokenEvent)]
        assert not [e for e in events if isinstance(e, DoneEvent)]

    async def test_legacy_error_dict_without_code_still_fails_honestly(self):
        result = {"error": "LLM timed out after 120s", "confidence_score": 0.0}
        with patch(GRAPH_QA, AsyncMock(return_value=result)):
            events = await _collect(qa_stream_generator("q", None, _fake_user(), enable_cove=False))
        errors = [e for e in events if isinstance(e, ErrorEvent)]
        assert len(errors) == 1
        assert errors[0].error_code == "llm_timeout"
        assert not [e for e in events if isinstance(e, DoneEvent)]


# ------------------------------------------------------------------ #
#  qa_stream_generator - citation mapping edge cases                 #
# ------------------------------------------------------------------ #


class TestQaCitationMapping:
    async def test_reference_is_not_passed_off_as_celex(self):
        # No "celex" and no framework: the article reference is NOT smuggled
        # into the celex field (the UI shows celex as the identifier badge),
        # and no URL is invented for it.
        result = {
            "answer": "x",
            "citations": [{"reference": "REF-123", "title": "Doc"}],
            "confidence_score": 0.7,
        }
        with patch(GRAPH_QA, AsyncMock(return_value=result)):
            events = await _collect(qa_stream_generator("q", None, _fake_user(), enable_cove=False))
        cit = [e for e in events if isinstance(e, CitationEvent)][0]
        assert cit.celex == ""
        assert cit.article == "REF-123"
        assert cit.url is None

    async def test_url_built_from_celex_defaults_to_italian_eurlex(self):
        result = {
            "answer": "x",
            "citations": [{"celex": "32024R1689"}],
            "confidence_score": 0.7,
        }
        with patch(GRAPH_QA, AsyncMock(return_value=result)):
            events = await _collect(qa_stream_generator("q", None, _fake_user(), enable_cove=False))
        cit = [e for e in events if isinstance(e, CitationEvent)][0]
        assert cit.url == "https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:32024R1689"

    async def test_url_uses_english_eurlex_when_language_is_en(self):
        result = {
            "answer": "x",
            "citations": [{"celex": "32024R1689"}],
            "confidence_score": 0.7,
        }
        with patch(GRAPH_QA, AsyncMock(return_value=result)):
            events = await _collect(
                qa_stream_generator("q", None, _fake_user(), enable_cove=False, language="en")
            )
        cit = [e for e in events if isinstance(e, CitationEvent)][0]
        assert cit.url == "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1689"

    async def test_framework_only_citation_links_to_primary_act(self):
        # The qa_bot prompt emits {framework, reference, quote_snippet} with no
        # CELEX: the link resolves through the seeded primary act of the framework.
        result = {
            "answer": "x",
            "citations": [{"framework": "CSRD", "reference": "Art. 19a(1)"}],
            "confidence_score": 0.7,
        }
        with patch(GRAPH_QA, AsyncMock(return_value=result)):
            events = await _collect(qa_stream_generator("q", None, _fake_user(), enable_cove=False))
        cit = [e for e in events if isinstance(e, CitationEvent)][0]
        assert cit.celex == "32022L2464"
        assert cit.url == "https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:32022L2464"
        assert cit.title == "CSRD"
        assert cit.article == "Art. 19a(1)"

    async def test_verified_and_grounded_only_from_pipeline_booleans(self):
        result = {
            "answer": "x",
            "citations": [
                {"celex": "32022L2464", "verified": True, "grounded": True},
                {"celex": "32022L2464", "verified": "yes", "grounded": None},
            ],
            "confidence_score": 0.7,
        }
        with patch(GRAPH_QA, AsyncMock(return_value=result)):
            events = await _collect(qa_stream_generator("q", None, _fake_user(), enable_cove=False))
        cits = [e for e in events if isinstance(e, CitationEvent)]
        assert cits[0].verified is True and cits[0].grounded is True
        # Non-boolean "verification" values are not trusted -> omitted.
        assert cits[1].verified is None and cits[1].grounded is None

    def test_absent_verified_is_omitted_from_the_wire_format(self):
        from src.api.streaming.sse import format_sse

        wire = format_sse(CitationEvent(celex="32022L2464", article="Art. 1", title="CSRD"))
        assert '"verified"' not in wire
        assert '"url"' not in wire
        assert '"urn"' not in wire

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

        # Exactly one DoneEvent - the CoVe-emitted one - carrying revised_text,
        # completed with the answer's own fields (counters, caveats, ...).
        done = [e for e in events if isinstance(e, DoneEvent)]
        assert len(done) == 1
        assert done[0].model_dump(include=set(DoneEvent.model_fields) - _RESULT_FIELDS) == (
            cove_done.model_dump(include=set(DoneEvent.model_fields) - _RESULT_FIELDS)
        )
        assert done[0].cove_applied is True
        assert done[0].revised_text == "VERIFIED answer."
        assert (done[0].verified_citations, done[0].citations_total) == (0, 0)

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

    async def test_cove_failure_is_reported_and_done_says_not_applied(self):
        # If the CoVe block raises, the generator still finishes the draft -
        # but honestly: a RECOVERABLE error event says verification failed, and
        # the final DoneEvent carries cove_applied=False (CoVe never ran) and
        # requires_review=True (the answer is unverified). It used to claim
        # cove_applied=True from the *request* flag.
        result = {"answer": "draft", "citations": [], "confidence_score": 0.66}

        with (
            patch(GRAPH_QA, AsyncMock(return_value=result)),
            patch(COVE_ORCH, side_effect=RuntimeError("cove construction failed")),
        ):
            events = await _collect(qa_stream_generator("q", None, _fake_user(), enable_cove=True))

        errors = [e for e in events if isinstance(e, ErrorEvent)]
        assert len(errors) == 1
        assert errors[0].recoverable is True
        assert errors[0].error_code == "cove_failed"

        done = [e for e in events if isinstance(e, DoneEvent)]
        assert len(done) == 1
        assert done[0].cove_applied is False
        assert done[0].requires_review is True
        assert done[0].confidence_score == pytest.approx(0.66)
        # Draft tokens were still emitted before the fallback, error precedes done.
        assert [e for e in events if isinstance(e, TokenEvent)]
        assert events.index(errors[0]) < events.index(done[0])

    async def test_cove_terminal_error_is_not_followed_by_done(self):
        # The orchestrator ends with a NON-recoverable error (pipeline crash):
        # the generator must not append a DoneEvent claiming completion.
        cove_patch, _cls = _patch_cove(
            [
                PhaseChangeEvent(phase="planning", message="planning..."),
                ErrorEvent(message="CoVe pipeline error: boom", recoverable=False),
            ]
        )
        result = {"answer": "draft", "citations": [], "confidence_score": 0.5}
        with patch(GRAPH_QA, AsyncMock(return_value=result)), cove_patch:
            events = await _collect(qa_stream_generator("q", None, _fake_user(), enable_cove=True))
        assert not [e for e in events if isinstance(e, DoneEvent)]
        assert [e for e in events if isinstance(e, ErrorEvent)][-1].recoverable is False


# ------------------------------------------------------------------ #
#  qa_stream_generator - deterministic citation verification         #
# ------------------------------------------------------------------ #

GENERATORS_SETTINGS = "src.api.streaming.generators.get_settings"


def _settings(**overrides):
    from src.config import get_settings

    return get_settings().model_copy(update=overrides)


def _verified_citation(**overrides):
    """A citation as the agent node leaves it after the citation verifier."""
    citation = {
        "framework": "AI_ACT",
        "reference": "Art. 50(2)",
        "quote_snippet": "garantiscono che gli output siano marcati",
        "grounded": True,
        "verified": True,
        "match": "exact",
        "level": "article",
        "chunk_id": "pt-ai-50",
        "celex": "32024R1689",
        "article": "Art. 50",
        "paragraph": "2",
        "lang": "IT",
        "consolidated_as_of": "2026-07-27",
        "url": "https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:32024R1689",
        "official_quote": "garantiscono che gli output del sistema di IA siano marcati",
    }
    citation.update(overrides)
    return citation


def _unverified_citation():
    return {
        "framework": "CSRD",
        "reference": "Art. 19a(1)",
        "quote_snippet": "le grandi imprese includono nella relazione",
        "grounded": False,
        "verified": False,
        "match": None,
        "level": None,
        "chunk_id": None,
        "celex": None,
        "article": None,
        "paragraph": None,
        "lang": None,
        "consolidated_as_of": None,
        "url": None,
        "official_quote": None,
    }


class TestQaCitationVerification:
    async def _stream(self, result, *, settings=None, **kwargs):
        with (
            patch(GRAPH_QA, AsyncMock(return_value=result)) as arun,
            patch(GENERATORS_SETTINGS, return_value=settings or _settings()),
        ):
            events = await _collect(
                qa_stream_generator(
                    "q", None, _fake_user(), enable_cove=kwargs.pop("enable_cove", False), **kwargs
                )
            )
        return events, arun

    async def test_verified_citation_event_describes_the_official_text(self):
        result = {
            "answer": "x",
            "citations": [_verified_citation()],
            "verified_citations": 1,
            "citations_total": 1,
            "confidence_score": 0.9,
        }
        events, _ = await self._stream(result, language="en")
        cit = [e for e in events if isinstance(e, CitationEvent)][0]
        assert cit.framework == "AI_ACT"
        assert cit.verified is True and cit.match == "exact" and cit.level == "article"
        assert cit.celex == "32024R1689"
        assert cit.article == "Art. 50" and cit.paragraph == "2"
        # The official wording, not the model's paraphrase of it.
        assert cit.quote == "garantiscono che gli output del sistema di IA siano marcati"
        assert cit.chunk_id == "pt-ai-50" and cit.lang == "IT"
        assert cit.consolidated_as_of == "2026-07-27"
        # The URL is the verifier's (chunk language), not rebuilt from the request.
        assert cit.url == "https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:32024R1689"
        assert cit.grounded is True and cit.title == "AI_ACT"

    async def test_unverified_citation_event_keeps_the_models_reference_and_quote(self):
        result = {"answer": "x", "citations": [_unverified_citation()], "confidence_score": 0.9}
        events, _ = await self._stream(result)
        cit = [e for e in events if isinstance(e, CitationEvent)][0]
        assert cit.verified is False
        assert cit.quote == "le grandi imprese includono nella relazione"
        assert cit.article == "Art. 19a(1)"
        assert cit.match is None and cit.level is None and cit.chunk_id is None
        assert cit.lang is None and cit.paragraph is None
        # "Da verificare" still links to the primary act of the cited framework.
        assert cit.celex == "32022L2464"
        assert cit.url == "https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:32022L2464"

    def test_wire_format_of_citation_events(self):
        from src.api.streaming.generators import _citation_event
        from src.api.streaming.sse import format_sse

        verified = json.loads(format_sse(_citation_event(_verified_citation(), "it"))[6:])
        assert verified == {
            "type": "citation",
            "framework": "AI_ACT",
            "celex": "32024R1689",
            "article": "Art. 50",
            "paragraph": "2",
            "title": "AI_ACT",
            "url": "https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:32024R1689",
            "quote": "garantiscono che gli output del sistema di IA siano marcati",
            "verified": True,
            "match": "exact",
            "level": "article",
            "chunk_id": "pt-ai-50",
            "lang": "IT",
            "consolidated_as_of": "2026-07-27",
            "grounded": True,
        }
        unverified = json.loads(format_sse(_citation_event(_unverified_citation(), "it"))[6:])
        assert unverified == {
            "type": "citation",
            "framework": "CSRD",
            "celex": "32022L2464",
            "article": "Art. 19a(1)",
            "title": "CSRD",
            "url": "https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:32022L2464",
            "quote": "le grandi imprese includono nella relazione",
            "verified": False,
            "grounded": False,
        }

    def test_verified_passage_without_celex_gets_no_guessed_link(self):
        # Found in a chunk with no CELEX (e.g. an uploaded document): the event
        # must not borrow the cited framework's primary act as its source.
        from src.api.streaming.generators import _citation_event

        event = _citation_event(_verified_citation(celex=None, url=None), "it")
        assert event.verified is True
        assert event.celex == "" and event.url is None

    def test_unknown_match_or_level_values_are_not_forwarded(self):
        from src.api.streaming.generators import _citation_event

        event = _citation_event(_verified_citation(match="maybe", level="somewhere"), "it")
        assert event.match is None and event.level is None

    async def test_done_event_reports_the_answer(self):
        result = {
            "answer": "x",
            "citations": [_verified_citation(), _unverified_citation()],
            "verified_citations": 1,
            "citations_total": 2,
            "confidence_score": 0.8,
            "caveats": ["Nota.", {"not": "a string"}, ""],
            "related_frameworks": ["GDPR", None],
        }
        events, _ = await self._stream(result, settings=_settings(corpus_as_of="2026-10-01"))
        done = [e for e in events if isinstance(e, DoneEvent)][0]
        assert (done.verified_citations, done.citations_total) == (1, 2)
        assert done.caveats == ["Nota."]
        assert done.related_frameworks == ["GDPR"]
        assert done.abstention_reason is None
        assert done.corpus_as_of == "2026-10-01"
        assert done.requires_review is False and done.confidence_score == pytest.approx(0.8)

    def test_done_wire_format_always_carries_abstention_reason_and_corpus_date(self):
        from src.api.streaming.sse import format_sse

        wire = json.loads(
            format_sse(
                DoneEvent(
                    total_tokens=1,
                    confidence_score=0.5,
                    requires_review=True,
                    cove_applied=False,
                    verified_citations=0,
                    citations_total=0,
                )
            )[6:]
        )
        assert wire["abstention_reason"] is None and wire["corpus_as_of"] is None
        assert wire["caveats"] == [] and wire["related_frameworks"] == []
        assert (wire["verified_citations"], wire["citations_total"]) == (0, 0)
        assert "revised_text" not in wire  # other None fields stay omitted

    async def test_no_verified_citation_flags_the_streamed_answer(self):
        result = {
            "answer": "x",
            "citations": [_unverified_citation()],
            "verified_citations": 0,
            "citations_total": 1,
            "confidence_score": 0.9,
            "requires_expert_review": False,
        }
        events, _ = await self._stream(result, language="it")
        done = [e for e in events if isinstance(e, DoneEvent)][0]
        assert done.requires_review is True
        assert done.confidence_score == pytest.approx(0.6)
        assert done.caveats == [
            "Nessuno dei passaggi citati è stato ritrovato testualmente nei testi del corpus: "
            "verifica le fonti prima di usarla."
        ]

        events, _ = await self._stream(dict(result, caveats=[]), language="en")
        done = [e for e in events if isinstance(e, DoneEvent)][0]
        assert done.caveats == [
            "None of the cited passages was found verbatim in the corpus texts: "
            "check the sources before using this answer."
        ]

    async def test_strict_mode_streams_the_abstention(self):
        result = {
            "answer": "risposta non verificata",
            "citations": [_unverified_citation()],
            "verified_citations": 0,
            "citations_total": 1,
            "confidence_score": 0.9,
        }
        events, _ = await self._stream(
            result, settings=_settings(citation_verification="strict"), language="it"
        )
        text = "".join(e.content for e in events if isinstance(e, TokenEvent))
        assert text.startswith("Non posso fornire una risposta verificata")
        assert not [e for e in events if isinstance(e, CitationEvent)]
        done = [e for e in events if isinstance(e, DoneEvent)][0]
        assert done.abstention_reason == "unverified_citations"
        assert (done.verified_citations, done.citations_total) == (0, 1)
        assert done.requires_review is True

    async def test_cove_cannot_clear_the_unverified_flag(self):
        cove_done = DoneEvent(
            total_tokens=3, confidence_score=0.97, requires_review=False, cove_applied=True
        )
        cove_patch, _cls = _patch_cove([cove_done])
        result = {
            "answer": "x",
            "citations": [_unverified_citation()],
            "verified_citations": 0,
            "citations_total": 1,
            "confidence_score": 0.6,
            "requires_expert_review": True,
        }
        with cove_patch:
            events, _ = await self._stream(result, enable_cove=True)
        done = [e for e in events if isinstance(e, DoneEvent)]
        assert len(done) == 1
        assert done[0].cove_applied is True
        assert done[0].requires_review is True
        assert done[0].confidence_score == pytest.approx(0.6)
        assert (done[0].verified_citations, done[0].citations_total) == (0, 1)

    async def test_cove_verdict_stands_when_a_citation_is_verified(self):
        cove_done = DoneEvent(
            total_tokens=3, confidence_score=0.97, requires_review=False, cove_applied=True
        )
        cove_patch, _cls = _patch_cove([cove_done])
        result = {
            "answer": "x",
            "citations": [_verified_citation()],
            "verified_citations": 1,
            "citations_total": 1,
            "confidence_score": 0.7,
        }
        with cove_patch:
            events, _ = await self._stream(result, enable_cove=True)
        done = [e for e in events if isinstance(e, DoneEvent)][0]
        assert done.requires_review is False
        assert done.confidence_score == pytest.approx(0.97)

    async def test_cove_is_skipped_for_an_abstention(self):
        cove_patch, cls = _patch_cove([])
        result = {
            "answer": "Non posso fornire una risposta sufficientemente affidabile.",
            "citations": [],
            "confidence_score": 0.2,
            "requires_expert_review": True,
            "abstention_reason": "snc_low_trust",
        }
        with cove_patch:
            events, _ = await self._stream(result, enable_cove=True)
        cls.assert_not_called()
        done = [e for e in events if isinstance(e, DoneEvent)][0]
        assert done.cove_applied is False
        assert done.abstention_reason == "snc_low_trust"

    async def test_request_language_is_forwarded_to_the_agent(self):
        result = {"answer": "x", "citations": [], "confidence_score": 0.9}
        _, arun = await self._stream(result, language="en")
        assert arun.await_args.kwargs["language"] == "en"


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
        assert errors[0].error_code == "internal_error"
        assert "graph exploded" not in errors[0].message  # internals are logged, not leaked
        assert "Errore interno" in errors[0].message
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

    async def test_requires_review_reflects_result_flag_not_a_default(self):
        # The flag mirrors the pipeline's own verdict: absent -> False, set -> True.
        result = {"summary": "s", "confidence_score": 0.8}
        with patch(GRAPH_GAP, AsyncMock(return_value=result)):
            events = await _collect(
                gap_analysis_stream_generator("CSRD", {}, _fake_user(), enable_cove=False)
            )
        done = [e for e in events if isinstance(e, DoneEvent)][0]
        assert done.requires_review is False

        flagged = {"summary": "s", "confidence_score": 0.8, "requires_expert_review": True}
        with patch(GRAPH_GAP, AsyncMock(return_value=flagged)):
            events = await _collect(
                gap_analysis_stream_generator("CSRD", {}, _fake_user(), enable_cove=False)
            )
        assert [e for e in events if isinstance(e, DoneEvent)][0].requires_review is True

    async def test_zero_confidence_not_rewritten_to_080(self):
        result = {"summary": "s", "confidence_score": 0}
        with patch(GRAPH_GAP, AsyncMock(return_value=result)):
            events = await _collect(
                gap_analysis_stream_generator("CSRD", {}, _fake_user(), enable_cove=False)
            )
        done = [e for e in events if isinstance(e, DoneEvent)][0]
        assert done.confidence_score == 0.0

    async def test_structured_gap_result_streams_a_digest_not_a_python_repr(self):
        # The gap agent returns the prompt's JSON shape (no summary/answer):
        # the streamed text must be a readable digest, not str(dict).
        result = {
            "framework": "CSRD",
            "overall_score": 45.0,
            "status_summary": {"compliant": 2, "non_compliant": 5},
            "requirements": [],
            "confidence_score": 0.8,
        }
        with patch(GRAPH_GAP, AsyncMock(return_value=result)):
            events = await _collect(
                gap_analysis_stream_generator("CSRD", {}, _fake_user(), enable_cove=False)
            )
        text = "".join(e.content for e in events if isinstance(e, TokenEvent))
        assert "45.0%" in text
        assert "2 compliant" in text
        assert "{'" not in text

    async def test_agent_error_dict_emits_terminal_error(self):
        result = {"error": "Rate limited by gemini API.", "error_code": "llm_rate_limited"}
        with patch(GRAPH_GAP, AsyncMock(return_value=result)):
            events = await _collect(
                gap_analysis_stream_generator("CSRD", {}, _fake_user(), enable_cove=False)
            )
        errors = [e for e in events if isinstance(e, ErrorEvent)]
        assert len(errors) == 1
        assert errors[0].recoverable is False
        assert errors[0].error_code == "llm_rate_limited"
        assert not [e for e in events if isinstance(e, DoneEvent)]
        assert not [e for e in events if isinstance(e, TokenEvent)]

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
        assert done[0].revised_text == "revised gap"
        assert done[0].cove_applied is True and done[0].requires_review is False
        assert done[0].confidence_score == pytest.approx(0.93)
        # No Q&A citations here: no counters on the gap-analysis done.
        assert done[0].citations_total is None
        # Orchestrator built once with config enabled=True.
        cls.assert_called_once()
        assert cls.call_args.kwargs["config"].enabled is True

    async def test_cove_failure_falls_back_honestly(self):
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
        assert done[0].cove_applied is False
        assert done[0].requires_review is True
        errors = [e for e in events if isinstance(e, ErrorEvent)]
        assert len(errors) == 1 and errors[0].recoverable is True

    async def test_agent_exception_emits_error_event(self):
        with patch(GRAPH_GAP, AsyncMock(side_effect=ValueError("gap failed"))):
            events = await _collect(
                gap_analysis_stream_generator("CSRD", {}, _fake_user(), enable_cove=False)
            )
        errors = [e for e in events if isinstance(e, ErrorEvent)]
        assert len(errors) == 1
        assert errors[0].recoverable is False
        assert errors[0].error_code == "internal_error"
        assert "gap failed" not in errors[0].message  # internals are logged, not leaked
        assert "Errore interno" in errors[0].message


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

    async def test_zero_confidence_not_rewritten_to_090(self):
        result = {"impact_summary": "s", "confidence_score": 0}
        with patch(GRAPH_MONITOR, AsyncMock(return_value=result)):
            events = await _collect(
                monitor_stream_generator("change", {}, _fake_user(), enable_cove=False)
            )
        done = [e for e in events if isinstance(e, DoneEvent)][0]
        assert done.confidence_score == 0.0

    async def test_agent_error_dict_emits_terminal_error(self):
        result = {
            "error": "Knowledge base retrieval failed: x",
            "error_code": "retrieval_unavailable",
        }
        with patch(GRAPH_MONITOR, AsyncMock(return_value=result)):
            events = await _collect(
                monitor_stream_generator("change", {}, _fake_user(), enable_cove=False)
            )
        errors = [e for e in events if isinstance(e, ErrorEvent)]
        assert len(errors) == 1 and errors[0].recoverable is False
        assert not [e for e in events if isinstance(e, DoneEvent)]

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
        assert done[0].model_dump(include=set(DoneEvent.model_fields) - _RESULT_FIELDS) == (
            cove_done.model_dump(include=set(DoneEvent.model_fields) - _RESULT_FIELDS)
        )
        assert done[0].revised_text == "revised impact"
        cls.assert_called_once()

    async def test_cove_failure_falls_back_honestly(self):
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
        assert done[0].cove_applied is False
        assert done[0].requires_review is True
        errors = [e for e in events if isinstance(e, ErrorEvent)]
        assert len(errors) == 1 and errors[0].recoverable is True

    async def test_agent_exception_emits_error_event(self):
        with patch(GRAPH_MONITOR, AsyncMock(side_effect=RuntimeError("monitor down"))):
            events = await _collect(
                monitor_stream_generator("change", {}, _fake_user(), enable_cove=False)
            )
        errors = [e for e in events if isinstance(e, ErrorEvent)]
        assert len(errors) == 1
        assert errors[0].recoverable is False
        assert errors[0].error_code == "internal_error"
        assert "monitor down" not in errors[0].message  # internals are logged, not leaked
        assert "Errore interno" in errors[0].message


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
