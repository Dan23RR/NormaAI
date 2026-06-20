"""Unit tests for the SNC LangGraph node (src/agents/snc_node.py).

Covers the node's pure-Python orchestration logic with the LLM fully mocked:

  - config plumbing from settings -> SNCConfig
  - prompt / user-message reconstruction helpers
  - the async governance node: pass-through (disabled), draft-error skip,
    missing-prompt skip, exception non-fatal fall-through, and the happy
    path that rewrites state with the SNC decision
  - the three-way routing helper (ABSTAIN -> abstain_response, else
    confidence_check)
  - the abstain_response terminal node payload
  - end-to-end through the REAL snc_governance() with acall_llm mocked to feed
    controlled K-sample sets (identical = max trust / ADMIT_HIGH,
    divergent = low trust / ABSTAIN), plus the k<2 closed-form branch.

No real LLM / network / DB is touched; acall_llm and snc_governance are
patched at their import sites.
"""

import json
from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest

from src.agents import snc_node
from src.agents.snc_layer import SNCConfig, SNCDecision, snc_governance
from src.agents.snc_node import (
    _build_user_message,
    _config_from_settings,
    abstain_response_node,
    async_snc_governance_node,
    snc_governance_node,
    snc_route_to_next,
)


def _make_decision(action="ADMIT_HIGH", trust=0.9):
    """Build a deterministic SNCDecision for node-level tests."""
    return SNCDecision(
        action=action,
        trust=trust,
        ppv=0.9,
        sigma_calib=0.0,
        t_comp=0.6,
        n_clusters=1,
        modal_answer={"answer": "modal answer", "citations": []},
        samples=[{"answer": "modal answer", "confidence_score": 0.9, "citations": []}],
    )


# ─── _config_from_settings ─────────────────────────────────────────────


class TestConfigFromSettings:
    def test_reads_defaults_from_settings(self):
        cfg = _config_from_settings()
        assert isinstance(cfg, SNCConfig)
        # Matches the Settings defaults (src/config.py).
        assert cfg.k == 3
        assert cfg.temperature == pytest.approx(0.7)
        assert cfg.theta_high == pytest.approx(0.85)
        assert cfg.theta_low == pytest.approx(0.50)
        assert cfg.enabled is True

    def test_uses_getattr_fallbacks_when_settings_missing_fields(self):
        # An object lacking the snc_* attributes must still produce a config
        # via the getattr() defaults baked into _config_from_settings.
        class Bare:
            pass

        with patch.object(snc_node, "get_settings", return_value=Bare()):
            cfg = _config_from_settings()
        assert cfg.k == 3
        assert cfg.temperature == pytest.approx(0.7)
        assert cfg.theta_high == pytest.approx(0.85)
        assert cfg.theta_low == pytest.approx(0.50)
        assert cfg.enabled is True


# ─── _build_user_message ──────────────────────────────────────────────


class TestBuildUserMessage:
    def test_query_only(self):
        msg = _build_user_message({"query": "Cosa prevede il GDPR?"})
        assert "User query: Cosa prevede il GDPR?" in msg
        # No profile / chunks sections.
        assert "Company profile:" not in msg
        assert "Regulatory context:" not in msg

    def test_includes_profile_when_present(self):
        msg = _build_user_message(
            {"query": "Q", "company_profile": {"name": "Acme", "sector": "Mfg"}}
        )
        assert "Company profile:" in msg
        assert "Acme" in msg

    def test_includes_formatted_chunks_when_present(self):
        msg = _build_user_message(
            {
                "query": "Q",
                "retrieved_chunks": [
                    {"framework": "GDPR", "article_number": "5", "text": "principi"}
                ],
            }
        )
        assert "Regulatory context:" in msg
        # format_retrieved_chunks renders the citation marker.
        assert "[GDPR, 5]" in msg
        assert "principi" in msg

    def test_empty_state_defaults(self):
        msg = _build_user_message({})
        assert "User query:" in msg

    def test_falsy_profile_and_chunks_are_skipped(self):
        # None profile/chunks must not add sections (covers the `or {}`/`or []`).
        msg = _build_user_message({"query": "Q", "company_profile": None, "retrieved_chunks": None})
        assert "Company profile:" not in msg
        assert "Regulatory context:" not in msg


# ─── _build_system_prompt_for_resample ────────────────────────────────


class TestBuildSystemPrompt:
    def test_returns_prompt_text_when_file_exists(self, tmp_path):
        # The helper resolves Path(__file__).parent.parent.parent / "prompts" /
        # "<name>.txt". With __file__ at tmp_path/src/agents/snc_node.py that is
        # tmp_path/prompts. Build that layout and point snc_node.__file__ at it,
        # so the real (un-patched) Path logic reads our temp prompt file.
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir(parents=True)
        prompt_text = "SYSTEM PROMPT BODY"
        (prompts_dir / "qa_bot.txt").write_text(prompt_text, encoding="utf-8")

        fake_module_file = str(tmp_path / "src" / "agents" / "snc_node.py")
        with patch.object(snc_node, "__file__", fake_module_file):
            out = snc_node._build_system_prompt_for_resample({"task_type": "qa"})
        assert out == prompt_text

    def test_returns_empty_when_prompt_file_missing(self, tmp_path):
        # Graceful degradation: when the resolved prompts dir has no matching
        # file, the helper logs a warning and returns "". Point __file__ at a
        # tmp location whose resolved prompts dir (tmp_path/prompts) is empty,
        # so the lookup misses and we exercise the warn+return "" path.
        fake_module_file = str(tmp_path / "src" / "agents" / "snc_node.py")
        with patch.object(snc_node, "__file__", fake_module_file):
            out = snc_node._build_system_prompt_for_resample({"task_type": "qa"})
        assert out == ""

    def test_maps_task_type_to_prompt_name(self, tmp_path):
        # monitor -> regulatory_monitor, gap_analysis -> gap_analyst,
        # qa / unknown -> qa_bot. Create each real prompt file with distinct
        # content and verify the helper picks the right one per task_type.
        # __file__ at tmp_path/src/agents/snc_node.py resolves to tmp_path/prompts.
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir(parents=True)
        (prompts_dir / "regulatory_monitor.txt").write_text("MON", encoding="utf-8")
        (prompts_dir / "gap_analyst.txt").write_text("GAP", encoding="utf-8")
        (prompts_dir / "qa_bot.txt").write_text("QA", encoding="utf-8")

        fake_module_file = str(tmp_path / "src" / "agents" / "snc_node.py")
        with patch.object(snc_node, "__file__", fake_module_file):
            assert snc_node._build_system_prompt_for_resample({"task_type": "monitor"}) == "MON"
            assert (
                snc_node._build_system_prompt_for_resample({"task_type": "gap_analysis"}) == "GAP"
            )
            assert snc_node._build_system_prompt_for_resample({"task_type": "qa"}) == "QA"
            # Unknown task falls back to qa_bot.
            assert snc_node._build_system_prompt_for_resample({"task_type": "weird"}) == "QA"
            # Missing task_type also defaults to qa.
            assert snc_node._build_system_prompt_for_resample({}) == "QA"


# ─── async_snc_governance_node ─────────────────────────────────────────


class TestAsyncNodeShortCircuits:
    async def test_disabled_passes_through_unmodified(self):
        cfg = SNCConfig(enabled=False)
        with patch.object(snc_node, "_config_from_settings", return_value=cfg):
            state = {"result_json": '{"answer": "x"}'}
            out = await async_snc_governance_node(state)
        # State returned unchanged; no SNC keys written.
        assert out is state
        assert "snc_decision" not in out
        assert "snc_action" not in out

    async def test_draft_with_error_is_skipped(self):
        cfg = SNCConfig(enabled=True)
        with patch.object(snc_node, "_config_from_settings", return_value=cfg):
            state = {"result_json": json.dumps({"error": "upstream failure"})}
            out = await async_snc_governance_node(state)
        assert "snc_decision" not in out
        assert "snc_action" not in out

    async def test_missing_prompt_or_message_is_skipped(self, tmp_path):
        # When the resolved prompts dir is empty the system prompt is "", so the
        # node hits the "missing prompt" guard and returns state untouched. We
        # point __file__ at a tmp location whose prompts dir does not exist to
        # force that path deterministically (without depending on real prompts).
        cfg = SNCConfig(enabled=True)
        fake_module_file = str(tmp_path / "src" / "agents" / "snc_node.py")
        with (
            patch.object(snc_node, "_config_from_settings", return_value=cfg),
            patch.object(snc_node, "__file__", fake_module_file),
        ):
            state = {"result_json": json.dumps({"answer": "ok", "confidence_score": 0.9})}
            out = await async_snc_governance_node(state)
        assert "snc_decision" not in out

    async def test_non_string_draft_dict_is_accepted(self, tmp_path):
        # result_json may already be a dict; with no prompt it still short-circuits
        # but must not raise on the json.loads branch.
        cfg = SNCConfig(enabled=True)
        fake_module_file = str(tmp_path / "src" / "agents" / "snc_node.py")
        with (
            patch.object(snc_node, "_config_from_settings", return_value=cfg),
            patch.object(snc_node, "__file__", fake_module_file),
        ):
            state = {"result_json": {"answer": "ok", "confidence_score": 0.9}}
            out = await async_snc_governance_node(state)
        assert out is state

    async def test_malformed_json_string_does_not_raise(self, tmp_path):
        # A non-JSON string draft is wrapped into {"answer": ..., "citations": []}
        # then short-circuits on the missing prompt. Must not raise.
        cfg = SNCConfig(enabled=True)
        fake_module_file = str(tmp_path / "src" / "agents" / "snc_node.py")
        with (
            patch.object(snc_node, "_config_from_settings", return_value=cfg),
            patch.object(snc_node, "__file__", fake_module_file),
        ):
            state = {"result_json": "this is not json {{{"}
            out = await async_snc_governance_node(state)
        assert out is state
        assert "snc_decision" not in out


class TestAsyncNodeHappyPath:
    async def test_writes_decision_into_state(self):
        cfg = SNCConfig(enabled=True)
        decision = _make_decision(action="ADMIT_MID", trust=0.7)
        mocked_gov = AsyncMock(return_value=decision)

        with (
            patch.object(snc_node, "_config_from_settings", return_value=cfg),
            patch.object(snc_node, "_build_system_prompt_for_resample", return_value="SYS"),
            patch.object(snc_node, "_build_user_message", return_value="USER MSG"),
            patch.object(snc_node, "snc_governance", mocked_gov),
        ):
            state = {"result_json": json.dumps({"answer": "draft", "confidence_score": 0.7})}
            out = await async_snc_governance_node(state)

        assert out["snc_action"] == "ADMIT_MID"
        assert out["confidence_score"] == pytest.approx(0.7)
        assert out["requires_expert_review"] is False
        # result_json carries the modal answer but with the COMPUTED trust
        # surfaced as confidence_score (not the sample's self-declared value).
        surfaced = json.loads(out["result_json"])
        assert surfaced["answer"] == decision.modal_answer["answer"]
        assert surfaced["confidence_score"] == pytest.approx(0.7)
        assert surfaced["snc_trust"] == pytest.approx(0.7)
        assert surfaced["snc_action"] == "ADMIT_MID"
        # serialized audit blob present and consistent.
        assert out["snc_audit"] == out["snc_decision"]
        assert out["snc_decision"]["action"] == "ADMIT_MID"
        assert out["snc_decision"]["n_clusters"] == 1
        mocked_gov.assert_awaited_once()

    async def test_abstain_sets_requires_expert_review(self):
        cfg = SNCConfig(enabled=True)
        decision = _make_decision(action="ABSTAIN", trust=0.1)
        mocked_gov = AsyncMock(return_value=decision)

        with (
            patch.object(snc_node, "_config_from_settings", return_value=cfg),
            patch.object(snc_node, "_build_system_prompt_for_resample", return_value="SYS"),
            patch.object(snc_node, "_build_user_message", return_value="USER MSG"),
            patch.object(snc_node, "snc_governance", mocked_gov),
        ):
            state = {"result_json": json.dumps({"answer": "draft", "confidence_score": 0.1})}
            out = await async_snc_governance_node(state)

        assert out["snc_action"] == "ABSTAIN"
        assert out["requires_expert_review"] is True

    async def test_governance_exception_is_non_fatal(self):
        cfg = SNCConfig(enabled=True)
        boom = AsyncMock(side_effect=RuntimeError("llm exploded"))

        with (
            patch.object(snc_node, "_config_from_settings", return_value=cfg),
            patch.object(snc_node, "_build_system_prompt_for_resample", return_value="SYS"),
            patch.object(snc_node, "_build_user_message", return_value="USER MSG"),
            patch.object(snc_node, "snc_governance", boom),
        ):
            state = {"result_json": json.dumps({"answer": "draft", "confidence_score": 0.9})}
            out = await async_snc_governance_node(state)

        # Fell through with the original state, no SNC keys.
        assert out is state
        assert "snc_decision" not in out
        assert "snc_action" not in out

    async def test_passes_config_and_messages_to_governance(self):
        cfg = SNCConfig(enabled=True, k=4, temperature=0.9)
        decision = _make_decision()
        mocked_gov = AsyncMock(return_value=decision)

        with (
            patch.object(snc_node, "_config_from_settings", return_value=cfg),
            patch.object(snc_node, "_build_system_prompt_for_resample", return_value="SYS-X"),
            patch.object(snc_node, "_build_user_message", return_value="USR-X"),
            patch.object(snc_node, "snc_governance", mocked_gov),
        ):
            await async_snc_governance_node(
                {"result_json": json.dumps({"answer": "d", "confidence_score": 0.9})}
            )

        _, kwargs = mocked_gov.call_args
        assert kwargs["system_prompt"] == "SYS-X"
        assert kwargs["user_message"] == "USR-X"
        assert kwargs["config"] is cfg
        assert kwargs["initial_response"] == {"answer": "d", "confidence_score": 0.9}


# ─── snc_governance_node (sync wrapper) ────────────────────────────────


class TestSyncWrapper:
    def test_drives_async_path_via_asyncio_run(self):
        cfg = SNCConfig(enabled=True)
        decision = _make_decision(action="ADMIT_HIGH", trust=0.95)
        mocked_gov = AsyncMock(return_value=decision)

        with (
            patch.object(snc_node, "_config_from_settings", return_value=cfg),
            patch.object(snc_node, "_build_system_prompt_for_resample", return_value="SYS"),
            patch.object(snc_node, "_build_user_message", return_value="USER"),
            patch.object(snc_node, "snc_governance", mocked_gov),
        ):
            out = snc_governance_node(
                {"result_json": json.dumps({"answer": "d", "confidence_score": 0.95})}
            )
        assert out["snc_action"] == "ADMIT_HIGH"

    def test_disabled_passthrough_via_sync_wrapper(self):
        with patch.object(snc_node, "_config_from_settings", return_value=SNCConfig(enabled=False)):
            state = {"result_json": "{}"}
            out = snc_governance_node(state)
        assert out is state

    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    async def test_inside_running_loop_falls_back_to_passthrough(self):
        # Called from within a live event loop, asyncio.run() raises RuntimeError;
        # the wrapper must catch it and return state unchanged. (The source builds
        # a coroutine that asyncio.run never awaits before raising -> RuntimeWarning,
        # which is the source's behavior, not a test defect.)
        state = {"result_json": "{}", "marker": 1}
        out = snc_governance_node(state)
        assert out is state
        assert out["marker"] == 1


# ─── snc_route_to_next ─────────────────────────────────────────────────


class TestRouting:
    def test_abstain_routes_to_abstain_response(self):
        assert snc_route_to_next({"snc_action": "ABSTAIN"}) == "abstain_response"

    def test_admit_high_routes_to_confidence_check(self):
        assert snc_route_to_next({"snc_action": "ADMIT_HIGH"}) == "confidence_check"

    def test_admit_mid_routes_to_confidence_check(self):
        assert snc_route_to_next({"snc_action": "ADMIT_MID"}) == "confidence_check"

    def test_missing_action_defaults_to_confidence_check(self):
        assert snc_route_to_next({}) == "confidence_check"


# ─── abstain_response_node ─────────────────────────────────────────────


class TestAbstainResponseNode:
    def test_builds_structured_abstention_payload(self):
        audit = {"action": "ABSTAIN", "trust": 0.1}
        state = {"confidence_score": 0.2, "snc_audit": audit}
        out = abstain_response_node(state)

        payload = json.loads(out["result_json"])
        assert payload["requires_expert_review"] is True
        assert payload["abstention_reason"] == "snc_low_trust"
        assert payload["citations"] == []
        assert payload["confidence_score"] == pytest.approx(0.2)
        assert payload["snc_audit"] == audit
        assert "revisione esperta" in payload["answer"].lower()
        # State-level flag also set.
        assert out["requires_expert_review"] is True

    def test_defaults_when_state_keys_absent(self):
        out = abstain_response_node({})
        payload = json.loads(out["result_json"])
        assert payload["confidence_score"] == pytest.approx(0.0)
        assert payload["snc_audit"] == {}
        assert payload["requires_expert_review"] is True


# ─── End-to-end through REAL snc_governance (acall_llm mocked) ─────────
#
# These exercise the actual trust math by feeding controlled K-sample sets,
# verifying the three-way routing thresholds emerge from real entropy/trust.


def _admit_high_settings():
    return SNCConfig(k=3, temperature=0.7, theta_high=0.85, theta_low=0.50, enabled=True)


class TestEndToEndGovernance:
    async def test_identical_samples_max_trust_admit_high(self):
        # Initial draft + K-1 identical resamples => single cluster, entropy 0,
        # sigma_calib 0 => trust == ppv (high). With ppv 0.95 and theta_high 0.85
        # => ADMIT_HIGH.
        initial = {
            "answer": "Articolo 5 GDPR.",
            "confidence_score": 0.95,
            "citations": [{"framework": "GDPR", "article_number": "5"}],
        }
        resample = dict(initial)  # identical behavior key + confidence
        mocked = AsyncMock(return_value=resample)

        with patch("src.agents.snc_layer.acall_llm", mocked):
            decision = await snc_governance(
                initial_response=initial,
                system_prompt="SYS",
                user_message="USR",
                config=_admit_high_settings(),
            )

        assert decision.n_clusters == 1
        assert decision.sigma_calib == pytest.approx(0.0)
        assert decision.trust == pytest.approx(0.95)
        assert decision.action == "ADMIT_HIGH"
        # K-1 = 2 resample calls.
        assert mocked.await_count == 2

    async def test_divergent_samples_low_trust_abstain(self):
        # Three fully divergent citations => 3 clusters, uniform => entropy 1,
        # sigma_calib 1. Even with high self-confidence the thermodynamic
        # discount collapses trust below theta_low => ABSTAIN.
        initial = {
            "answer": "A",
            "confidence_score": 0.9,
            "citations": [{"framework": "GDPR", "article_number": "5"}],
        }
        r2 = {
            "answer": "B",
            "confidence_score": 0.9,
            "citations": [{"framework": "CSRD", "article_number": "19a"}],
        }
        r3 = {
            "answer": "C",
            "confidence_score": 0.9,
            "citations": [{"framework": "CSDDD", "article_number": "8"}],
        }
        mocked = AsyncMock(side_effect=[r2, r3])

        with patch("src.agents.snc_layer.acall_llm", mocked):
            decision = await snc_governance(
                initial_response=initial,
                system_prompt="SYS",
                user_message="USR",
                config=_admit_high_settings(),
            )

        assert decision.n_clusters == 3
        assert decision.sigma_calib == pytest.approx(1.0)
        assert decision.trust < 0.50
        assert decision.action == "ABSTAIN"

    async def test_two_one_split_intermediate_admit_mid(self):
        # 2-vs-1 split => 2 clusters, skewed entropy (0 < sigma < 1). With
        # ppv 0.9 the trust lands between theta_low and theta_high => ADMIT_MID.
        cited = {"framework": "GDPR", "article_number": "5"}
        initial = {"answer": "A", "confidence_score": 0.9, "citations": [cited]}
        r2 = {"answer": "A2", "confidence_score": 0.9, "citations": [cited]}  # same cluster
        r3 = {
            "answer": "B",
            "confidence_score": 0.9,
            "citations": [{"framework": "CSRD", "article_number": "1"}],
        }
        mocked = AsyncMock(side_effect=[r2, r3])

        with patch("src.agents.snc_layer.acall_llm", mocked):
            decision = await snc_governance(
                initial_response=initial,
                system_prompt="SYS",
                user_message="USR",
                config=_admit_high_settings(),
            )

        assert decision.n_clusters == 2
        assert 0.0 < decision.sigma_calib < 1.0
        assert 0.50 <= decision.trust < 0.85
        assert decision.action == "ADMIT_MID"
        # Modal answer is the majority (GDPR:5) cluster, taken from the first
        # member (the initial response).
        assert decision.modal_answer is initial

    async def test_k_less_than_2_uses_closed_form_no_resampling(self):
        # k<2 short-circuits: no resampling, trust == self-confidence, routed by
        # theta thresholds. ppv 0.9 >= theta_high 0.85 => ADMIT_HIGH.
        initial = {"answer": "X", "confidence_score": 0.9, "citations": []}
        mocked = AsyncMock()
        with patch("src.agents.snc_layer.acall_llm", mocked):
            decision = await snc_governance(
                initial_response=initial,
                system_prompt="SYS",
                user_message="USR",
                config=SNCConfig(k=1, theta_high=0.85, theta_low=0.50, enabled=True),
            )
        assert decision.action == "ADMIT_HIGH"
        assert decision.trust == pytest.approx(0.9)
        assert decision.n_clusters == 1
        mocked.assert_not_awaited()

    async def test_k_less_than_2_mid_and_abstain_bands(self):
        # Same closed-form branch, exercising the MID and ABSTAIN bands.
        mid = await snc_governance(
            initial_response={"answer": "X", "confidence_score": 0.6, "citations": []},
            system_prompt="SYS",
            user_message="USR",
            config=SNCConfig(k=1, theta_high=0.85, theta_low=0.50, enabled=True),
        )
        assert mid.action == "ADMIT_MID"

        low = await snc_governance(
            initial_response={"answer": "X", "confidence_score": 0.2, "citations": []},
            system_prompt="SYS",
            user_message="USR",
            config=SNCConfig(k=1, theta_high=0.85, theta_low=0.50, enabled=True),
        )
        assert low.action == "ABSTAIN"

    async def test_all_resamples_fail_degraded_mode_abstain(self):
        # If every extra sample raises (returns Exception via gather), only the
        # initial remains (< 2 valid) => degraded mode => ABSTAIN, trust halved.
        initial = {"answer": "X", "confidence_score": 0.8, "citations": []}
        mocked = AsyncMock(side_effect=RuntimeError("llm down"))
        with patch("src.agents.snc_layer.acall_llm", mocked):
            decision = await snc_governance(
                initial_response=initial,
                system_prompt="SYS",
                user_message="USR",
                config=_admit_high_settings(),
            )
        assert decision.action == "ABSTAIN"
        assert decision.trust == pytest.approx(0.8 * 0.5)
        assert decision.n_clusters == 1

    async def test_error_dict_resamples_are_filtered_out(self):
        # Resamples that come back as {"error": ...} are dropped; if that leaves
        # only the initial sample, we degrade to ABSTAIN.
        initial = {"answer": "X", "confidence_score": 0.8, "citations": []}
        mocked = AsyncMock(side_effect=[{"error": "boom"}, {"error": "boom"}])
        with patch("src.agents.snc_layer.acall_llm", mocked):
            decision = await snc_governance(
                initial_response=initial,
                system_prompt="SYS",
                user_message="USR",
                config=_admit_high_settings(),
            )
        assert decision.action == "ABSTAIN"
        assert decision.n_clusters == 1

    async def test_disabled_config_uses_closed_form(self):
        # enabled=False also routes through the closed-form branch (no resample).
        initial = {"answer": "X", "confidence_score": 0.95, "citations": []}
        cfg = replace(_admit_high_settings(), enabled=False)
        mocked = AsyncMock()
        with patch("src.agents.snc_layer.acall_llm", mocked):
            decision = await snc_governance(
                initial_response=initial,
                system_prompt="SYS",
                user_message="USR",
                config=cfg,
            )
        assert decision.action == "ADMIT_HIGH"
        mocked.assert_not_awaited()


# ─── Full node wired to the REAL governance (acall_llm mocked) ─────────


class TestNodeWiredToRealGovernance:
    async def test_node_admit_high_end_to_end(self):
        # Patch only the prompt/message builders + acall_llm; let the real
        # snc_governance run inside the node and rewrite state.
        initial = {
            "answer": "Articolo 5 GDPR.",
            "confidence_score": 0.95,
            "citations": [{"framework": "GDPR", "article_number": "5"}],
        }
        resample = dict(initial)
        mocked = AsyncMock(return_value=resample)

        with (
            patch.object(snc_node, "_config_from_settings", return_value=_admit_high_settings()),
            patch.object(snc_node, "_build_system_prompt_for_resample", return_value="SYS"),
            patch.object(snc_node, "_build_user_message", return_value="USR"),
            patch("src.agents.snc_layer.acall_llm", mocked),
        ):
            state = {"result_json": json.dumps(initial)}
            out = await async_snc_governance_node(state)

        assert out["snc_action"] == "ADMIT_HIGH"
        assert out["requires_expert_review"] is False
        assert out["confidence_score"] == pytest.approx(0.95)
        # result_json now holds the modal answer (the GDPR:5 cluster rep).
        modal = json.loads(out["result_json"])
        assert modal["citations"] == [{"framework": "GDPR", "article_number": "5"}]

    async def test_node_abstain_end_to_end_then_abstain_response(self):
        # Divergent samples drive ABSTAIN at the node, then the routing helper
        # and the terminal abstain node produce the structured payload.
        initial = {
            "answer": "A",
            "confidence_score": 0.9,
            "citations": [{"framework": "GDPR", "article_number": "5"}],
        }
        r2 = {
            "answer": "B",
            "confidence_score": 0.9,
            "citations": [{"framework": "CSRD", "article_number": "19a"}],
        }
        r3 = {
            "answer": "C",
            "confidence_score": 0.9,
            "citations": [{"framework": "CSDDD", "article_number": "8"}],
        }
        mocked = AsyncMock(side_effect=[r2, r3])

        with (
            patch.object(snc_node, "_config_from_settings", return_value=_admit_high_settings()),
            patch.object(snc_node, "_build_system_prompt_for_resample", return_value="SYS"),
            patch.object(snc_node, "_build_user_message", return_value="USR"),
            patch("src.agents.snc_layer.acall_llm", mocked),
        ):
            out = await async_snc_governance_node({"result_json": json.dumps(initial)})

        assert out["snc_action"] == "ABSTAIN"
        assert out["requires_expert_review"] is True
        # Routing helper agrees.
        assert snc_route_to_next(out) == "abstain_response"
        # Terminal node serializes the abstention with the audit blob carried over.
        terminal = abstain_response_node(out)
        payload = json.loads(terminal["result_json"])
        assert payload["abstention_reason"] == "snc_low_trust"
        assert payload["snc_audit"] == out["snc_audit"]
