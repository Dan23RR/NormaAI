"""The PDF reports ask what /api/v1/qa asks: the LLM quota and a verified email.

- /reports/gap-analysis counts one unit of the organisation's daily quota and
  says how many are left (``X-Quota-Remaining``); once spent, 429 and the
  agent does not run.
- /reports/executive-summary counts one unit per framework; a report that
  wants more units than are left is refused without spending them.
- With REQUIRE_EMAIL_VERIFICATION on, an unverified address gets 403 and the
  agent does not run.
"""

from __future__ import annotations

import sys
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import get_settings
from src.quotas import DailyLLMQuota


@pytest.fixture(autouse=True)
def _restore_module_cache():
    yield
    for name in list(sys.modules):
        if (
            name == "src.api.main"
            or name.startswith("src.api.routers")
            or name == "src.auth.router"
        ):
            sys.modules.pop(name, None)


@pytest.fixture
def quota():
    """A quota counted in memory (no Redis attempt), limit 3 a day."""
    q = DailyLLMQuota()
    q._next_connect_attempt = float("inf")
    return q


@pytest.fixture
def client(quota):
    with (
        patch("src.api.lifespan.validate_settings_or_exit") as mock_settings,
        patch("src.api.lifespan.db_manager", create=True),
        patch.dict(
            "sys.modules",
            {"src.nlp.embedding.indexer": MagicMock(), "src.db.engine": MagicMock()},
        ),
    ):
        mock_settings.return_value = get_settings()

        from fastapi.testclient import TestClient

        from src.api.main import app, app_state, limiter
        from src.api.routers import reports

        app_state.qdrant_available = True
        app_state.llm_available = True
        limiter.enabled = False
        limited = get_settings().model_copy(update={"llm_daily_quota_per_org": 3})
        with (
            patch.object(reports, "llm_quota", quota),
            patch("src.quotas.get_settings", return_value=limited),
        ):
            try:
                yield TestClient(app)
            finally:
                app.dependency_overrides.clear()


PROFILE = {"name": "Acme Srl", "sector": "Manufacturing", "employee_count": 300}
GAP = {"framework": "CSRD", "overall_score": 50.0, "requirements": [], "recommendations": []}


def _headers(org_id=None, **claims) -> dict[str, str]:
    from src.auth.security import create_access_token

    token = create_access_token(uuid.uuid4(), org_id or uuid.uuid4(), "member", **claims)
    return {"Authorization": f"Bearer {token}"}


def _agent():
    return AsyncMock(side_effect=lambda framework, profile: dict(GAP, framework=framework))


def _generator():
    generator = MagicMock()
    generator.generate_gap_report.return_value = b"%PDF-1.4 gap"
    generator.generate_executive_summary.return_value = b"%PDF-1.4 summary"
    return MagicMock(return_value=generator)


def _gap(client, headers):
    return client.post(
        "/api/v1/reports/gap-analysis",
        json={"framework": "CSRD", "company_profile": PROFILE},
        headers=headers,
    )


def _summary(client, headers, frameworks):
    return client.post(
        "/api/v1/reports/executive-summary",
        json={"frameworks": frameworks, "company_profile": PROFILE},
        headers=headers,
    )


class TestGapReport:
    def test_counts_one_unit_and_stops_when_the_quota_is_spent(self, client, quota):
        org = uuid.uuid4()
        headers = _headers(org)
        agent = _agent()
        with (
            patch("src.agents.graph.arun_gap_analysis", agent),
            patch("src.reports.generator.ComplianceReportGenerator", _generator()),
        ):
            answers = [_gap(client, headers) for _ in range(4)]
        assert [r.status_code for r in answers] == [200, 200, 200, 429]
        assert [r.headers.get("X-Quota-Remaining") for r in answers[:3]] == ["2", "1", "0"]
        assert answers[3].headers["X-Quota-Remaining"] == "0"
        assert "Quota giornaliera" in answers[3].json()["detail"]
        assert int(answers[3].headers["Retry-After"]) >= 1
        assert agent.await_count == 3  # the refused request ran nothing

    def test_organisations_have_their_own_quota(self, client):
        with (
            patch("src.agents.graph.arun_gap_analysis", _agent()),
            patch("src.reports.generator.ComplianceReportGenerator", _generator()),
        ):
            org = uuid.uuid4()
            for _ in range(3):
                assert _gap(client, _headers(org)).status_code == 200
            assert _gap(client, _headers(org)).status_code == 429
            assert _gap(client, _headers()).status_code == 200


class TestExecutiveSummary:
    def test_counts_one_unit_per_framework(self, client, quota):
        org = uuid.uuid4()
        with (
            patch("src.agents.graph.arun_gap_analysis", _agent()),
            patch("src.reports.generator.ComplianceReportGenerator", _generator()),
        ):
            r = _summary(client, _headers(org), ["CSRD", "DORA"])
        assert r.status_code == 200
        assert r.headers["X-Quota-Remaining"] == "1"

    async def test_a_report_bigger_than_what_is_left_costs_nothing(self, client, quota):
        org = uuid.uuid4()
        agent = _agent()
        with (
            patch("src.agents.graph.arun_gap_analysis", agent),
            patch("src.reports.generator.ComplianceReportGenerator", _generator()),
        ):
            assert _gap(client, _headers(org)).status_code == 200  # 2 left
            r = _summary(client, _headers(org), ["CSRD", "DORA", "GDPR"])
            assert r.status_code == 429
            assert "richiede 3 analisi e ne restano 2" in r.json()["detail"]
            assert r.headers["X-Quota-Remaining"] == "2"
            assert agent.await_count == 1
            # The two units are still there.
            assert (await quota.usage(str(org), limit=3)).used == 1
            assert _summary(client, _headers(org), ["CSRD", "DORA"]).status_code == 200


class TestVerifiedEmail:
    @pytest.mark.parametrize(
        "path", ["/api/v1/reports/gap-analysis", "/api/v1/reports/executive-summary"]
    )
    def test_an_unverified_address_gets_403_and_nothing_runs(self, client, path):
        strict = get_settings().model_copy(update={"require_email_verification": True})
        agent = _agent()
        body = (
            {"framework": "CSRD", "company_profile": PROFILE}
            if path.endswith("gap-analysis")
            else {"frameworks": ["CSRD"], "company_profile": PROFILE}
        )
        with (
            patch("src.auth.dependencies.get_settings", return_value=strict),
            patch("src.auth.dependencies._email_verified_in_db", new=AsyncMock(return_value=False)),
            patch("src.agents.graph.arun_gap_analysis", agent),
        ):
            r = client.post(path, json=body, headers=_headers(email_verified=False))
        assert r.status_code == 403
        assert r.json()["detail"] == "Conferma l'indirizzo email per usare NormaAI."
        agent.assert_not_called()

    def test_a_verified_address_passes(self, client):
        strict = get_settings().model_copy(update={"require_email_verification": True})
        with (
            patch("src.auth.dependencies.get_settings", return_value=strict),
            patch("src.agents.graph.arun_gap_analysis", _agent()),
            patch("src.reports.generator.ComplianceReportGenerator", _generator()),
        ):
            r = _gap(client, _headers(email_verified=True))
        assert r.status_code == 200
