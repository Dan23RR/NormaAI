"""Unit tests for the CoVe orchestrator (src/agents/cove/orchestrator.py).

The orchestrator drives the 5-phase Chain-of-Verification pipeline. The phases
themselves are LLM-bound, so these tests exercise the parts that can be checked
deterministically without any real network/LLM:

- ``_extract_citations_from_text`` (pure regex helper)
- ``_known_celex`` (seeded ground-truth set)
- ``CoVeOrchestrator.__init__`` config handling
- ``_validate_citations`` with mocked indexer / normattiva client
- ``_extract_claims`` / ``_plan_verification`` / ``_verify_claim`` / ``_revise_draft``
  with a patched ``acall_llm`` (the only external call those helpers make)
- the ``run()`` async generator's early / guard branches

All LLM access is mocked via ``src.agents.cove.orchestrator.acall_llm`` (imported
into the module namespace), so no real provider call is ever made.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.cove.models import (
    Claim,
    CoVeConfig,
    DraftResult,
    VerificationQuestion,
    VerificationStep,
)
from src.agents.cove.orchestrator import (
    CoVeOrchestrator,
    _extract_citations_from_text,
    _known_celex,
)
from src.api.streaming.sse import (
    DoneEvent,
    ErrorEvent,
    PhaseChangeEvent,
    VerificationResultEvent,
    VerificationStartEvent,
)

ORCH = "src.agents.cove.orchestrator.acall_llm"


def _patch_llm(return_value=None, side_effect=None):
    """Patch the module-level acall_llm with an AsyncMock."""
    mock = AsyncMock()
    if side_effect is not None:
        mock.side_effect = side_effect
    else:
        mock.return_value = return_value
    return patch(ORCH, mock)


# NOTE (path resolution, fixed): the module computes
#   PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "prompts"
# which now correctly resolves to the repo-root ``prompts/`` directory where the
# real templates live (cove_extract_claims.txt, cove_plan_verification.txt,
# cove_verify_claim.txt, cove_revise_draft.txt). So ``_load_prompt`` succeeds for
# every helper that loads a template; only a genuinely-missing name raises
# FileNotFoundError.
#
# To unit-test the *parsing / branching* logic those helpers implement (in
# isolation from the real template content), we still patch ``_load_prompt`` to
# return a harmless template containing the placeholders each prompt formats.
# This keeps the parsing tests independent of edits to the shipped templates.
# Each helper calls prompt.format(**subset) with a DIFFERENT placeholder subset,
# so a single template would raise KeyError. Map name -> matching placeholders.
_FAKE_PROMPTS = {
    "cove_extract_claims": "EXTRACT {response_text}",
    "cove_plan_verification": "PLAN {claims}",
    "cove_verify_claim": "VERIFY {evidence} | {claim} | {question}",
    "cove_revise_draft": "REVISE {original_response} | {verification_results}",
}


def _patch_prompt():
    """Patch _load_prompt so helpers parse against deterministic templates.

    Isolates the parsing/branching logic from the real shipped template content.
    """
    return patch(
        "src.agents.cove.orchestrator._load_prompt",
        side_effect=lambda name: _FAKE_PROMPTS[name],
    )


# ------------------------------------------------------------------ #
#  _extract_citations_from_text (pure helper)                        #
# ------------------------------------------------------------------ #


class TestExtractCitations:
    def test_empty_text_returns_empty(self):
        assert _extract_citations_from_text("") == []

    def test_text_with_no_citations(self):
        cites = _extract_citations_from_text("This is a plain sentence with no references.")
        assert cites == []

    def test_lettered_celex_extracted(self):
        cites = _extract_citations_from_text("CSRD is 32022L2464 and AI Act is 32024R1689.")
        celex = {c["value"] for c in cites if c["type"] == "celex"}
        assert celex == {"32022L2464", "32024R1689"}

    def test_all_digit_celex_extracted(self):
        # The rare all-digit fallback form (\b3\d{7}\b).
        cites = _extract_citations_from_text("Legacy ref 32016001 appears here.")
        celex = {c["value"] for c in cites if c["type"] == "celex"}
        assert "32016001" in celex

    def test_celex_deduplicated(self):
        cites = _extract_citations_from_text("32022L2464 again 32022L2464 and 32022L2464.")
        celex = [c for c in cites if c["type"] == "celex"]
        assert len(celex) == 1
        assert celex[0]["value"] == "32022L2464"

    def test_urn_extracted(self):
        text = "See urn:nir:stato:legge:2024-01-01;123 for details."
        cites = _extract_citations_from_text(text)
        urns = [c for c in cites if c["type"] == "urn"]
        assert len(urns) == 1
        assert urns[0]["value"].startswith("urn:nir:")

    def test_single_article_reference(self):
        cites = _extract_citations_from_text("Per l'Art. 29 del regolamento.")
        articles = [c for c in cites if c["type"] == "article"]
        assert len(articles) == 1
        # A single article (no range) is rendered without a dash.
        assert articles[0]["value"] == "Articles 29"

    def test_article_range_reference(self):
        cites = _extract_citations_from_text("artt. 1-3 apply.")
        articles = [c for c in cites if c["type"] == "article"]
        assert len(articles) == 1
        assert articles[0]["value"] == "Articles 1-3"

    def test_article_word_form_and_value(self):
        cites = _extract_citations_from_text("Article 5 of the GDPR.")
        articles = [c for c in cites if c["type"] == "article"]
        assert articles[0]["value"] == "Articles 5"
        assert articles[0]["text"] == "Article 5"

    def test_mixed_citations(self):
        text = "Under 32022L2464 Art. 19a and urn:nir:stato:legge:2024;1 the rule holds."
        cites = _extract_citations_from_text(text)
        types = {c["type"] for c in cites}
        assert types == {"celex", "article", "urn"}


# ------------------------------------------------------------------ #
#  _known_celex (seeded ground-truth)                                #
# ------------------------------------------------------------------ #


class TestKnownCelex:
    def test_returns_seeded_celex_numbers(self):
        known = _known_celex()
        # These are seeded in CORE_FRAMEWORKS - must be in the trusted set.
        assert "32022L2464" in known  # CSRD
        assert "32024R1689" in known  # AI Act
        assert "32016R0679" in known  # GDPR

    def test_unseeded_celex_not_in_set(self):
        assert "39999L9999" not in _known_celex()

    def test_returns_a_set(self):
        assert isinstance(_known_celex(), set)

    def test_import_failure_returns_empty_set(self):
        # When CORE_FRAMEWORKS cannot be imported, fall back to empty set
        # (defensive guard in the source).
        import builtins

        real_import = builtins.__import__

        def boom(name, *args, **kwargs):
            if name == "src.crawler.eurlex.client":
                raise ImportError("simulated")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=boom):
            assert _known_celex() == set()


# ------------------------------------------------------------------ #
#  __init__ / config handling                                        #
# ------------------------------------------------------------------ #


class TestOrchestratorInit:
    def test_default_config_created_when_none(self):
        orch = CoVeOrchestrator()
        assert isinstance(orch.config, CoVeConfig)
        # Default CoVeConfig is disabled.
        assert orch.config.enabled is False
        assert orch.indexer is None
        assert orch.normattiva_client is None
        assert orch._start_time is None

    def test_passed_config_is_used(self):
        cfg = CoVeConfig(enabled=True, max_claims=3, timeout_per_phase_seconds=5.0)
        orch = CoVeOrchestrator(config=cfg)
        assert orch.config is cfg
        assert orch.config.max_claims == 3

    def test_dependencies_stored(self):
        indexer = MagicMock()
        normattiva = MagicMock()
        orch = CoVeOrchestrator(indexer=indexer, normattiva_client=normattiva)
        assert orch.indexer is indexer
        assert orch.normattiva_client is normattiva


# ------------------------------------------------------------------ #
#  _validate_citations                                               #
# ------------------------------------------------------------------ #


class TestValidateCitations:
    async def test_no_citations_returns_empty(self):
        orch = CoVeOrchestrator()
        checks = await orch._validate_citations("Plain text, nothing to validate.")
        assert checks == []

    async def test_known_celex_is_verified(self):
        orch = CoVeOrchestrator()
        checks = await orch._validate_citations("Per la CSRD 32022L2464.")
        by_celex = {c.celex: c for c in checks if c.celex}
        assert by_celex["32022L2464"].exists is True
        assert by_celex["32022L2464"].is_current is True
        assert by_celex["32022L2464"].validation == "verified"

    async def test_wellformed_unseeded_celex_is_unverified(self):
        # The core anti-hallucination guard: a well-formed but never-indexed
        # CELEX must NOT be rubber-stamped valid.
        orch = CoVeOrchestrator()
        checks = await orch._validate_citations("Una fantomatica 39999L9999.")
        check = next(c for c in checks if c.celex == "39999L9999")
        assert check.exists is False
        assert check.is_current is False
        assert check.validation == "unverified"
        assert check.error is not None

    async def test_malformed_all_digit_celex_is_invalid(self):
        # 32016001 matches the all-digit extraction pattern but FAILS the
        # canonical _CELEX_RE (which requires a type letter) -> "invalid".
        orch = CoVeOrchestrator()
        checks = await orch._validate_citations("Bogus 32016001 reference.")
        check = next(c for c in checks if c.celex == "32016001")
        assert check.exists is False
        assert check.validation == "invalid"
        assert "Malformed" in (check.error or "")

    async def test_article_reference_is_grounded(self):
        orch = CoVeOrchestrator()
        checks = await orch._validate_citations("As stated in Art. 29.")
        article = next(c for c in checks if c.article)
        assert article.validation == "grounded"
        # Honest provenance: exists/current are set but the error note explains
        # it is grounded via retrieved evidence, not an independent registry.
        assert article.exists is True
        assert article.error is not None

    async def test_urn_verified_when_normattiva_confirms(self):
        normattiva = MagicMock()
        result = MagicMock()
        result.exists = True
        result.is_in_force = True
        result.url = "https://normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:2024;1"
        normattiva.validate_urn = AsyncMock(return_value=result)

        orch = CoVeOrchestrator(normattiva_client=normattiva)
        checks = await orch._validate_citations("Vedi urn:nir:stato:legge:2024;1 qui.")
        urn_check = next(c for c in checks if c.urn)
        assert urn_check.exists is True
        assert urn_check.is_current is True
        assert urn_check.validation == "verified"
        assert urn_check.url == result.url
        normattiva.validate_urn.assert_awaited_once()

    async def test_urn_unverified_when_normattiva_reports_missing(self):
        normattiva = MagicMock()
        result = MagicMock()
        result.exists = False
        result.is_in_force = False
        result.url = None
        normattiva.validate_urn = AsyncMock(return_value=result)

        orch = CoVeOrchestrator(normattiva_client=normattiva)
        checks = await orch._validate_citations("Vedi urn:nir:stato:legge:9999;9 qui.")
        urn_check = next(c for c in checks if c.urn)
        assert urn_check.exists is False
        assert urn_check.validation == "unverified"

    async def test_urn_exception_path_marks_unverified(self):
        normattiva = MagicMock()
        normattiva.validate_urn = AsyncMock(side_effect=RuntimeError("boom"))

        orch = CoVeOrchestrator(normattiva_client=normattiva)
        checks = await orch._validate_citations("Vedi urn:nir:stato:legge:2024;1 qui.")
        urn_check = next(c for c in checks if c.urn)
        assert urn_check.exists is False
        assert urn_check.validation == "unverified"
        assert "boom" in (urn_check.error or "")

    async def test_urn_without_normattiva_client_skipped(self):
        # No normattiva_client -> the urn branch is not entered, so no check.
        orch = CoVeOrchestrator()
        checks = await orch._validate_citations("Vedi urn:nir:stato:legge:2024;1 qui.")
        assert [c for c in checks if c.urn] == []

    async def test_unseeded_celex_live_check_when_eurlex_wired(self):
        # When an indexer exposes a .eurlex with metadata, an unseeded CELEX is
        # checked live instead of being marked unverified outright.
        meta = MagicMock()
        meta.title = "Some Regulation"
        meta.is_in_force = True
        meta.full_text_url = "https://eur-lex.europa.eu/some"
        eurlex = MagicMock()
        eurlex.fetch_regulation_metadata.return_value = meta
        indexer = MagicMock()
        indexer.eurlex = eurlex

        orch = CoVeOrchestrator(indexer=indexer)
        checks = await orch._validate_citations("Live check 39999L9999.")
        check = next(c for c in checks if c.celex == "39999L9999")
        assert check.exists is True
        assert check.validation == "verified"
        eurlex.fetch_regulation_metadata.assert_called_once_with("39999L9999")

    async def test_unseeded_celex_live_check_failure_marks_unverified(self):
        eurlex = MagicMock()
        eurlex.fetch_regulation_metadata.side_effect = RuntimeError("network down")
        indexer = MagicMock()
        indexer.eurlex = eurlex

        orch = CoVeOrchestrator(indexer=indexer)
        checks = await orch._validate_citations("Live check 39999L9999.")
        check = next(c for c in checks if c.celex == "39999L9999")
        assert check.exists is False
        assert check.validation == "unverified"
        assert "network down" in (check.error or "")

    async def test_unseeded_celex_live_check_missing_title_unverified(self):
        # eurlex returns metadata with no title -> exists False, unverified.
        meta = MagicMock()
        meta.title = None
        eurlex = MagicMock()
        eurlex.fetch_regulation_metadata.return_value = meta
        indexer = MagicMock()
        indexer.eurlex = eurlex

        orch = CoVeOrchestrator(indexer=indexer)
        checks = await orch._validate_citations("Live check 39999L9999.")
        check = next(c for c in checks if c.celex == "39999L9999")
        assert check.exists is False
        assert check.validation == "unverified"


# ------------------------------------------------------------------ #
#  _extract_claims                                                   #
# ------------------------------------------------------------------ #


class TestExtractClaims:
    async def test_short_text_returns_empty_without_llm(self):
        orch = CoVeOrchestrator()
        with _patch_llm(return_value=[{"text": "x"}]) as m:
            claims = await orch._extract_claims("short")
        assert claims == []
        # Guard short-circuits before any LLM call.
        m.assert_not_called()

    async def test_whitespace_only_text_returns_empty(self):
        orch = CoVeOrchestrator()
        with _patch_llm(return_value=[{"text": "x"}]):
            claims = await orch._extract_claims("          \n   ")
        assert claims == []

    async def test_list_result_builds_claims(self):
        payload = [
            {"text": "CSRD applies", "framework": "CSRD", "confidence": 0.9},
            {"text": "CSDDD applies", "framework": "CSDDD", "confidence": 0.8},
        ]
        orch = CoVeOrchestrator()
        with _patch_prompt(), _patch_llm(return_value=payload):
            claims = await orch._extract_claims("A long enough response text about CSRD.")
        assert [c.text for c in claims] == ["CSRD applies", "CSDDD applies"]
        assert claims[0].framework == "CSRD"
        assert claims[0].confidence == 0.9

    async def test_error_result_returns_empty(self):
        orch = CoVeOrchestrator()
        with _patch_prompt(), _patch_llm(return_value={"error": "llm exploded"}):
            claims = await orch._extract_claims("A long enough response text about CSRD.")
        assert claims == []

    async def test_dict_with_claims_key_is_unwrapped(self):
        payload = {"claims": [{"text": "CSRD applies"}]}
        orch = CoVeOrchestrator()
        with _patch_prompt(), _patch_llm(return_value=payload):
            claims = await orch._extract_claims("A long enough response text about CSRD.")
        assert len(claims) == 1
        assert claims[0].text == "CSRD applies"

    async def test_dict_with_text_key_returns_empty(self):
        # A bare {"text": ...} dict (no "claims") is treated as a non-list
        # answer and yields no claims.
        payload = {"text": "this is the answer, not a claim list"}
        orch = CoVeOrchestrator()
        with _patch_prompt(), _patch_llm(return_value=payload):
            claims = await orch._extract_claims("A long enough response text about CSRD.")
        assert claims == []

    async def test_max_claims_truncation(self):
        payload = [{"text": f"claim {i}"} for i in range(20)]
        orch = CoVeOrchestrator(config=CoVeConfig(max_claims=3))
        with _patch_prompt(), _patch_llm(return_value=payload):
            claims = await orch._extract_claims("A long enough response text about CSRD.")
        assert len(claims) == 3

    async def test_malformed_item_is_skipped(self):
        # confidence=2.0 is out of bounds -> Claim() raises -> item skipped,
        # the valid one survives.
        payload = [
            {"text": "bad one", "confidence": 2.0},
            {"text": "good one", "confidence": 0.5},
        ]
        orch = CoVeOrchestrator()
        with _patch_prompt(), _patch_llm(return_value=payload):
            claims = await orch._extract_claims("A long enough response text about CSRD.")
        assert [c.text for c in claims] == ["good one"]

    async def test_empty_text_field_item_dropped(self):
        payload = [{"text": ""}, {"text": "real claim"}]
        orch = CoVeOrchestrator()
        with _patch_prompt(), _patch_llm(return_value=payload):
            claims = await orch._extract_claims("A long enough response text about CSRD.")
        assert [c.text for c in claims] == ["real claim"]

    async def test_llm_exception_returns_empty(self):
        orch = CoVeOrchestrator()
        with _patch_prompt(), _patch_llm(side_effect=RuntimeError("network")):
            claims = await orch._extract_claims("A long enough response text about CSRD.")
        assert claims == []

    def test_real_load_prompt_loads_template_and_missing_raises(self):
        # With the fixed PROMPTS_DIR the REAL _load_prompt resolves the repo-root
        # prompts/ dir: a shipped template loads to a non-empty string, while a
        # genuinely-missing name still raises FileNotFoundError (the load happens
        # before _extract_claims' try block, so a real miss would propagate).
        from src.agents.cove.orchestrator import _load_prompt

        template = _load_prompt("cove_extract_claims")
        assert isinstance(template, str)
        assert template.strip()

        with pytest.raises(FileNotFoundError):
            _load_prompt("this_prompt_definitely_does_not_exist")


# ------------------------------------------------------------------ #
#  _plan_verification                                                #
# ------------------------------------------------------------------ #


class TestPlanVerification:
    async def test_empty_claims_returns_empty_plan(self):
        orch = CoVeOrchestrator()
        # No LLM call should happen for an empty claim list.
        with _patch_llm(return_value={"questions": []}) as m:
            plan = await orch._plan_verification([])
        assert plan.questions == []
        assert plan.estimated_time_seconds == 0.0
        m.assert_not_called()

    async def test_questions_key_unwrapped(self):
        claims = [Claim(text="CSRD applies"), Claim(text="CSDDD applies")]
        payload = {
            "questions": [
                {"claim_index": 0, "question": "Does CSRD apply?", "search_query": "csrd scope"},
                {"claim_index": 1, "question": "Does CSDDD apply?"},
            ]
        }
        orch = CoVeOrchestrator()
        with _patch_prompt(), _patch_llm(return_value=payload):
            plan = await orch._plan_verification(claims)
        assert len(plan.questions) == 2
        # search_query falls back to the question when absent.
        assert plan.questions[1].search_query == "Does CSDDD apply?"
        # estimated_time = 2s per question.
        assert plan.estimated_time_seconds == 4.0

    async def test_plans_key_unwrapped(self):
        claims = [Claim(text="CSRD applies")]
        payload = {"plans": [{"claim_index": 0, "question": "Does CSRD apply?"}]}
        orch = CoVeOrchestrator()
        with _patch_prompt(), _patch_llm(return_value=payload):
            plan = await orch._plan_verification(claims)
        assert len(plan.questions) == 1

    async def test_claim_index_clamped_to_valid_range(self):
        # An out-of-range claim_index from the LLM is clamped to len-1.
        claims = [Claim(text="only claim")]
        payload = {"questions": [{"claim_index": 99, "question": "Q?"}]}
        orch = CoVeOrchestrator()
        with _patch_prompt(), _patch_llm(return_value=payload):
            plan = await orch._plan_verification(claims)
        assert plan.questions[0].claim_index == 0

    async def test_empty_question_text_dropped(self):
        claims = [Claim(text="c0"), Claim(text="c1")]
        payload = {
            "questions": [
                {"claim_index": 0, "question": ""},
                {"claim_index": 1, "question": "real?"},
            ]
        }
        orch = CoVeOrchestrator()
        with _patch_prompt(), _patch_llm(return_value=payload):
            plan = await orch._plan_verification(claims)
        assert len(plan.questions) == 1
        assert plan.questions[0].question == "real?"

    async def test_error_result_returns_empty_plan(self):
        claims = [Claim(text="c0")]
        orch = CoVeOrchestrator()
        with _patch_prompt(), _patch_llm(return_value={"error": "boom"}):
            plan = await orch._plan_verification(claims)
        assert plan.questions == []
        assert plan.estimated_time_seconds == 0.0

    async def test_llm_exception_returns_empty_plan(self):
        claims = [Claim(text="c0")]
        orch = CoVeOrchestrator()
        with _patch_prompt(), _patch_llm(side_effect=RuntimeError("down")):
            plan = await orch._plan_verification(claims)
        assert plan.questions == []


# ------------------------------------------------------------------ #
#  _verify_claim                                                     #
# ------------------------------------------------------------------ #


class TestVerifyClaim:
    async def test_verified_claim_with_indexer_evidence(self):
        indexer = MagicMock()
        indexer.hybrid_search.return_value = [
            {"framework": "CSRD", "article_number": "19a", "text": "Large undertakings..."}
        ]
        orch = CoVeOrchestrator(indexer=indexer)
        claim = Claim(text="CSRD applies to large undertakings", framework="CSRD")
        question = VerificationQuestion(
            claim_index=0, question="Does CSRD apply?", search_query="csrd large"
        )
        llm_result = {"verified": True, "confidence": 0.95, "answer": "Confirmed by Art. 19a."}
        with _patch_prompt(), _patch_llm(return_value=llm_result):
            step = await orch._verify_claim(claim, question)
        assert step.verified is True
        assert step.confidence == 0.95
        assert step.discrepancy is None
        assert len(step.evidence_chunks) == 1
        # framework_filter is derived from the claim's framework.
        indexer.hybrid_search.assert_called_once()
        assert indexer.hybrid_search.call_args.kwargs["framework_filter"] == ["CSRD"]

    async def test_unverified_claim_records_discrepancy(self):
        orch = CoVeOrchestrator()  # no indexer
        claim = Claim(text="CSDDD deadline is 2026")
        question = VerificationQuestion(
            claim_index=2, question="When is the deadline?", search_query="csddd deadline"
        )
        llm_result = {
            "verified": False,
            "confidence": 0.2,
            "answer": "Evidence says 2028.",
            "discrepancy": "Claimed 2026 but actual is 2028.",
        }
        with _patch_prompt(), _patch_llm(return_value=llm_result):
            step = await orch._verify_claim(claim, question)
        assert step.verified is False
        assert step.discrepancy == "Claimed 2026 but actual is 2028."
        assert step.claim_index == 2
        # No indexer -> no evidence chunks.
        assert step.evidence_chunks == []

    async def test_no_indexer_uses_no_evidence(self):
        orch = CoVeOrchestrator()
        claim = Claim(text="some claim")
        question = VerificationQuestion(claim_index=0, question="Q?", search_query="q")
        with (
            _patch_prompt(),
            _patch_llm(return_value={"verified": True, "confidence": 0.5, "answer": "ok"}),
        ):
            step = await orch._verify_claim(claim, question)
        assert step.evidence_chunks == []

    async def test_indexer_search_exception_is_swallowed(self):
        indexer = MagicMock()
        indexer.hybrid_search.side_effect = RuntimeError("qdrant down")
        orch = CoVeOrchestrator(indexer=indexer)
        claim = Claim(text="some claim", framework="GDPR")
        question = VerificationQuestion(claim_index=0, question="Q?", search_query="q")
        with (
            _patch_prompt(),
            _patch_llm(return_value={"verified": True, "confidence": 0.7, "answer": "ok"}),
        ):
            step = await orch._verify_claim(claim, question)
        # Search failed gracefully -> no evidence, but verification still ran.
        assert step.evidence_chunks == []
        assert step.verified is True

    async def test_error_result_marks_unverified(self):
        orch = CoVeOrchestrator()
        claim = Claim(text="claim")
        question = VerificationQuestion(claim_index=0, question="Q?", search_query="q")
        with _patch_prompt(), _patch_llm(return_value={"error": "model failed"}):
            step = await orch._verify_claim(claim, question)
        assert step.verified is False
        assert step.confidence == 0.0
        assert step.discrepancy == "Verification failed"

    async def test_llm_exception_returns_error_step(self):
        orch = CoVeOrchestrator()
        claim = Claim(text="claim")
        question = VerificationQuestion(claim_index=3, question="Q?", search_query="q")
        with _patch_prompt(), _patch_llm(side_effect=RuntimeError("kaboom")):
            step = await orch._verify_claim(claim, question)
        assert step.verified is False
        assert step.confidence == 0.0
        assert step.claim_index == 3
        assert "kaboom" in step.answer
        assert "kaboom" in (step.discrepancy or "")

    async def test_answer_is_truncated_to_500_chars(self):
        orch = CoVeOrchestrator()
        claim = Claim(text="claim")
        question = VerificationQuestion(claim_index=0, question="Q?", search_query="q")
        long_answer = "x" * 1000
        with (
            _patch_prompt(),
            _patch_llm(return_value={"verified": True, "confidence": 0.6, "answer": long_answer}),
        ):
            step = await orch._verify_claim(claim, question)
        assert len(step.answer) == 500


# ------------------------------------------------------------------ #
#  _revise_draft                                                     #
# ------------------------------------------------------------------ #


class TestReviseDraft:
    def _draft(self):
        return DraftResult(text="Original answer text.", claims=[], raw_json={}, confidence=0.6)

    async def test_no_verifications_returns_draft_unchanged(self):
        orch = CoVeOrchestrator()
        draft = self._draft()
        # No LLM call should happen when there is nothing verified.
        with _patch_llm(return_value={"revised_response": "should not be used"}) as m:
            revision = await orch._revise_draft(draft, [])
        assert revision.revised_text == draft.text
        assert revision.original_text == draft.text
        assert revision.changes_made == []
        assert revision.confidence == draft.confidence
        m.assert_not_called()

    async def test_revision_counts_corrected_and_removed(self):
        orch = CoVeOrchestrator()
        draft = self._draft()
        verifications = [
            VerificationStep(
                claim_index=0,
                claim=Claim(text="c0"),
                question="q0",
                answer="a0",
                verified=True,
                confidence=0.9,
            ),
            VerificationStep(
                claim_index=1,
                claim=Claim(text="c1"),
                question="q1",
                answer="a1",
                verified=False,
                confidence=0.2,
                discrepancy="wrong date",
            ),
        ]
        llm_result = {
            "revised_response": "Corrected answer.",
            "changes_made": ["fixed date"],
            "confidence": 0.88,
        }
        with _patch_prompt(), _patch_llm(return_value=llm_result):
            revision = await orch._revise_draft(draft, verifications)
        assert revision.revised_text == "Corrected answer."
        assert revision.claims_corrected == 1  # one verified
        assert revision.claims_removed == 1  # one unverified
        assert revision.changes_made == ["fixed date"]
        assert revision.confidence == 0.88

    async def test_error_result_falls_back_to_draft(self):
        orch = CoVeOrchestrator()
        draft = self._draft()
        verifications = [
            VerificationStep(
                claim_index=0,
                claim=Claim(text="c0"),
                question="q0",
                answer="a0",
                verified=True,
                confidence=0.9,
            )
        ]
        with _patch_prompt(), _patch_llm(return_value={"error": "revision model failed"}):
            revision = await orch._revise_draft(draft, verifications)
        assert revision.revised_text == draft.text
        # Confidence is degraded by 0.8 factor on error.
        assert revision.confidence == pytest.approx(draft.confidence * 0.8)
        assert any("Revision failed" in c for c in revision.changes_made)

    async def test_llm_exception_falls_back_to_draft(self):
        orch = CoVeOrchestrator()
        draft = self._draft()
        verifications = [
            VerificationStep(
                claim_index=0,
                claim=Claim(text="c0"),
                question="q0",
                answer="a0",
                verified=True,
                confidence=0.9,
            )
        ]
        with _patch_prompt(), _patch_llm(side_effect=RuntimeError("explode")):
            revision = await orch._revise_draft(draft, verifications)
        assert revision.revised_text == draft.text
        assert revision.confidence == draft.confidence
        assert any("Revision error" in c for c in revision.changes_made)


# ------------------------------------------------------------------ #
#  run() generator - early / guard branches                          #
# ------------------------------------------------------------------ #


async def _collect(agen):
    return [event async for event in agen]


class TestRunGenerator:
    async def test_no_claims_skips_to_validation_only(self):
        # When _extract_claims yields nothing, run() must short-circuit to a
        # citations-only pass and emit a DoneEvent with cove_applied=False.
        orch = CoVeOrchestrator()
        draft_state = {
            "result_json": '{"answer": "CSRD applies per 32022L2464.", "confidence_score": 0.8}'
        }
        with patch.object(orch, "_extract_claims", AsyncMock(return_value=[])):
            events = await _collect(orch.run(draft_state, "qa"))

        phases = [e for e in events if isinstance(e, PhaseChangeEvent)]
        assert phases[0].phase == "draft"
        assert any(p.phase == "validation" for p in phases)

        done = [e for e in events if isinstance(e, DoneEvent)]
        assert len(done) == 1
        assert done[0].cove_applied is False
        # The seeded CELEX should have been validated along the way (no crash).
        assert done[0].confidence_score == pytest.approx(0.8)

    async def test_invalid_result_json_is_tolerated(self):
        # A non-JSON result_json should not crash run(); it gets wrapped.
        orch = CoVeOrchestrator()
        draft_state = {"result_json": "this is not json at all"}
        with patch.object(orch, "_extract_claims", AsyncMock(return_value=[])):
            events = await _collect(orch.run(draft_state, "qa"))
        done = [e for e in events if isinstance(e, DoneEvent)]
        assert len(done) == 1
        assert done[0].cove_applied is False
        # No ErrorEvent for a recoverable parse fallback.
        assert not [e for e in events if isinstance(e, ErrorEvent)]

    async def test_dict_result_json_supported(self):
        # result_json may already be a dict (not a JSON string).
        orch = CoVeOrchestrator()
        draft_state = {"result_json": {"answer": "Plain answer.", "confidence_score": 0.55}}
        with patch.object(orch, "_extract_claims", AsyncMock(return_value=[])):
            events = await _collect(orch.run(draft_state, "qa"))
        done = [e for e in events if isinstance(e, DoneEvent)]
        assert done[0].confidence_score == pytest.approx(0.55)

    async def test_full_pipeline_happy_path_emits_revised_text(self):
        # Drive the full 5-phase path with every LLM-bound helper mocked.
        orch = CoVeOrchestrator(config=CoVeConfig(enabled=True))

        claims = [Claim(text="CSRD applies", framework="CSRD")]
        from src.agents.cove.models import VerificationPlan

        plan = VerificationPlan(
            questions=[
                VerificationQuestion(
                    claim_index=0, question="Does CSRD apply?", search_query="csrd"
                )
            ],
            estimated_time_seconds=2.0,
        )
        verified_step = VerificationStep(
            claim_index=0,
            claim=claims[0],
            question="Does CSRD apply?",
            answer="Confirmed.",
            verified=True,
            confidence=0.95,
        )
        from src.agents.cove.models import RevisionResult

        revision = RevisionResult(
            original_text="DRAFT",
            revised_text="VERIFIED answer with checked citations.",
            changes_made=["tightened"],
            claims_corrected=1,
            claims_removed=0,
            confidence=0.9,
        )

        with (
            patch.object(orch, "_extract_claims", AsyncMock(return_value=claims)),
            patch.object(orch, "_plan_verification", AsyncMock(return_value=plan)),
            patch.object(orch, "_verify_claim", AsyncMock(return_value=verified_step)),
            patch.object(orch, "_revise_draft", AsyncMock(return_value=revision)),
            patch.object(orch, "_validate_citations", AsyncMock(return_value=[])),
        ):
            draft_state = {"result_json": '{"answer": "DRAFT", "confidence_score": 0.5}'}
            events = await _collect(orch.run(draft_state, "qa"))

        # All five phase-change events should be present.
        phases = [e.phase for e in events if isinstance(e, PhaseChangeEvent)]
        assert phases == ["draft", "planning", "verification", "revision", "validation"]

        # Verification start/result events emitted for the single claim.
        assert any(isinstance(e, VerificationStartEvent) for e in events)
        assert any(isinstance(e, VerificationResultEvent) for e in events)

        done = [e for e in events if isinstance(e, DoneEvent)]
        assert len(done) == 1
        assert done[0].cove_applied is True
        assert done[0].revised_text == "VERIFIED answer with checked citations."
        # final_confidence = (1/1)*0.7 + 0.9*0.3 = 0.97
        assert done[0].confidence_score == pytest.approx(0.97)
        assert done[0].requires_review is False

    async def test_invalid_citation_forces_review(self):
        # An invalid citation in the validation phase must flip requires_review.
        from src.agents.cove.models import CitationCheck, RevisionResult, VerificationPlan

        orch = CoVeOrchestrator(config=CoVeConfig(enabled=True))
        claims = [Claim(text="claim")]
        plan = VerificationPlan(
            questions=[VerificationQuestion(claim_index=0, question="Q?", search_query="q")],
            estimated_time_seconds=2.0,
        )
        step = VerificationStep(
            claim_index=0,
            claim=claims[0],
            question="Q?",
            answer="a",
            verified=True,
            confidence=0.95,
        )
        revision = RevisionResult(
            original_text="d", revised_text="revised text body", confidence=0.95
        )
        bad_citation = CitationCheck(celex="39999L9999", exists=False, is_current=False)

        with (
            patch.object(orch, "_extract_claims", AsyncMock(return_value=claims)),
            patch.object(orch, "_plan_verification", AsyncMock(return_value=plan)),
            patch.object(orch, "_verify_claim", AsyncMock(return_value=step)),
            patch.object(orch, "_revise_draft", AsyncMock(return_value=revision)),
            patch.object(orch, "_validate_citations", AsyncMock(return_value=[bad_citation])),
        ):
            events = await _collect(orch.run({"result_json": '{"answer": "d"}'}, "qa"))
        done = [e for e in events if isinstance(e, DoneEvent)][0]
        # invalid_citations > 0 -> review required even though confidence is high.
        assert done.requires_review is True

    async def test_skip_citation_check_config_bypasses_validation(self):
        from src.agents.cove.models import RevisionResult, VerificationPlan

        orch = CoVeOrchestrator(config=CoVeConfig(enabled=True, skip_citation_check=True))
        claims = [Claim(text="claim")]
        plan = VerificationPlan(
            questions=[VerificationQuestion(claim_index=0, question="Q?", search_query="q")],
            estimated_time_seconds=2.0,
        )
        step = VerificationStep(
            claim_index=0,
            claim=claims[0],
            question="Q?",
            answer="a",
            verified=True,
            confidence=0.9,
        )
        revision = RevisionResult(original_text="d", revised_text="revised body", confidence=0.9)
        validate_mock = AsyncMock(return_value=[])

        with (
            patch.object(orch, "_extract_claims", AsyncMock(return_value=claims)),
            patch.object(orch, "_plan_verification", AsyncMock(return_value=plan)),
            patch.object(orch, "_verify_claim", AsyncMock(return_value=step)),
            patch.object(orch, "_revise_draft", AsyncMock(return_value=revision)),
            patch.object(orch, "_validate_citations", validate_mock),
        ):
            events = await _collect(orch.run({"result_json": '{"answer": "d"}'}, "qa"))
        # Citation validation must be skipped entirely.
        validate_mock.assert_not_called()
        assert any(isinstance(e, DoneEvent) for e in events)

    async def test_verification_timeout_emits_recoverable_error(self):
        from src.agents.cove.models import RevisionResult, VerificationPlan

        # timeout_per_phase_seconds is tiny; _verify_claim sleeps past it.
        orch = CoVeOrchestrator(config=CoVeConfig(enabled=True, timeout_per_phase_seconds=0.01))
        claims = [Claim(text="claim")]
        plan = VerificationPlan(
            questions=[VerificationQuestion(claim_index=0, question="Q?", search_query="q")],
            estimated_time_seconds=2.0,
        )

        async def slow_verify(*_args, **_kwargs):
            import asyncio

            await asyncio.sleep(1.0)
            raise AssertionError("should have timed out")

        revision = RevisionResult(original_text="d", revised_text="revised body", confidence=0.5)

        with (
            patch.object(orch, "_extract_claims", AsyncMock(return_value=claims)),
            patch.object(orch, "_plan_verification", AsyncMock(return_value=plan)),
            patch.object(orch, "_verify_claim", side_effect=slow_verify),
            patch.object(orch, "_revise_draft", AsyncMock(return_value=revision)),
            patch.object(orch, "_validate_citations", AsyncMock(return_value=[])),
        ):
            events = await _collect(orch.run({"result_json": '{"answer": "d"}'}, "qa"))

        errors = [e for e in events if isinstance(e, ErrorEvent)]
        assert any("timeout" in e.message.lower() and e.recoverable for e in errors)
        # Pipeline still completes through to a DoneEvent (graceful degradation).
        assert any(isinstance(e, DoneEvent) for e in events)

    async def test_verification_error_emits_recoverable_error(self):
        from src.agents.cove.models import RevisionResult, VerificationPlan

        orch = CoVeOrchestrator(config=CoVeConfig(enabled=True))
        claims = [Claim(text="claim")]
        plan = VerificationPlan(
            questions=[VerificationQuestion(claim_index=0, question="Q?", search_query="q")],
            estimated_time_seconds=2.0,
        )
        revision = RevisionResult(original_text="d", revised_text="revised body", confidence=0.5)

        with (
            patch.object(orch, "_extract_claims", AsyncMock(return_value=claims)),
            patch.object(orch, "_plan_verification", AsyncMock(return_value=plan)),
            patch.object(orch, "_verify_claim", AsyncMock(side_effect=ValueError("verify boom"))),
            patch.object(orch, "_revise_draft", AsyncMock(return_value=revision)),
            patch.object(orch, "_validate_citations", AsyncMock(return_value=[])),
        ):
            events = await _collect(orch.run({"result_json": '{"answer": "d"}'}, "qa"))

        errors = [e for e in events if isinstance(e, ErrorEvent)]
        assert any("verify boom" in e.message and e.recoverable for e in errors)

    async def test_unhandled_exception_emits_fatal_error(self):
        # An exception thrown before claims are extracted bubbles into the
        # outer except, emitting a non-recoverable ErrorEvent.
        orch = CoVeOrchestrator()
        with patch.object(orch, "_extract_claims", AsyncMock(side_effect=RuntimeError("fatal"))):
            events = await _collect(orch.run({"result_json": '{"answer": "x"}'}, "qa"))
        errors = [e for e in events if isinstance(e, ErrorEvent)]
        assert len(errors) == 1
        assert errors[0].recoverable is False
        assert "fatal" in errors[0].message
