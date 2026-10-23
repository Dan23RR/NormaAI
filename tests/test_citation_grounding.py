"""Per-citation ``grounded`` annotation written by the grounding guard.

The guard in src/agents/nodes.py used to expose only an aggregate verdict
(``grounding_warning`` + capped confidence). It now also annotates every
citation dict with ``grounded`` - the same "backed by the retrieved evidence"
definition the citation_grounding_rate KPI uses - so the citation SSE events
can carry an honest per-citation flag instead of a default.
"""

import pytest

from src.agents.nodes import _apply_grounding_guard, citation_grounding_rate


class TestCitationGroundedAnnotation:
    def test_each_citation_gets_an_evidence_backed_verdict(self):
        result = {
            "answer": "x",
            "confidence_score": 0.9,
            "citations": [
                {
                    "framework": "GDPR",
                    "reference": "Art. 5",
                    "quote_snippet": "principi di trattamento",
                },
                {"framework": "AI_ACT", "reference": "Art. 6"},  # not in the evidence
                {"framework": "GDPR", "quote_snippet": "frase completamente inventata dal modello"},
            ],
        }
        chunks = [
            {
                "framework": "GDPR",
                "article_number": "5",
                "text": "I principi di trattamento dei dati personali sono elencati all'articolo 5.",
            }
        ]
        out = _apply_grounding_guard(result, chunks)
        assert [c["grounded"] for c in out["citations"]] == [True, False, False]
        # The annotation agrees with the KPI built on the same helper.
        assert citation_grounding_rate(out, chunks) == pytest.approx(1 / 3)

    def test_grounded_citation_on_clean_answer_is_true_without_warning(self):
        result = {
            "answer": "x",
            "confidence_score": 0.9,
            "citations": [{"framework": "GDPR", "reference": "Art. 5"}],
        }
        chunks = [{"framework": "GDPR", "article_number": "5", "text": "articolo 5 principi"}]
        out = _apply_grounding_guard(result, chunks)
        assert out["citations"][0]["grounded"] is True
        assert "grounding_warning" not in out
        assert out["confidence_score"] == 0.9

    def test_no_evidence_means_not_grounded(self):
        result = {"answer": "x", "confidence_score": 0.9, "citations": [{"framework": "GDPR"}]}
        out = _apply_grounding_guard(result, [])
        assert out["citations"][0]["grounded"] is False
        assert out["requires_expert_review"] is True

    def test_non_dict_citations_are_left_alone(self):
        result = {"answer": "x", "confidence_score": 0.9, "citations": ["loose text"]}
        out = _apply_grounding_guard(result, [{"framework": "GDPR", "text": "evidence text here"}])
        assert out["citations"] == ["loose text"]

    async def test_flag_reaches_the_citation_sse_event(self):
        # End to end through the stream generator: the annotated result yields
        # CitationEvent.grounded without any default.
        from unittest.mock import AsyncMock, MagicMock, patch

        from src.api.streaming.generators import qa_stream_generator
        from src.api.streaming.sse import CitationEvent

        result = _apply_grounding_guard(
            {
                "answer": "x",
                "confidence_score": 0.9,
                "citations": [{"framework": "GDPR"}, {"framework": "CSRD"}],
            },
            [{"framework": "GDPR", "text": "evidence text here"}],
        )
        user = MagicMock()
        user.org_id = "org"
        with patch("src.agents.graph.arun_qa", AsyncMock(return_value=result)):
            events = [
                e
                async for e in qa_stream_generator("q", None, user, enable_cove=False)
                if isinstance(e, CitationEvent)
            ]
        assert [e.grounded for e in events] == [True, False]
        assert all(e.verified is None for e in events)  # no verifier ran
