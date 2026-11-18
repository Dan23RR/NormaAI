"""Tests for the LangGraph node functions in src/agents/nodes.py.

Focus: each node's *pure* transformation of the AgentState dict, with all
external dependencies mocked (LLM via call_llm/acall_llm, retrieval via the
indexer's hybrid_search). No real network / LLM / Qdrant / DB is touched.

Complements tests/test_agents.py (route_to_agent, json/confidence/chunk helpers)
and tests/test_local_router.py (complexity_gate_branch, aroute_query) without
duplicating them. Here we cover:

  - retrieve_node: empty-query guard, single/multi-framework search dispatch,
    profile-frameworks fallback, org_id propagation, exception handling
  - the grounding guard (_apply_grounding_guard) and _pack_llm_result
  - the prompt builders (_build_monitor_prompt / _build_gap_prompt /
    _build_qa_prompt) including the injection guard prefix
  - sync agent nodes (monitor/gap/qa) wired to a mocked call_llm
  - async agent nodes wired to a mocked acall_llm
  - confidence_check_node, async_local_router_node, async_simple_response_node
  - _load_prompt (real prompts dir resolves correctly) + detect_frameworks_in_query
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents import nodes
from src.agents.nodes import (
    _INJECTION_GUARD,
    RETRIEVAL_ERROR_PREFIX,
    _apply_grounding_guard,
    _build_gap_prompt,
    _build_monitor_prompt,
    _build_qa_prompt,
    _load_prompt,
    _pack_llm_result,
    async_gap_analyst_node,
    async_local_router_node,
    async_monitor_agent_node,
    async_qa_bot_node,
    async_simple_response_node,
    citation_grounding_rate,
    confidence_check_node,
    detect_frameworks_in_query,
    gap_analyst_node,
    monitor_agent_node,
    qa_bot_node,
    retrieve_node,
)

# ─── Helpers ──────────────────────────────────────────────────────

# One retrieved passage: the Q&A agent asks the model only when it has at least one.
_A_PASSAGE = {
    "id": "pt-gdpr-5",
    "text": (
        "Article 5\nPrinciples relating to processing of personal data\n1. Personal data shall "
        "be processed lawfully, fairly and in a transparent manner in relation to the data subject."
    ),
    "framework": "GDPR",
    "celex": "32016R0679",
    "article": "Art. 5",
    "lang": "EN",
}


def _indexer_returning(results):
    """Build a mock indexer whose hybrid_search returns `results`."""
    indexer = MagicMock()
    indexer.hybrid_search.return_value = results
    return indexer


# ─── detect_frameworks_in_query ───────────────────────────────────


class TestDetectFrameworks:
    def test_detects_single_english(self):
        assert detect_frameworks_in_query("Tell me about the AI Act") == ["AI_ACT"]

    def test_detects_italian_keyword(self):
        # "protezione dei dati" -> GDPR (Italian keyword path)
        assert "GDPR" in detect_frameworks_in_query("Parlami della protezione dei dati personali")

    def test_detects_multiple(self):
        out = detect_frameworks_in_query("How does DORA interact with NIS2?")
        assert "DORA" in out and "NIS2" in out

    def test_no_match_returns_empty(self):
        assert detect_frameworks_in_query("What is the weather today?") == []

    def test_case_insensitive(self):
        assert detect_frameworks_in_query("CSRD AND csrd") == ["CSRD"]

    @pytest.mark.parametrize(
        "question",
        [
            "La burocrazia per i fornitori è eccessiva?",
            "Chi adora i registri dei trattamenti?",
            "Lo scraping di immagini dal web è lecito?",
            "In una democrazia chi controlla le autorità?",
        ],
    )
    def test_a_name_inside_another_word_does_not_count(self, question):
        # Matched as substrings, "burocrazia" and "democrazia" named the CRA,
        # "adora" DORA and "scraping" the CRA.
        assert detect_frameworks_in_query(question) == []

    def test_the_same_names_as_whole_words_count(self):
        assert detect_frameworks_in_query("La burocrazia del CRA") == ["CRA"]
        assert detect_frameworks_in_query("Chi adora il DORA?") == ["DORA"]

    @pytest.mark.parametrize(
        "question, framework",
        [
            ("Cosa prevede l'AI Act?", "AI_ACT"),
            ("Obblighi dell'AI-Act per i deployer", "AI_ACT"),
            ("Il Regolamento IA si applica alle PMI?", "AI_ACT"),
            ("Cosa dice il regolamento sull’IA?", "AI_ACT"),
            ("Il DORA si applica agli intermediari?", "DORA"),
            ("La direttiva NIS 2 e i soggetti importanti", "NIS2"),
            ("NIS-2: termini di notifica", "NIS2"),
            ("NIS2 incident reporting", "NIS2"),
            ("Le RGPD s'applique-t-il ?", "GDPR"),
            ("Il GDPR e i cookie", "GDPR"),
            ("CS3D scope after Omnibus I", "CSDDD"),
            ("Il regolamento sulla ciberresilienza", "CRA"),
        ],
    )
    def test_known_names_and_spellings(self, question, framework):
        assert detect_frameworks_in_query(question) == [framework]

    def test_accents_and_apostrophes_do_not_matter(self):
        for spelling in (
            "rendicontazione di sostenibilità",
            "rendicontazione di sostenibilita",
            "rendicontazione di sostenibilita'",
            "RENDICONTAZIONE DI SOSTENIBILITÀ",
        ):
            assert detect_frameworks_in_query(f"Chi deve fare la {spelling}?") == ["CSRD"]

    @pytest.mark.parametrize(
        "question, framework",
        [
            ("Come si protegge un dato personale?", "GDPR"),
            ("Come si proteggono i dati personali?", "GDPR"),
            ("Chi gestisce i rischi informatici?", "DORA"),
            ("Chi gestisce il rischio informatico?", "DORA"),
            ("È un'infrastruttura critica?", "NIS2"),
            ("Un prodotto con elementi digitali va marcato?", "CRA"),
            ("Le catene di fornitura extra UE", "CSDDD"),
        ],
    )
    def test_singular_and_plural(self, question, framework):
        assert detect_frameworks_in_query(question) == [framework]

    def test_nis3_is_not_nis2(self):
        assert detect_frameworks_in_query("Cosa cambia con la NIS3?") == []

    @pytest.mark.parametrize(
        "golden_id, question, expected",
        [
            (
                "aiact-005-002",
                "È consentito creare o ampliare una banca dati di riconoscimento facciale "
                "tramite scraping non mirato di immagini dal web secondo l'AI Act?",
                ["AI_ACT"],  # was ["AI_ACT", "CRA"]: "scraping" contains "cra"
            ),
            (
                "refuse-009",
                "What does the NIS3 Directive change compared to NIS2?",
                ["NIS2"],
            ),
            (
                "dora-005-001",
                "Chi ha la responsabilità finale della gestione dei rischi informatici in "
                "un'entità finanziaria secondo il DORA?",
                ["DORA"],
            ),
            (
                "cra-014-001",
                "A chi deve notificare un fabbricante una vulnerabilità attivamente sfruttata "
                "in un prodotto con elementi digitali ai sensi dell'art. 14 del Cyber "
                "Resilience Act?",
                ["CRA"],
            ),
            (
                "gdpr-033-001",
                "Entro quanto tempo il titolare deve notificare una violazione dei dati "
                "personali all'autorità di controllo?",
                ["GDPR"],
            ),
            (
                "tax-003-002",
                "Quale condizione relativa alle «garanzie minime di salvaguardia» deve "
                "rispettare un'attività per essere ecosostenibile secondo il regolamento "
                "Tassonomia?",
                ["TAXONOMY"],
            ),
            (
                "nis2-021-003",
                "La direttiva NIS2 richiede l'uso dell'autenticazione a più fattori?",
                ["NIS2"],
            ),
            (
                "csddd-002-003",
                "La CSDDD si applica a una società che supera le soglie dell'art. 2 per un "
                "solo esercizio?",
                ["CSDDD"],
            ),
            (
                "csrd-19a-002",
                "After Omnibus I, which size thresholds trigger individual sustainability "
                "reporting under Article 19a(1) of the Accounting Directive?",
                [],  # names the act by its common name only: no framework, as before
            ),
            (
                "aiact-026-001",
                "Per quanto tempo il deployer di un sistema di IA ad alto rischio deve "
                "conservare i log generati automaticamente dal sistema?",
                [],
            ),
        ],
    )
    def test_golden_v2_questions(self, golden_id, question, expected):
        # Real questions of tests/validation/test_cases/golden_v2.jsonl: of the 101,
        # only aiact-005-002 is detected differently from the substring matching.
        assert detect_frameworks_in_query(question) == expected, golden_id


# ─── _load_prompt (real prompts dir) ──────────────────────────────


class TestLoadPrompt:
    def test_loads_existing_prompt(self):
        # nodes.py at src/agents/ resolves 3 parents up to the repo-root prompts/.
        text = _load_prompt("qa_bot")
        assert isinstance(text, str)
        assert len(text) > 0

    def test_missing_prompt_raises(self):
        with pytest.raises(FileNotFoundError):
            _load_prompt("definitely_not_a_real_prompt_xyz")


# ─── retrieve_node ────────────────────────────────────────────────


class TestRetrieveNode:
    def test_empty_query_short_circuits(self):
        out = retrieve_node({"query": ""})
        assert out["retrieved_chunks"] == []
        assert out["error"] == "No query provided"

    def test_single_framework_uses_filter(self):
        chunks = [{"id": "1", "framework": "CSRD", "text": "x", "score": 0.9}]
        indexer = _indexer_returning(chunks)
        with patch("src.api.app_state.app_state.indexer", indexer):
            out = retrieve_node({"query": "What does CSRD require?"})
        assert out["retrieved_chunks"] == chunks
        # detected framework -> single search with that framework_filter
        indexer.hybrid_search.assert_called_once()
        _, kwargs = indexer.hybrid_search.call_args
        assert kwargs["framework_filter"] == "CSRD"
        assert kwargs["limit"] == 15
        assert kwargs["depth"] == 45  # 3 x limit, the search's own default

    def test_no_framework_detected_passes_none_filter(self):
        indexer = _indexer_returning([])
        with patch("src.api.app_state.app_state.indexer", indexer):
            retrieve_node({"query": "Tell me something general"})
        _, kwargs = indexer.hybrid_search.call_args
        assert kwargs["framework_filter"] is None

    def test_org_id_propagated_to_search(self):
        indexer = _indexer_returning([])
        with patch("src.api.app_state.app_state.indexer", indexer):
            retrieve_node({"query": "CSRD requirements", "org_id": "org-123"})
        _, kwargs = indexer.hybrid_search.call_args
        assert kwargs["org_id"] == "org-123"

    def test_org_id_defaults_to_none(self):
        indexer = _indexer_returning([])
        with patch("src.api.app_state.app_state.indexer", indexer):
            retrieve_node({"query": "CSRD requirements"})
        _, kwargs = indexer.hybrid_search.call_args
        assert kwargs["org_id"] is None

    def test_profile_single_framework_fallback(self):
        # No framework detected in query, but profile lists exactly one ->
        # that one is used as the filter.
        indexer = _indexer_returning([])
        state = {
            "query": "Generic question without keywords",
            "company_profile": {"applicable_frameworks": ["DORA"]},
        }
        with patch("src.api.app_state.app_state.indexer", indexer):
            retrieve_node(state)
        _, kwargs = indexer.hybrid_search.call_args
        assert kwargs["framework_filter"] == "DORA"

    def test_multi_framework_dedups_and_sorts(self):
        # Two detected frameworks -> per-framework searches, dedup by id,
        # results sorted by descending score.
        def per_fw(query, limit, depth, framework_filter, org_id):
            if framework_filter == "DORA":
                return [
                    {"id": "a", "score": 0.4},
                    {"id": "shared", "score": 0.5},
                ]
            return [
                {"id": "b", "score": 0.9},
                {"id": "shared", "score": 0.99},  # duplicate id, dropped
            ]

        indexer = MagicMock()
        indexer.hybrid_search.side_effect = per_fw
        with patch("src.api.app_state.app_state.indexer", indexer):
            out = retrieve_node({"query": "How does DORA relate to NIS2?"})

        ids = [c["id"] for c in out["retrieved_chunks"]]
        # 'shared' appears once (dedup); first-seen kept.
        assert ids.count("shared") == 1
        # Sorted by score descending.
        scores = [c["score"] for c in out["retrieved_chunks"]]
        assert scores == sorted(scores, reverse=True)
        # One search per detected framework, 7 results from the 21 of each retriever.
        assert indexer.hybrid_search.call_count == 2
        calls = indexer.hybrid_search.call_args_list
        assert [(c.kwargs["limit"], c.kwargs["depth"]) for c in calls] == [(7, 21), (7, 21)]

    def test_detected_frameworks_from_router_preferred(self):
        # state['detected_frameworks'] (from local router) overrides keyword
        # detection on the query.
        indexer = _indexer_returning([])
        state = {
            "query": "this text mentions GDPR explicitly",
            "detected_frameworks": ["AI_ACT"],
        }
        with patch("src.api.app_state.app_state.indexer", indexer):
            retrieve_node(state)
        _, kwargs = indexer.hybrid_search.call_args
        assert kwargs["framework_filter"] == "AI_ACT"

    def test_search_exception_returns_error(self):
        indexer = MagicMock()
        indexer.hybrid_search.side_effect = RuntimeError("qdrant down")
        with patch("src.api.app_state.app_state.indexer", indexer):
            out = retrieve_node({"query": "CSRD requirements"})
        assert out["retrieved_chunks"] == []
        assert "Knowledge base retrieval failed" in out["error"]
        assert "qdrant down" in out["error"]

    def test_search_exception_writes_honest_failure_payload(self):
        # The failure IS the result: result_json carries the machine-readable
        # code the HTTP layer maps to 503, with zero confidence + review.
        indexer = MagicMock()
        indexer.hybrid_search.side_effect = RuntimeError("qdrant down")
        with patch("src.api.app_state.app_state.indexer", indexer):
            out = retrieve_node({"query": "CSRD requirements"})
        payload = json.loads(out["result_json"])
        assert payload["error_code"] == "retrieval_unavailable"
        assert payload["confidence_score"] == 0.0
        assert payload["requires_expert_review"] is True
        assert out["confidence_score"] == 0.0
        assert out["requires_review"] is True


class TestRetrieveNodeWithReranker:
    """RERANKER_MODEL_DIR set: more candidates, the fused best 15 (20) reach the agents."""

    @staticmethod
    def _scorer(scores=None, error=None):
        scorer = MagicMock()
        if error is not None:
            scorer.score.side_effect = error
        else:
            scorer.score.side_effect = lambda query, passages: (
                scores if scores is not None else [0.0] * len(passages)
            )
        return scorer

    def test_asks_for_more_candidates_and_keeps_the_fused_best(self):
        chunks = [{"id": str(i), "text": f"t{i}", "score": 1.0 - i / 100} for i in range(30)]
        scores = [-float(i) for i in range(30)]
        scores[25] = 100.0  # the cross-encoder's pick, 26th for the hybrid search
        indexer = _indexer_returning(chunks)
        with (
            patch("src.api.app_state.app_state.indexer", indexer),
            patch("src.api.app_state.app_state.reranker", self._scorer(scores)),
        ):
            out = retrieve_node({"query": "What does CSRD require?"})

        _, kwargs = indexer.hybrid_search.call_args
        assert (kwargs["limit"], kwargs["depth"]) == (30, 90)
        ids = [c["id"] for c in out["retrieved_chunks"]]
        assert len(ids) == 15
        assert ids[0] == "0"
        assert "25" in ids

    @staticmethod
    def _per_fw(query, limit, depth, framework_filter, org_id):
        return [
            {"id": f"{framework_filter}-{i}", "text": "x", "score": 1.0 - i / 100}
            for i in range(limit)
        ]

    def test_several_frameworks_split_the_candidates_and_keep_20(self):
        indexer = MagicMock()
        indexer.hybrid_search.side_effect = self._per_fw
        with (
            patch("src.api.app_state.app_state.indexer", indexer),
            patch("src.api.app_state.app_state.reranker", self._scorer()),
        ):
            out = retrieve_node({"query": "How does DORA relate to NIS2?"})

        calls = indexer.hybrid_search.call_args_list
        assert [(c.kwargs["limit"], c.kwargs["depth"]) for c in calls] == [(15, 45), (15, 45)]
        assert len(out["retrieved_chunks"]) == 20

    def test_search_depth_45_extends_the_ranking_without_reranker(self):
        # RERANKER_SEARCH_DEPTH=45 fuses as many results as the search without a
        # reranker, so the candidates start with the chunks it would return.
        from src.config import get_settings

        shallow = get_settings().model_copy(update={"reranker_search_depth": 45})
        single, multi = _indexer_returning([]), MagicMock()
        multi.hybrid_search.side_effect = self._per_fw
        with (
            patch("src.config.get_settings", return_value=shallow),
            patch("src.api.app_state.app_state.reranker", self._scorer()),
        ):
            with patch("src.api.app_state.app_state.indexer", single):
                retrieve_node({"query": "What does CSRD require?"})
            with patch("src.api.app_state.app_state.indexer", multi):
                retrieve_node({"query": "How does DORA relate to NIS2?"})

        _, kwargs = single.hybrid_search.call_args
        assert (kwargs["limit"], kwargs["depth"]) == (30, 45)
        calls = multi.hybrid_search.call_args_list
        assert [(c.kwargs["limit"], c.kwargs["depth"]) for c in calls] == [(15, 21), (15, 21)]

    def test_a_failing_reranker_keeps_the_hybrid_order(self):
        chunks = [{"id": str(i), "text": "x", "score": 1.0 - i / 100} for i in range(30)]
        indexer = _indexer_returning(chunks)
        with (
            patch("src.api.app_state.app_state.indexer", indexer),
            patch("src.api.app_state.app_state.reranker", self._scorer(error=RuntimeError("onnx"))),
        ):
            out = retrieve_node({"query": "What does CSRD require?"})

        assert "error" not in out
        assert [c["id"] for c in out["retrieved_chunks"]] == [str(i) for i in range(15)]


# ─── Agents skip the LLM when the knowledge base failed ──────────


class TestAgentsSkipOnRetrievalFailure:
    _FAILED_STATE = {
        "query": "q",
        "task_type": "qa",
        "error": f"{nodes.RETRIEVAL_ERROR_PREFIX}: qdrant down",
        "retrieved_chunks": [],
        "result_json": json.dumps({"error": "x", "error_code": "retrieval_unavailable"}),
    }

    def test_sync_agents_do_not_call_llm(self):
        with patch.object(nodes, "call_llm") as llm:
            assert qa_bot_node(dict(self._FAILED_STATE)) == {}
            assert gap_analyst_node(dict(self._FAILED_STATE)) == {}
            assert monitor_agent_node(dict(self._FAILED_STATE)) == {}
        llm.assert_not_called()

    async def test_async_agents_do_not_call_llm(self):
        with patch.object(nodes, "acall_llm", new=AsyncMock()) as llm:
            assert await async_qa_bot_node(dict(self._FAILED_STATE)) == {}
            assert await async_gap_analyst_node(dict(self._FAILED_STATE)) == {}
            assert await async_monitor_agent_node(dict(self._FAILED_STATE)) == {}
        llm.assert_not_awaited()

    def test_other_errors_do_not_block_the_agent(self):
        # Only a retrieval failure short-circuits; e.g. the empty-query marker
        # must not stop the agent from running.
        llm_result = {"answer": "ok", "confidence_score": 0.9, "citations": []}
        state = {"query": "", "error": "No query provided", "retrieved_chunks": [_A_PASSAGE]}
        with patch.object(nodes, "call_llm", return_value=llm_result):
            out = qa_bot_node(state)
        assert json.loads(out["result_json"])["answer"] == "ok"

    def test_pack_llm_result_mirrors_llm_error_into_state(self):
        out = _pack_llm_result(
            {"error": "LLM error (gemini): boom", "error_code": "llm_provider_error"}
        )
        assert out["error"] == "LLM error (gemini): boom"
        assert out["confidence_score"] == 0.0
        assert out["requires_review"] is True
        # A real answer does not touch the error channel.
        assert "error" not in _pack_llm_result({"answer": "x", "confidence_score": 0.9})


# ─── _apply_grounding_guard ───────────────────────────────────────


class TestGroundingGuard:
    def test_non_dict_returned_unchanged(self):
        assert _apply_grounding_guard("not a dict", []) == "not a dict"

    def test_grounded_citation_not_flagged(self):
        chunks = [{"framework": "CSRD", "text": "x"}]
        result = {
            "answer": "ok",
            "citations": [{"framework": "CSRD"}],
            "confidence_score": 0.9,
        }
        out = _apply_grounding_guard(result, chunks)
        assert "grounding_warning" not in out
        assert out["confidence_score"] == 0.9

    def test_ungrounded_framework_citation_flags_and_caps(self):
        chunks = [{"framework": "CSRD", "text": "x"}]
        result = {
            "answer": "ok",
            "citations": [{"framework": "GDPR"}],  # not in retrieved sources
            "confidence_score": 0.95,
        }
        out = _apply_grounding_guard(result, chunks)
        assert out["requires_expert_review"] is True
        assert "grounding_warning" in out
        # Confidence capped at 0.6.
        assert out["confidence_score"] == 0.6

    def test_citations_with_no_chunks_are_ungrounded(self):
        # Nothing retrieved but model produced citations -> all ungrounded.
        result = {
            "answer": "ok",
            "citations": [{"framework": "GDPR"}, {"framework": "CSRD"}],
            "confidence_score": 0.9,
        }
        out = _apply_grounding_guard(result, [])
        assert out["requires_expert_review"] is True
        assert "2 citation" in out["grounding_warning"]

    def test_ungrounded_celex_in_answer_flagged(self):
        chunks = [{"framework": "GDPR", "celex": "32016R0679"}]
        result = {
            # CELEX 32024R1234 appears in the answer but is not in retrieved celex set.
            "answer": "See 32024R1234 for details.",
            "citations": [],
            "confidence_score": 0.9,
        }
        out = _apply_grounding_guard(result, chunks)
        assert out["requires_expert_review"] is True

    def test_grounded_celex_in_answer_not_flagged(self):
        chunks = [{"framework": "GDPR", "celex": "32016R0679"}]
        result = {
            "answer": "Per 32016R0679 the rules apply.",
            "citations": [{"framework": "GDPR"}],
            "confidence_score": 0.9,
        }
        out = _apply_grounding_guard(result, chunks)
        assert "grounding_warning" not in out

    def test_grounded_article_reference_not_flagged(self):
        # The cited article number IS present in the retrieved chunk text -> ok.
        chunks = [
            {
                "framework": "GDPR",
                "text": "Articolo 17 Diritto alla cancellazione. L'interessato ha diritto...",
                "article_number": "Article 17",
            }
        ]
        result = {
            "answer": "You may request erasure.",
            "citations": [{"framework": "GDPR", "reference": "Art. 17(1)"}],
            "confidence_score": 0.9,
        }
        out = _apply_grounding_guard(result, chunks)
        assert "grounding_warning" not in out
        assert out["confidence_score"] == 0.9

    def test_fabricated_article_reference_flags_and_caps(self):
        # The cited article number appears in NO retrieved chunk -> ungrounded.
        chunks = [
            {
                "framework": "GDPR",
                "text": "Articolo 17 Diritto alla cancellazione...",
                "article_number": "Article 17",
            }
        ]
        result = {
            "answer": "See the provision.",
            "citations": [{"framework": "GDPR", "reference": "Art. 99(3)"}],
            "confidence_score": 0.95,
        }
        out = _apply_grounding_guard(result, chunks)
        assert out["requires_expert_review"] is True
        assert out["confidence_score"] == 0.6


# ─── Quote-snippet grounding (verbatim quotes vs the evidence) ─────


class TestQuoteSnippetGrounding:
    _EV = "L'interessato ha diritto alla cancellazione dei dati personali senza ingiustificato ritardo."

    def test_fabricated_quote_flags_and_caps(self):
        # A quote absent from the evidence is the most deceptive hallucination.
        chunks = [{"framework": "GDPR", "text": self._EV}]
        result = {
            "answer": "ok",
            "citations": [
                {
                    "framework": "GDPR",
                    "quote_snippet": "il titolare deve pagare una sanzione di dieci milioni subito",
                }
            ],
            "confidence_score": 0.95,
        }
        out = _apply_grounding_guard(result, chunks)
        assert out["requires_expert_review"] is True
        assert "grounding_warning" in out
        assert out["confidence_score"] == 0.6

    def test_verbatim_quote_not_flagged(self):
        chunks = [{"framework": "GDPR", "text": self._EV}]
        result = {
            "answer": "ok",
            "citations": [
                {
                    "framework": "GDPR",
                    "quote_snippet": "diritto alla cancellazione dei dati personali",
                }
            ],
            "confidence_score": 0.9,
        }
        out = _apply_grounding_guard(result, chunks)
        assert "grounding_warning" not in out
        assert out["confidence_score"] == 0.9

    def test_trivially_short_quote_ignored(self):
        # Too short to verify reliably -> not flagged (conservative).
        chunks = [{"framework": "GDPR", "text": self._EV}]
        result = {
            "answer": "ok",
            "citations": [{"framework": "GDPR", "quote_snippet": "art 17"}],
            "confidence_score": 0.9,
        }
        out = _apply_grounding_guard(result, chunks)
        assert "grounding_warning" not in out


# ─── citation_grounding_rate (the moat as a number) ───────────────


class TestCitationGroundingRate:
    def test_none_when_no_citations(self):
        assert (
            citation_grounding_rate({"citations": []}, [{"framework": "GDPR", "text": "x"}]) is None
        )
        assert citation_grounding_rate({}, []) is None
        assert citation_grounding_rate("not a dict", []) is None

    def test_all_grounded_is_one(self):
        chunks = [
            {"framework": "GDPR", "text": "principi"},
            {"framework": "CSRD", "text": "report"},
        ]
        result = {"citations": [{"framework": "GDPR"}, {"framework": "CSRD"}]}
        assert citation_grounding_rate(result, chunks) == pytest.approx(1.0)

    def test_half_grounded_on_framework_mismatch(self):
        chunks = [{"framework": "GDPR", "text": "principi"}]
        result = {"citations": [{"framework": "GDPR"}, {"framework": "AI_ACT"}]}
        assert citation_grounding_rate(result, chunks) == pytest.approx(0.5)

    def test_zero_when_no_evidence(self):
        result = {"citations": [{"framework": "GDPR"}, {"framework": "CSRD"}]}
        assert citation_grounding_rate(result, []) == pytest.approx(0.0)

    def test_fabricated_quote_lowers_rate(self):
        chunks = [
            {
                "framework": "GDPR",
                "text": "L'interessato ha diritto alla cancellazione dei dati personali.",
            }
        ]
        result = {
            "citations": [
                {"framework": "GDPR", "quote_snippet": "diritto alla cancellazione dei dati"},
                {"framework": "GDPR", "quote_snippet": "sanzione di dieci milioni di euro subito"},
            ]
        }
        assert citation_grounding_rate(result, chunks) == pytest.approx(0.5)

    def test_metric_agrees_with_guard(self):
        # Metric and guard never diverge: an ungrounded framework makes the rate
        # < 1.0 AND makes the guard force review.
        chunks = [{"framework": "CSRD", "text": "sustainability reporting requirements"}]
        result = {"answer": "x", "citations": [{"framework": "GDPR"}], "confidence_score": 0.9}
        rate = citation_grounding_rate(result, chunks)
        guarded = _apply_grounding_guard(dict(result), chunks)
        assert rate == pytest.approx(0.0)
        assert guarded["requires_expert_review"] is True

    def test_bad_confidence_value_falls_back_to_0_6(self):
        result = {
            "answer": "ok",
            "citations": [{"framework": "GDPR"}],
            "confidence_score": "not-a-number",
        }
        out = _apply_grounding_guard(result, [])  # no chunks -> ungrounded
        assert out["confidence_score"] == 0.6


# ─── _pack_llm_result ─────────────────────────────────────────────


class TestPackLlmResult:
    def test_high_confidence_no_review(self):
        out = _pack_llm_result({"answer": "x", "confidence_score": 0.95})
        assert json.loads(out["result_json"])["answer"] == "x"
        assert out["confidence_score"] == 0.95
        assert out["requires_review"] is False

    def test_low_confidence_requires_review(self):
        out = _pack_llm_result({"answer": "x", "confidence_score": 0.5})
        assert out["requires_review"] is True

    def test_explicit_expert_review_forces_review(self):
        out = _pack_llm_result(
            {"answer": "x", "confidence_score": 0.99, "requires_expert_review": True}
        )
        assert out["requires_review"] is True

    def test_grounding_guard_applied_when_state_given(self):
        # State with no retrieved chunks but a citation -> guard caps to 0.6
        # and forces review.
        state = {"retrieved_chunks": []}
        out = _pack_llm_result(
            {"answer": "x", "citations": [{"framework": "GDPR"}], "confidence_score": 0.99},
            state,
        )
        assert out["requires_review"] is True
        assert out["confidence_score"] == 0.6
        assert "grounding_warning" in json.loads(out["result_json"])

    def test_non_ascii_preserved_in_json(self):
        out = _pack_llm_result({"answer": "società è à", "confidence_score": 0.9})
        # ensure_ascii=False keeps accented chars literal.
        assert "società è à" in out["result_json"]


# ─── Prompt builders ──────────────────────────────────────────────


class TestPromptBuilders:
    def test_monitor_prompt_has_guard_and_query(self, sample_company_profile):
        state = {
            "query": "New CSRD amendment published",
            "company_profile": sample_company_profile,
            "retrieved_chunks": [{"framework": "CSRD", "article_number": "19a", "text": "body"}],
        }
        system_prompt, user_msg = _build_monitor_prompt(state)
        assert system_prompt.startswith(_INJECTION_GUARD)
        assert user_msg == "New CSRD amendment published"
        # Company profile fields formatted into the system prompt.
        assert "Acme Srl" in system_prompt
        # Retrieved chunk context appended.
        assert "ADDITIONAL REGULATORY CONTEXT" in system_prompt
        assert "body" in system_prompt

    def test_gap_prompt_has_guard_and_action_message(self, sample_company_profile):
        state = {"query": "CSRD", "company_profile": sample_company_profile}
        system_prompt, user_msg = _build_gap_prompt(state)
        assert system_prompt.startswith(_INJECTION_GUARD)
        assert user_msg == "Perform gap analysis for CSRD"
        assert "Annual sustainability report 2024" in system_prompt

    def test_qa_prompt_has_guard_and_serializes_profile(self, sample_company_profile):
        state = {
            "query": "Who must report under CSRD?",
            "company_profile": sample_company_profile,
            "retrieved_chunks": [{"framework": "CSRD", "article_number": "1", "text": "ctx"}],
        }
        system_prompt, user_msg = _build_qa_prompt(state)
        assert system_prompt.startswith(_INJECTION_GUARD)
        assert user_msg == "Who must report under CSRD?"
        assert "ctx" in system_prompt
        # Profile JSON-serialized into the prompt.
        assert "Acme Srl" in system_prompt

    def test_qa_prompt_empty_profile_uses_placeholder(self):
        system_prompt, _ = _build_qa_prompt({"query": "Q", "company_profile": {}})
        assert "Not available" in system_prompt

    @pytest.mark.parametrize(
        "language, name", [("en", "English"), ("it", "Italian"), ("de", "German"), ("fr", "French")]
    )
    def test_qa_prompt_asks_for_the_request_language(self, language, name):
        # The Chiedi page lets the user pick the answer language, which may differ
        # from the language of the question: the request's language decides.
        system_prompt, _ = _build_qa_prompt({"query": "Entro quando?", "language": language})
        assert f"every explanation in {name}, the language the user chose" in system_prompt
        assert "Match the language of the user's question" not in system_prompt

    @pytest.mark.parametrize("language", ["", None, "xx"])
    def test_qa_prompt_without_a_known_language_follows_the_question(self, language):
        system_prompt, _ = _build_qa_prompt({"query": "Q", "language": language})
        assert "Match the language of the user's question" in system_prompt

    def test_qa_prompt_fills_every_placeholder(self):
        system_prompt, _ = _build_qa_prompt({"query": "Q", "language": "en"})
        assert "{answer_language}" not in system_prompt
        assert "6. Language: Write the answer" in system_prompt

    def test_qa_node_sends_the_language_instruction_to_the_model(self, sample_qa_response):
        with patch.object(nodes, "call_llm", return_value=sample_qa_response) as llm:
            qa_bot_node({"query": "When?", "language": "it", "retrieved_chunks": [_A_PASSAGE]})
        system_prompt, _ = llm.call_args.args
        assert "every explanation in Italian" in system_prompt

    async def test_async_qa_node_sends_the_language_instruction_to_the_model(
        self, sample_qa_response
    ):
        llm = AsyncMock(return_value=sample_qa_response)
        with patch.object(nodes, "acall_llm", llm):
            await async_qa_bot_node(
                {"query": "Quando?", "language": "en", "retrieved_chunks": [_A_PASSAGE]}
            )
        system_prompt, _ = llm.await_args.args
        assert "every explanation in English" in system_prompt

    def test_monitor_prompt_defaults_for_missing_profile(self):
        # No profile -> default tokens ("Unknown", "All", etc.) and no crash.
        system_prompt, user_msg = _build_monitor_prompt({"query": "Q"})
        assert "Unknown" in system_prompt
        assert user_msg == "Q"


# ─── Sync agent nodes (mocked call_llm) ───────────────────────────


class TestSyncAgentNodes:
    def test_monitor_node_packs_result(self, sample_company_profile):
        llm_result = {"answer": "monitor out", "confidence_score": 0.9, "citations": []}
        with patch.object(nodes, "call_llm", return_value=llm_result) as mock_llm:
            out = monitor_agent_node(
                {"query": "CSRD change", "company_profile": sample_company_profile}
            )
        mock_llm.assert_called_once()
        # First positional arg is the system prompt carrying the injection guard.
        assert mock_llm.call_args.args[0].startswith(_INJECTION_GUARD)
        assert json.loads(out["result_json"])["answer"] == "monitor out"
        assert out["confidence_score"] == 0.9
        assert out["requires_review"] is False

    def test_gap_node_packs_result(self, sample_company_profile, sample_gap_response):
        with patch.object(nodes, "call_llm", return_value=sample_gap_response):
            out = gap_analyst_node({"query": "CSRD", "company_profile": sample_company_profile})
        # sample_gap_response confidence 0.85 -> no review needed.
        assert out["confidence_score"] == 0.85
        assert out["requires_review"] is False
        assert json.loads(out["result_json"])["framework"] == "CSRD"

    def test_qa_node_grounding_guard_caps_ungrounded(self, sample_qa_response):
        # sample_qa_response cites CSRD; the only passage retrieved is from the
        # GDPR, so the guard treats the citation as ungrounded -> review +
        # capped confidence.
        with patch.object(nodes, "call_llm", return_value=dict(sample_qa_response)):
            out = qa_bot_node({"query": "Who reports?", "retrieved_chunks": [_A_PASSAGE]})
        assert out["requires_review"] is True
        assert out["confidence_score"] == 0.6

    def test_qa_node_grounded_citation_keeps_confidence(self, sample_qa_response):
        # With a matching CSRD chunk retrieved, the CSRD citation is grounded,
        # and its quote is found word for word in that chunk: verified.
        chunks = [
            {
                "framework": "CSRD",
                "article_number": "19a",
                "text": "Large undertakings shall include in the management report information "
                "necessary to understand the undertaking's impacts on sustainability matters.",
            }
        ]
        with patch.object(nodes, "call_llm", return_value=dict(sample_qa_response)):
            out = qa_bot_node({"query": "Who reports?", "retrieved_chunks": chunks})
        assert out["confidence_score"] == 0.9
        assert out["requires_review"] is False
        served = json.loads(out["result_json"])
        assert served["citations"][0]["verified"] is True
        assert served["verified_citations"] == 1 and served["citations_total"] == 1


# ─── Citation verification wired into the Q&A agent ───────────────


class TestCitationVerificationWiring:
    """The Q&A node verifies every citation word for word after the grounding
    guard (src.agents.citation_verifier) and applies the unverified policy."""

    _CHUNKS = [
        {
            "id": "pt-gdpr-17",
            "framework": "GDPR",
            "article": "Art. 17",
            "celex": "32016R0679",
            "source_celex": "32016R0679",
            "lang": "IT",
            "text": "Articolo 17\nDiritto alla cancellazione\n1. L'interessato ha il diritto di "
            "ottenere dal titolare del trattamento la cancellazione dei dati personali che lo "
            "riguardano senza ingiustificato ritardo.",
        }
    ]
    _QUOTE = "ha il diritto di ottenere dal titolare del trattamento la cancellazione"

    def _llm(self, quote, confidence=0.9):
        return {
            "answer": "Sì [GDPR, Art. 17(1)].",
            "citations": [{"framework": "GDPR", "reference": "Art. 17(1)", "quote_snippet": quote}],
            "confidence_score": confidence,
            "requires_expert_review": False,
            "related_frameworks": [],
            "caveats": [],
        }

    def _run(self, llm, **state):
        with patch.object(nodes, "call_llm", return_value=llm):
            out = qa_bot_node({"query": "q", "retrieved_chunks": self._CHUNKS, **state})
        return out, json.loads(out["result_json"])

    def test_verified_citation_carries_the_official_provenance(self):
        llm = self._llm(self._QUOTE)
        cited = llm["citations"][0]
        snapshot = dict(cited)
        out, served = self._run(llm, language="it")

        cit = served["citations"][0]
        assert cit["verified"] is True and cit["match"] == "exact" and cit["level"] == "article"
        assert cit["chunk_id"] == "pt-gdpr-17"
        assert cit["celex"] == "32016R0679"
        assert cit["article"] == "Art. 17" and cit["paragraph"] == "1"
        assert cit["lang"] == "IT" and cit["consolidated_as_of"] is None
        assert cit["url"] == "https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:32016R0679"
        assert cit["official_quote"] == self._QUOTE
        assert cit["grounded"] is True  # the guard's verdict is kept as it was
        assert (served["verified_citations"], served["citations_total"]) == (1, 1)
        assert out["confidence_score"] == 0.9 and out["requires_review"] is False
        # Written on a copy: the model's citation dict is untouched.
        assert cited == snapshot

    def test_no_verified_citation_flags_the_answer_in_italian(self):
        out, served = self._run(self._llm("il titolare paga dieci milioni di euro di sanzione"))
        assert served["citations"][0]["verified"] is False
        assert served["citations"][0]["official_quote"] is None
        assert (served["verified_citations"], served["citations_total"]) == (0, 1)
        assert served["requires_expert_review"] is True
        assert out["confidence_score"] == 0.6 and out["requires_review"] is True
        assert served["caveats"] == [
            "Nessuno dei passaggi citati è stato ritrovato testualmente nei testi del corpus: "
            "verifica le fonti prima di usarla."
        ]

    def test_english_request_gets_the_english_caveat(self):
        _, served = self._run(
            self._llm("il titolare paga dieci milioni di euro di sanzione"), language="en"
        )
        assert served["caveats"] == [
            "None of the cited passages was found verbatim in the corpus texts: "
            "check the sources before using this answer."
        ]

    def test_strict_mode_turns_the_answer_into_an_abstention(self):
        from src.config import get_settings

        strict = get_settings().model_copy(update={"citation_verification": "strict"})
        with patch("src.config.get_settings", return_value=strict):
            out, served = self._run(self._llm("il titolare paga dieci milioni di euro di sanzione"))
        assert served["abstention_reason"] == "unverified_citations"
        assert served["citations"] == []
        assert served["answer"].startswith("Non posso fornire una risposta verificata")
        assert (served["verified_citations"], served["citations_total"]) == (0, 1)
        assert out["requires_review"] is True

    def test_strict_mode_keeps_a_verified_answer(self):
        from src.config import get_settings

        strict = get_settings().model_copy(update={"citation_verification": "strict"})
        with patch("src.config.get_settings", return_value=strict):
            out, served = self._run(self._llm(self._QUOTE))
        assert "abstention_reason" not in served
        assert served["citations"][0]["verified"] is True

    def test_llm_error_is_not_verified(self):
        error = {"error": "LLM timed out", "error_code": "llm_timeout", "confidence_score": 0.0}
        out, served = self._run(error)
        assert "citations_total" not in served and out["error"] == "LLM timed out"

    async def test_async_qa_node_verifies_too(self):
        mock = AsyncMock(return_value=self._llm(self._QUOTE))
        with patch.object(nodes, "acall_llm", new=mock):
            out = await async_qa_bot_node({"query": "q", "retrieved_chunks": self._CHUNKS})
        served = json.loads(out["result_json"])
        assert served["citations"][0]["verified"] is True

    def test_monitor_and_gap_answers_are_not_citation_verified(self, sample_company_profile):
        monitor = {"answer": "m", "confidence_score": 0.9, "citations": ["GDPR, Art. 17 - x"]}
        with patch.object(nodes, "call_llm", return_value=monitor):
            out = monitor_agent_node(
                {
                    "query": "change",
                    "company_profile": sample_company_profile,
                    "retrieved_chunks": self._CHUNKS,
                }
            )
        assert "citations_total" not in json.loads(out["result_json"])


# ─── Async agent nodes (mocked acall_llm) ─────────────────────────


class TestAsyncAgentNodes:
    async def test_async_monitor_node(self, sample_company_profile):
        llm_result = {"answer": "async monitor", "confidence_score": 0.9, "citations": []}
        with patch.object(nodes, "acall_llm", new=AsyncMock(return_value=llm_result)) as m:
            out = await async_monitor_agent_node(
                {"query": "CSRD change", "company_profile": sample_company_profile}
            )
        m.assert_awaited_once()
        assert json.loads(out["result_json"])["answer"] == "async monitor"
        assert out["requires_review"] is False

    async def test_async_gap_node(self, sample_company_profile, sample_gap_response):
        with patch.object(nodes, "acall_llm", new=AsyncMock(return_value=sample_gap_response)):
            out = await async_gap_analyst_node(
                {"query": "CSRD", "company_profile": sample_company_profile}
            )
        assert out["confidence_score"] == 0.85

    async def test_async_qa_node_passes_messages(self):
        mock = AsyncMock(return_value={"answer": "qa", "confidence_score": 0.9, "citations": []})
        with patch.object(nodes, "acall_llm", new=mock):
            await async_qa_bot_node({"query": "Who reports?", "retrieved_chunks": [_A_PASSAGE]})
        # system_prompt + user_message forwarded; user message == the query.
        args = mock.await_args.args
        assert args[0].startswith(_INJECTION_GUARD)
        assert args[1] == "Who reports?"


# ─── No passage, no answer ────────────────────────────────────────


class TestNoPassageNoAnswer:
    """Retrieval worked and found nothing: the Q&A abstains without asking the model."""

    def test_qa_abstains_without_calling_the_model(self):
        with patch.object(nodes, "call_llm") as llm:
            out = qa_bot_node({"query": "Qual è l'aliquota IVA sul pane?", "retrieved_chunks": []})
        llm.assert_not_called()
        result = json.loads(out["result_json"])
        assert result["abstention_reason"] == nodes.NO_SOURCES_ABSTENTION_REASON == "no_sources"
        assert result["answer"] == nodes.NO_SOURCES_ABSTENTION_IT
        assert result["citations"] == [] and result["citations_total"] == 0
        assert out["confidence_score"] == 0.0 and out["requires_review"] is True
        assert "error" not in out

    async def test_async_qa_abstains_in_the_language_of_the_request(self):
        with patch.object(nodes, "acall_llm", new=AsyncMock()) as llm:
            out = await async_qa_bot_node({"query": "VAT on bread?", "language": "en"})
        llm.assert_not_awaited()
        assert json.loads(out["result_json"])["answer"] == nodes.NO_SOURCES_ABSTENTION_EN

    def test_a_failed_retrieval_is_still_an_error_not_an_abstention(self):
        failed = {"query": "x", "retrieved_chunks": [], "error": f"{RETRIEVAL_ERROR_PREFIX}: down"}
        with patch.object(nodes, "call_llm") as llm:
            assert qa_bot_node(failed) == {}
        llm.assert_not_called()

    def test_the_other_agents_still_run_without_passages(self, sample_gap_response):
        with patch.object(nodes, "call_llm", return_value=sample_gap_response) as llm:
            gap_analyst_node({"query": "CSRD", "retrieved_chunks": []})
        llm.assert_called_once()


def _settings(**update):
    from src.config import get_settings

    return get_settings().model_copy(update=update)


class TestBestDenseScore:
    def test_the_highest_dense_score_of_the_results(self):
        chunks = [
            {"id": "a", "score": 0.03, "dense_score": 0.71},
            {"id": "b", "score": 0.02, "dense_score": None},  # sparse only
            {"id": "c", "score": 0.01, "dense_score": 0.83},
            "not a chunk",
            {"id": "d", "dense_score": True},
        ]
        assert nodes.best_dense_score(chunks) == 0.83

    def test_none_without_dense_scores(self):
        assert nodes.best_dense_score([{"id": "a", "score": 0.03}]) is None
        assert nodes.best_dense_score([]) is None
        assert nodes.best_dense_score(None) is None

    def test_retrieve_node_measures_it_before_reranking(self):
        # The reranker may leave the closest passage out of the 15 the model
        # reads: the threshold compares the closest one the search found.
        chunks = [
            {"id": str(i), "text": f"t{i}", "score": 1.0 - i / 100, "dense_score": 0.5}
            for i in range(30)
        ]
        chunks[29]["dense_score"] = 0.88
        scorer = MagicMock()
        scorer.score.side_effect = lambda query, passages: [-float(i) for i in range(30)]
        with (
            patch("src.api.app_state.app_state.indexer", _indexer_returning(chunks)),
            patch("src.api.app_state.app_state.reranker", scorer),
        ):
            out = retrieve_node({"query": "What does CSRD require?"})
        assert "29" not in [c["id"] for c in out["retrieved_chunks"]]
        assert out["retrieval_best_dense_score"] == 0.88

    def test_retrieve_node_leaves_it_out_when_no_result_has_one(self):
        with patch("src.api.app_state.app_state.indexer", _indexer_returning([_A_PASSAGE])):
            out = retrieve_node({"query": "What does the GDPR require?"})
        assert "retrieval_best_dense_score" not in out


class TestLowRelevanceAbstention:
    """QA_MIN_DENSE_SCORE: below it the Q&A abstains without asking the model."""

    @staticmethod
    def _state(best, language=""):
        return {
            "query": "Qual è l'aliquota IVA ordinaria?",
            "language": language,
            "retrieved_chunks": [_A_PASSAGE],
            "retrieval_best_dense_score": best,
        }

    def test_off_by_default(self):
        from src.config import Settings

        assert Settings.model_fields["qa_min_dense_score"].default == 0.0

    def test_below_the_threshold_abstains_without_calling_the_model(self):
        with (
            patch("src.config.get_settings", return_value=_settings(qa_min_dense_score=0.8)),
            patch.object(nodes, "call_llm") as llm,
        ):
            out = qa_bot_node(self._state(0.7512345))
        llm.assert_not_called()
        result = json.loads(out["result_json"])
        assert result["abstention_reason"] == nodes.LOW_RELEVANCE_ABSTENTION_REASON
        assert result["abstention_reason"] == "low_relevance"
        assert result["answer"] == nodes.LOW_RELEVANCE_ABSTENTION_IT
        assert result["best_dense_score"] == 0.7512
        assert result["citations"] == [] and result["citations_total"] == 0
        assert out["confidence_score"] == 0.0 and out["requires_review"] is True

    async def test_async_node_abstains_in_the_request_language(self):
        llm = AsyncMock()
        with (
            patch("src.config.get_settings", return_value=_settings(qa_min_dense_score=0.8)),
            patch.object(nodes, "acall_llm", llm),
        ):
            out = await async_qa_bot_node(self._state(0.42, language="en"))
        llm.assert_not_awaited()
        assert json.loads(out["result_json"])["answer"] == nodes.LOW_RELEVANCE_ABSTENTION_EN

    @pytest.mark.parametrize("threshold, best", [(0.8, 0.8), (0.8, 0.86), (0.0, 0.1), (0.8, None)])
    def test_the_model_answers_otherwise(self, threshold, best, sample_qa_response):
        # At or above the threshold, with the threshold off, or with no dense
        # score to compare (nothing measured), the model is asked as before.
        with (
            patch("src.config.get_settings", return_value=_settings(qa_min_dense_score=threshold)),
            patch.object(nodes, "call_llm", return_value=sample_qa_response) as llm,
        ):
            out = qa_bot_node(self._state(best))
        llm.assert_called_once()
        result = json.loads(out["result_json"])
        assert "abstention_reason" not in result
        if best is None:
            assert "best_dense_score" not in result
        else:
            assert result["best_dense_score"] == best

    def test_the_abstention_is_never_cached(self):
        from src.cache import is_cacheable_result

        with (
            patch("src.config.get_settings", return_value=_settings(qa_min_dense_score=0.8)),
            patch.object(nodes, "call_llm"),
        ):
            out = qa_bot_node(self._state(0.5))
        cacheable, _ = is_cacheable_result(json.loads(out["result_json"]))
        assert cacheable is False

    def test_an_llm_error_gets_no_score(self):
        error = {"error": "LLM timed out", "error_code": "llm_timeout", "confidence_score": 0.0}
        with patch.object(nodes, "call_llm", return_value=error):
            out = qa_bot_node(self._state(0.9))
        assert "best_dense_score" not in json.loads(out["result_json"])


# ─── confidence_check_node ────────────────────────────────────────


class TestConfidenceCheckNode:
    def test_high_confidence_no_review(self):
        assert confidence_check_node({"confidence_score": 0.9}) == {"requires_review": False}

    def test_low_confidence_requires_review(self):
        assert confidence_check_node({"confidence_score": 0.7}) == {"requires_review": True}

    def test_boundary_0_8_not_flagged(self):
        # score < 0.8 triggers review; exactly 0.8 does NOT.
        assert confidence_check_node({"confidence_score": 0.8}) == {"requires_review": False}

    def test_missing_score_defaults_to_review(self):
        # Default 0.0 < 0.8 -> review.
        assert confidence_check_node({}) == {"requires_review": True}


# ─── async_local_router_node ──────────────────────────────────────


class TestAsyncLocalRouterNode:
    async def test_writes_router_fields_into_state(self):
        router_result = MagicMock()
        router_result.frameworks = ["CSRD"]
        router_result.complexity = "complex"
        router_result.entities = {"article_refs": ["Art. 8"], "deadlines": [], "thresholds": []}
        router_result.source = "local_llm"

        with patch(
            "src.agents.router.aroute_query", new=AsyncMock(return_value=router_result)
        ) as m:
            out = await async_local_router_node({"query": "CSRD Art 8", "task_type": "qa"})

        m.assert_awaited_once_with("CSRD Art 8", "qa")
        assert out["detected_frameworks"] == ["CSRD"]
        assert out["complexity_tier"] == "complex"
        assert out["extracted_entities"]["article_refs"] == ["Art. 8"]
        assert out["router_source"] == "local_llm"

    async def test_defaults_query_and_task_type(self):
        router_result = MagicMock()
        router_result.frameworks = []
        router_result.complexity = "medium"
        router_result.entities = {}
        router_result.source = "keyword_fallback"
        with patch(
            "src.agents.router.aroute_query", new=AsyncMock(return_value=router_result)
        ) as m:
            await async_local_router_node({})
        # Empty state -> defaults: query "", task_type "qa".
        m.assert_awaited_once_with("", "qa")


# ─── async_simple_response_node ───────────────────────────────────


class TestAsyncSimpleResponseNode:
    async def test_cache_hit_returns_cached_payload(self):
        # A verified citation: the citation policy has nothing to flag.
        cached = {"answer": "cached", "confidence_score": 0.91, "citations": [{"verified": True}]}
        with patch("src.cache.response_cache.get", new=AsyncMock(return_value=cached)):
            out = await async_simple_response_node(
                {"query": "What is GDPR?", "task_type": "qa", "company_profile": {}}
            )
        assert json.loads(out["result_json"])["answer"] == "cached"
        assert out["confidence_score"] == 0.91
        assert out["requires_review"] is False
        # Cache hit does NOT escalate.
        assert "complexity_tier" not in out

    async def test_cache_hit_missing_confidence_is_zero_and_reviewed(self):
        # Cached payload missing confidence_score -> 0.0 + review (a cache hit
        # must not fabricate the 0.8 it used to report).
        with patch("src.cache.response_cache.get", new=AsyncMock(return_value={"answer": "c"})):
            out = await async_simple_response_node({"query": "Q", "task_type": "qa"})
        assert out["confidence_score"] == 0.0
        assert out["requires_review"] is True

    async def test_cache_hit_without_citations_is_reviewed(self):
        cached = {"answer": "cached", "confidence_score": 0.91, "citations": []}
        with patch("src.cache.response_cache.get", new=AsyncMock(return_value=cached)):
            out = await async_simple_response_node({"query": "Q", "task_type": "qa"})
        assert out["requires_review"] is True
        assert json.loads(out["result_json"])["caveats"] == [
            "La risposta non cita nessun passaggio dei testi del corpus: verifica le fonti prima "
            "di usarla."
        ]

    async def test_cache_hit_honours_cached_review_flag(self):
        cached = {"answer": "c", "confidence_score": 0.95, "requires_expert_review": True}
        with patch("src.cache.response_cache.get", new=AsyncMock(return_value=cached)):
            out = await async_simple_response_node({"query": "Q", "task_type": "qa"})
        assert out["confidence_score"] == 0.95
        assert out["requires_review"] is True

    async def test_cache_hit_reapplies_the_unverified_citation_policy(self):
        # A cached Q&A answer bypasses the agent node: the policy is applied
        # again with the CURRENT setting (here strict) and request language.
        from src.config import get_settings

        cached = {
            "answer": "c",
            "citations": [{"framework": "GDPR", "verified": False}],
            "verified_citations": 0,
            "citations_total": 1,
            "confidence_score": 0.6,
            "requires_expert_review": True,
        }
        strict = get_settings().model_copy(update={"citation_verification": "strict"})
        with (
            patch("src.cache.response_cache.get", new=AsyncMock(return_value=cached)),
            patch("src.config.get_settings", return_value=strict),
        ):
            out = await async_simple_response_node(
                {"query": "Q", "task_type": "qa", "language": "en"}
            )
        served = json.loads(out["result_json"])
        assert served["abstention_reason"] == "unverified_citations"
        assert served["answer"].startswith("I cannot provide a verified answer")
        assert out["requires_review"] is True

    async def test_cache_miss_escalates_to_medium(self):
        with patch("src.cache.response_cache.get", new=AsyncMock(return_value=None)):
            out = await async_simple_response_node({"query": "Q", "task_type": "qa"})
        assert out == {"complexity_tier": "medium"}

    async def test_cache_error_escalates_gracefully(self):
        # A cache exception must not crash the node; it escalates instead.
        with patch(
            "src.cache.response_cache.get",
            new=AsyncMock(side_effect=RuntimeError("redis down")),
        ):
            out = await async_simple_response_node({"query": "Q", "task_type": "qa"})
        assert out == {"complexity_tier": "medium"}
