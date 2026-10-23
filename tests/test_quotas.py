"""Daily LLM quota per organization (src/quotas.py + intelligence wiring).

- in-memory fallback: counts per (org, UTC day), exhaustion, usage, reset,
  day rollover, a 0 limit = unlimited
- Redis path: INCR + EXPIRE pipeline through a tiny fake client, outage falls
  back to memory without failing open
- endpoints: X-Quota-Remaining on 200s (dict + streaming), the Italian 429
  with Retry-After once exhausted, GET /api/v1/system/quota shape
"""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src import quotas
from src.auth.security import create_access_token
from src.quotas import DailyLLMQuota, quota_exceeded_detail, seconds_until_utc_midnight

# ──────────────────────────────────────────────────────────────────────────
#  Unit: memory fallback
# ──────────────────────────────────────────────────────────────────────────


async def _no_redis():
    return None


@pytest.fixture
def quota(monkeypatch):
    q = DailyLLMQuota()
    monkeypatch.setattr(q, "_get_redis", _no_redis)
    return q


class TestMemoryFallback:
    async def test_counts_until_limit_then_denies(self, quota):
        org = str(uuid.uuid4())
        for i in range(1, 4):
            status = await quota.consume(org, limit=3)
            assert status.allowed and status.used == i and status.remaining == 3 - i
        status = await quota.consume(org, limit=3)
        assert status.allowed is False
        assert status.used == 4 and status.remaining == 0

    async def test_orgs_are_isolated(self, quota):
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        for _ in range(2):
            await quota.consume(a, limit=2)
        assert (await quota.consume(a, limit=2)).allowed is False
        assert (await quota.consume(b, limit=2)).allowed is True

    async def test_usage_does_not_consume_and_reset_clears(self, quota):
        org = str(uuid.uuid4())
        await quota.consume(org, limit=5)
        before = await quota.usage(org, limit=5)
        after = await quota.usage(org, limit=5)
        assert before.used == after.used == 1
        await quota.reset(org)
        assert (await quota.usage(org, limit=5)).used == 0

    async def test_zero_limit_is_unlimited(self, quota):
        org = str(uuid.uuid4())
        for _ in range(5):
            status = await quota.consume(org, limit=0)
        assert status.allowed and status.unlimited and status.remaining == -1
        assert status.as_dict()["unlimited"] is True

    async def test_day_rollover_starts_fresh(self, quota, monkeypatch):
        org = str(uuid.uuid4())
        monkeypatch.setattr(quotas, "_today", lambda now=None: "2026-10-23")
        for _ in range(2):
            await quota.consume(org, limit=2)
        assert (await quota.consume(org, limit=2)).allowed is False
        monkeypatch.setattr(quotas, "_today", lambda now=None: "2026-10-24")
        status = await quota.consume(org, limit=2)
        assert status.allowed and status.used == 1 and status.day == "2026-10-24"

    async def test_limit_defaults_to_settings(self, quota):
        from src.config import get_settings

        patched = get_settings().model_copy(update={"llm_daily_quota_per_org": 1})
        with patch("src.quotas.get_settings", return_value=patched):
            assert (await quota.consume(str(uuid.uuid4()))).limit == 1

    def test_memory_bound_prunes_other_days(self, quota, monkeypatch):
        monkeypatch.setattr(quotas, "_MEMORY_MAX_KEYS", 3)
        quota._memory = {("a", "2026-01-01"): 5, ("b", "2026-01-01"): 5, ("c", "2026-01-01"): 5}
        assert quota._memory_incr("new", "2026-01-02") == 1
        assert quota._memory == {("new", "2026-01-02"): 1}

    def test_messages_and_helpers(self):
        assert quota_exceeded_detail(200) == (
            "Quota giornaliera dell'organizzazione raggiunta (200 richieste). "
            "Riprova domani o contatta info@normaai.org."
        )
        at = datetime(2026, 10, 23, 23, 59, 30, tzinfo=UTC)
        assert seconds_until_utc_midnight(at) == 30
        assert 1 <= seconds_until_utc_midnight() <= 86400


# ──────────────────────────────────────────────────────────────────────────
#  Unit: Redis path
# ──────────────────────────────────────────────────────────────────────────


class _FakePipeline:
    def __init__(self, store: dict, log: list):
        self._store, self._log, self._ops = store, log, []

    def incr(self, key):
        self._ops.append(("incr", key))

    def expire(self, key, ttl):
        self._ops.append(("expire", key, ttl))

    async def execute(self):
        results = []
        for op in self._ops:
            self._log.append(op)
            if op[0] == "incr":
                self._store[op[1]] = self._store.get(op[1], 0) + 1
                results.append(self._store[op[1]])
            else:
                results.append(True)
        return results


class _FakeRedis:
    def __init__(self):
        self.store: dict = {}
        self.log: list = []

    def pipeline(self):
        return _FakePipeline(self.store, self.log)

    async def get(self, key):
        return self.store.get(key)

    async def delete(self, key):
        self.store.pop(key, None)


class TestRedisPath:
    async def test_incr_with_daily_expiry(self):
        q = DailyLLMQuota()
        redis = _FakeRedis()
        await q.connect(redis)
        org = str(uuid.uuid4())
        s1 = await q.consume(org, limit=2)
        s2 = await q.consume(org, limit=2)
        s3 = await q.consume(org, limit=2)
        assert (s1.used, s2.used, s3.used) == (1, 2, 3)
        assert s3.allowed is False
        key = f"{quotas.KEY_PREFIX}{org}:{s1.day}"
        assert redis.store[key] == 3
        expire_ops = [op for op in redis.log if op[0] == "expire"]
        assert expire_ops and all(op[1] == key for op in expire_ops)
        # TTL covers the rest of the day plus slack, never more than a day + slack.
        assert all(0 < op[2] <= 86400 + quotas._EXPIRE_SLACK_SECONDS for op in expire_ops)
        assert (await q.usage(org, limit=2)).used == 3
        await q.reset(org)
        assert (await q.usage(org, limit=2)).used == 0

    async def test_redis_error_falls_back_to_memory(self):
        q = DailyLLMQuota()
        broken = MagicMock()
        broken.pipeline.side_effect = RuntimeError("connection reset")
        await q.connect(broken)
        org = str(uuid.uuid4())
        with patch.object(q, "_get_redis", new=AsyncMock(side_effect=[broken, None, None])):
            s1 = await q.consume(org, limit=1)
            s2 = await q.consume(org, limit=1)
        assert s1.allowed is True
        assert s2.allowed is False  # still enforced from memory, not fail-open

    async def test_connect_failure_backs_off(self, monkeypatch):
        q = DailyLLMQuota()
        attempts = []

        def _boom(*_a, **_k):
            attempts.append(1)
            raise ConnectionError("refused")

        monkeypatch.setattr("redis.asyncio.from_url", _boom)
        assert await q._get_redis() is None
        assert await q._get_redis() is None  # within the back-off window: no retry
        assert len(attempts) == 1
        assert q.available is False


# ──────────────────────────────────────────────────────────────────────────
#  Endpoints
# ──────────────────────────────────────────────────────────────────────────


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
def client(monkeypatch):
    with (
        patch("src.api.lifespan.validate_settings_or_exit") as mock_settings,
        patch("src.api.lifespan.db_manager", create=True),
        patch.dict(
            "sys.modules",
            {"src.nlp.embedding.indexer": MagicMock(), "src.db.engine": MagicMock()},
        ),
    ):
        from src.config import get_settings

        mock_settings.return_value = get_settings()

        from fastapi.testclient import TestClient

        from src.api.main import app, app_state, limiter

        app_state.qdrant_available = True
        app_state.llm_available = True
        app_state.indexer = MagicMock()
        limiter.enabled = False

        # Force the in-memory fallback (no live Redis in the offline suite / a
        # deterministic counter in CI where Redis exists).
        monkeypatch.setattr(quotas.llm_quota, "_get_redis", _no_redis)
        quotas.llm_quota._memory.clear()

        try:
            from src.cache import response_cache

            response_cache._available = False
            response_cache._client = None
        except ImportError:
            pass

        yield TestClient(app)


def _headers(org_id=None):
    token = create_access_token(uuid.uuid4(), org_id or uuid.uuid4(), "admin")
    return {"Authorization": f"Bearer {token}"}


def _with_limit(limit: int):
    from src.config import get_settings

    return patch(
        "src.quotas.get_settings",
        return_value=get_settings().model_copy(update={"llm_daily_quota_per_org": limit}),
    )


class TestIntelligenceQuota:
    def test_qa_exposes_remaining_and_then_429(self, client):
        org = uuid.uuid4()
        with (
            _with_limit(2),
            patch("src.agents.graph.arun_qa", new_callable=AsyncMock) as qa,
        ):
            qa.return_value = {"answer": "ok", "citations": [], "confidence_score": 0.9}
            r1 = client.post(
                "/api/v1/qa", json={"question": "What is CSRD?"}, headers=_headers(org)
            )
            r2 = client.post(
                "/api/v1/qa", json={"question": "What is DORA?"}, headers=_headers(org)
            )
            r3 = client.post(
                "/api/v1/qa", json={"question": "What is NIS2?"}, headers=_headers(org)
            )
        assert (r1.status_code, r2.status_code, r3.status_code) == (200, 200, 429)
        assert r1.headers["X-Quota-Remaining"] == "1"
        assert r2.headers["X-Quota-Remaining"] == "0"
        assert r3.headers["X-Quota-Remaining"] == "0"
        assert int(r3.headers["Retry-After"]) >= 1
        assert r3.json()["detail"] == quota_exceeded_detail(2)
        assert (
            "Quota giornaliera dell'organizzazione raggiunta (2 richieste)" in r3.json()["detail"]
        )
        assert qa.await_count == 2  # the rejected request never reached the LLM

    def test_quota_is_per_org(self, client):
        with (
            _with_limit(1),
            patch("src.agents.graph.arun_qa", new_callable=AsyncMock) as qa,
        ):
            qa.return_value = {"answer": "ok", "citations": [], "confidence_score": 0.9}
            body = {"question": "What is CSRD?"}
            assert client.post("/api/v1/qa", json=body, headers=_headers()).status_code == 200
            assert client.post("/api/v1/qa", json=body, headers=_headers()).status_code == 200

    def test_streaming_endpoint_carries_header_and_quota(self, client):
        org = uuid.uuid4()
        with (
            _with_limit(1),
            patch("src.agents.graph.arun_qa", new_callable=AsyncMock) as qa,
        ):
            qa.return_value = {"answer": "ok", "citations": [], "confidence_score": 0.9}
            body = {"question": "What is CSRD?"}
            r1 = client.post("/api/v1/qa/stream", json=body, headers=_headers(org))
            r2 = client.post("/api/v1/qa/stream", json=body, headers=_headers(org))
        assert r1.status_code == 200
        assert r1.headers["X-Quota-Remaining"] == "0"
        assert r2.status_code == 429

    @pytest.mark.parametrize(
        ("path", "body"),
        [
            ("/api/v1/gap-analysis", {"framework": "CSRD", "company_profile": {"name": "Acme"}}),
            (
                "/api/v1/monitor",
                {
                    "regulation_change": "Omnibus raised the CSRD thresholds",
                    "company_profile": {"name": "Acme"},
                },
            ),
        ],
    )
    def test_gap_and_monitor_are_quota_gated(self, client, path, body):
        org = uuid.uuid4()
        with (
            _with_limit(1),
            patch("src.agents.graph.arun_gap_analysis", new_callable=AsyncMock) as gap,
            patch("src.agents.graph.arun_monitor_check", new_callable=AsyncMock) as mon,
        ):
            gap.return_value = {"framework": "CSRD", "overall_score": 1.0}
            mon.return_value = {"applicability": "YES"}
            r1 = client.post(path, json=body, headers=_headers(org))
            r2 = client.post(path, json=body, headers=_headers(org))
        assert r1.status_code == 200, r1.text
        assert r1.headers["X-Quota-Remaining"] == "0"
        assert r2.status_code == 429

    def test_unlimited_when_zero(self, client):
        org = uuid.uuid4()
        with (
            _with_limit(0),
            patch("src.agents.graph.arun_qa", new_callable=AsyncMock) as qa,
        ):
            qa.return_value = {"answer": "ok", "citations": [], "confidence_score": 0.9}
            for _ in range(3):
                r = client.post(
                    "/api/v1/qa", json={"question": "What is CSRD?"}, headers=_headers(org)
                )
        assert r.status_code == 200
        assert r.headers["X-Quota-Remaining"] == "-1"


class TestQuotaEndpoint:
    def test_requires_auth(self, client):
        assert client.get("/api/v1/system/quota").status_code == 401

    def test_reports_usage_for_callers_org(self, client):
        org = uuid.uuid4()
        with (
            _with_limit(5),
            patch("src.agents.graph.arun_qa", new_callable=AsyncMock) as qa,
        ):
            qa.return_value = {"answer": "ok", "citations": [], "confidence_score": 0.9}
            client.post("/api/v1/qa", json={"question": "What is CSRD?"}, headers=_headers(org))
            r = client.get("/api/v1/system/quota", headers=_headers(org))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["org_id"] == str(org)
        assert body["limit"] == 5 and body["used"] == 1 and body["remaining"] == 4
        assert body["unlimited"] is False
        assert body["date"] == datetime.now(UTC).strftime("%Y-%m-%d")
        assert 1 <= body["resets_in_seconds"] <= 86400
        assert body["resets_at"].endswith("+00:00")
