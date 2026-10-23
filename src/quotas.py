"""Daily LLM request quota per organization.

Every call to an intelligence endpoint (Q&A, gap analysis, monitor and their
streaming variants) consumes one unit of the organization's daily quota
(``settings.llm_daily_quota_per_org``; 0 disables the quota). The day rolls
over at 00:00 UTC.

Storage: Redis ``INCR`` on ``normaai:quota:llm:<org_id>:<YYYY-MM-DD>`` with
an ``EXPIRE`` set to the next UTC midnight (plus slack), so counters vanish on
their own. When Redis is unavailable the counter degrades to a bounded
in-process dict (per replica, like ``src.auth.brute_force``), never to
fail-open.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from src.config import get_settings

logger = logging.getLogger(__name__)

KEY_PREFIX = "normaai:quota:llm:"
_MEMORY_MAX_KEYS = 10_000
# Keys are dated, so a counter only needs to outlive its day; the slack covers
# clock skew between replicas.
_EXPIRE_SLACK_SECONDS = 300
# After a failed Redis connection, do not retry on every request.
_RECONNECT_BACKOFF_SECONDS = 30.0


def quota_exceeded_detail(limit: int) -> str:
    """UI-facing (Italian) 429 message."""
    return (
        f"Quota giornaliera dell'organizzazione raggiunta ({limit} richieste). "
        "Riprova domani o contatta info@normaai.org."
    )


def _today(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).strftime("%Y-%m-%d")


def seconds_until_utc_midnight(now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((tomorrow - now).total_seconds()))


@dataclass(frozen=True)
class QuotaStatus:
    """Snapshot of an organization's daily quota."""

    org_id: str
    day: str
    limit: int  # 0 = unlimited
    used: int
    resets_in_seconds: int

    @property
    def unlimited(self) -> bool:
        return self.limit <= 0

    @property
    def remaining(self) -> int:
        if self.unlimited:
            return -1
        return max(0, self.limit - self.used)

    @property
    def allowed(self) -> bool:
        """True when the request that produced this snapshot fits the quota."""
        return self.unlimited or self.used <= self.limit

    @property
    def resets_at(self) -> str:
        return (
            (datetime.now(UTC) + timedelta(seconds=self.resets_in_seconds))
            .replace(microsecond=0)
            .isoformat()
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "org_id": self.org_id,
            "date": self.day,
            "limit": self.limit,
            "used": self.used,
            "remaining": self.remaining,
            "unlimited": self.unlimited,
            "resets_in_seconds": self.resets_in_seconds,
            "resets_at": self.resets_at,
        }


class DailyLLMQuota:
    """Redis-backed per-org daily counter with a bounded in-memory fallback."""

    def __init__(self) -> None:
        self._client: Any = None
        self._available = False
        self._next_connect_attempt = 0.0
        # (org_id, day) -> count; bounded, entries of past days are pruned.
        self._memory: dict[tuple[str, str], int] = {}

    # ─── Redis plumbing ───────────────────────────────────────

    async def connect(self, redis_client: Any) -> None:
        """Use an existing Redis connection (tests / shared pool)."""
        self._client = redis_client
        self._available = redis_client is not None

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:  # noqa: BLE001
                pass
        self._client = None
        self._available = False

    async def _get_redis(self) -> Any:
        """Lazily connect; back off after a failure instead of retrying per request."""
        if self._client is not None:
            return self._client
        if time.monotonic() < self._next_connect_attempt:
            return None
        try:
            import redis.asyncio as aioredis

            settings = get_settings()
            client = aioredis.from_url(  # type: ignore[no-untyped-call]  # redis.asyncio untyped
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=3,
            )
            await client.ping()
            self._client = client
            self._available = True
            return client
        except Exception as e:  # noqa: BLE001
            logger.warning("llm_quota_redis_unavailable: %s", e)
            self._available = False
            self._next_connect_attempt = time.monotonic() + _RECONNECT_BACKOFF_SECONDS
            return None

    @staticmethod
    def _key(org_id: str, day: str) -> str:
        return f"{KEY_PREFIX}{org_id}:{day}"

    # ─── Counting ─────────────────────────────────────────────

    def _status(self, org_id: str, day: str, limit: int, used: int) -> QuotaStatus:
        return QuotaStatus(
            org_id=org_id,
            day=day,
            limit=limit,
            used=used,
            resets_in_seconds=seconds_until_utc_midnight(),
        )

    def _memory_incr(self, org_id: str, day: str, amount: int = 1) -> int:
        key = (org_id, day)
        if key not in self._memory and len(self._memory) >= _MEMORY_MAX_KEYS:
            # Drop counters of past days; if still full (a flood of new orgs
            # during a Redis outage) count the request but do not track it.
            self._memory = {k: v for k, v in self._memory.items() if k[1] == day}
            if len(self._memory) >= _MEMORY_MAX_KEYS:
                return amount
        value = self._memory.get(key, 0) + amount
        self._memory[key] = value
        return value

    async def consume(self, org_id: str, limit: int | None = None) -> QuotaStatus:
        """Count one request for ``org_id`` and report the resulting status.

        The counter is incremented even when the request ends up rejected (the
        n-th request past the limit still counts), which keeps the check a
        single atomic INCR. ``allowed`` tells the caller whether to serve it.
        """
        limit = get_settings().llm_daily_quota_per_org if limit is None else limit
        day = _today()
        if limit <= 0:
            return self._status(org_id, day, limit, 0)

        redis = await self._get_redis()
        if redis is not None:
            try:
                key = self._key(org_id, day)
                pipe = redis.pipeline()
                pipe.incr(key)
                pipe.expire(key, seconds_until_utc_midnight() + _EXPIRE_SLACK_SECONDS)
                used, _ = await pipe.execute()
                return self._status(org_id, day, limit, int(used))
            except Exception as e:  # noqa: BLE001
                logger.warning("llm_quota_redis_error: %s", e)
                self._client = None
                self._available = False
                self._next_connect_attempt = time.monotonic() + _RECONNECT_BACKOFF_SECONDS

        return self._status(org_id, day, limit, self._memory_incr(org_id, day, 1))

    async def usage(self, org_id: str, limit: int | None = None) -> QuotaStatus:
        """Current status WITHOUT consuming."""
        limit = get_settings().llm_daily_quota_per_org if limit is None else limit
        day = _today()
        used = 0
        if limit > 0:
            redis = await self._get_redis()
            if redis is not None:
                try:
                    raw = await redis.get(self._key(org_id, day))
                    used = int(raw) if raw is not None else 0
                    return self._status(org_id, day, limit, used)
                except Exception as e:  # noqa: BLE001
                    logger.warning("llm_quota_redis_error: %s", e)
            used = self._memory.get((org_id, day), 0)
        return self._status(org_id, day, limit, used)

    async def reset(self, org_id: str) -> None:
        """Clear today's counter for ``org_id`` (operations / tests)."""
        day = _today()
        self._memory.pop((org_id, day), None)
        redis = await self._get_redis()
        if redis is not None:
            try:
                await redis.delete(self._key(org_id, day))
            except Exception as e:  # noqa: BLE001
                logger.warning("llm_quota_reset_error: %s", e)

    @property
    def available(self) -> bool:
        return self._available


# Singleton
llm_quota = DailyLLMQuota()
