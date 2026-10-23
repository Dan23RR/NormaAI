"""Redis caching layer for LLM responses.

Caches expensive LLM calls (Q&A, gap analysis, monitor) to reduce API costs
and improve response times. Cache keys are derived from the request parameters.

TTL strategy:
- Q&A responses: 1 hour (regulations don't change frequently)
- Gap analysis: 30 minutes (company profile-dependent)
- Monitor impact: 15 minutes (time-sensitive regulatory changes)

Cache honesty: only GENUINE results are cached - real answers and abstentions
that describe the corpus ("the knowledge base does not cover this"). A failure
or an abstention caused by the pipeline's own transient state (provider/network
errors, an SNC run whose resamples failed, stochastic disagreement) must not be
pinned for an hour: the next request may well succeed. See is_cacheable_result.
"""

import hashlib
import json
import logging

from src.config import get_settings

logger = logging.getLogger(__name__)

# Abstention reasons that describe the CORPUS rather than a transient pipeline
# condition; only these may be cached. SNC abstentions ("snc_low_trust",
# "snc_degraded") are never cached: the first is stochastic, the second is a
# provider failure in disguise.
CACHEABLE_ABSTENTION_REASONS: frozenset[str] = frozenset(
    {"corpus_not_covering", "no_relevant_sources"}
)

# Below this confidence a result is not worth pinning for the TTL.
MIN_CACHEABLE_CONFIDENCE = 0.1


def is_cacheable_result(result: object) -> tuple[bool, str]:
    """Decide whether an agent result may be cached.

    Returns ``(cacheable, reason)``; ``reason`` names the rule that rejected the
    result (for logs) or is ``"ok"``.
    """
    if not isinstance(result, dict):
        return False, "not_a_dict"
    if result.get("error") or result.get("error_code"):
        return False, "error_result"
    if result.get("parse_warning") or "raw_response" in result:
        # The LLM output could not be parsed: not a genuine structured answer.
        return False, "unparsed_llm_output"
    reason = result.get("abstention_reason")
    if reason and str(reason) not in CACHEABLE_ABSTENTION_REASONS:
        return False, f"abstention:{reason}"
    try:
        confidence = float(result.get("confidence_score", 1.0))
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence < MIN_CACHEABLE_CONFIDENCE:
        return False, "low_confidence"
    return True, "ok"


class ResponseCache:
    """Async Redis cache for LLM responses.

    Falls back gracefully (returns None / False) when Redis is not
    available, so callers never need to handle connection errors.
    """

    # TTL in seconds per task type
    TTL_MAP = {
        "qa": 3600,  # 1 hour
        "gap_analysis": 1800,  # 30 minutes
        "monitor": 900,  # 15 minutes
    }
    KEY_PREFIX = "normaai:llm:"

    def __init__(self):
        self._client = None
        self._available = False

    async def connect(self) -> bool:
        """Connect to Redis. Returns True if successful."""
        try:
            import redis.asyncio as aioredis

            settings = get_settings()
            self._client = aioredis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            await self._client.ping()
            self._available = True
            logger.info("redis_cache_connected")
            return True
        except Exception as e:
            logger.warning("redis_cache_unavailable: %s", e)
            self._available = False
            return False

    async def close(self):
        """Close Redis connection."""
        if self._client:
            await self._client.aclose()
            self._client = None
            self._available = False

    def _make_key(
        self,
        task_type: str,
        query: str,
        profile: dict | None = None,
        org_id: str | None = None,
    ) -> str:
        """Generate a deterministic, org-scoped cache key.

        Including org_id ensures tenant isolation: org A's cached results
        are never served to org B, even for identical queries.
        """
        key_data = {
            "task_type": task_type,
            "query": query.strip().lower(),
        }
        if org_id:
            key_data["org_id"] = org_id
        if profile:
            key_data["profile"] = {
                "name": profile.get("name", ""),
                "sector": profile.get("sector", ""),
                "employee_count": profile.get("employee_count", 0),
                "revenue_eur": profile.get("revenue_eur", 0),
                "jurisdictions": sorted(profile.get("jurisdictions", [])),
                "applicable_frameworks": sorted(profile.get("applicable_frameworks", [])),
            }
        key_hash = hashlib.sha256(json.dumps(key_data, sort_keys=True).encode()).hexdigest()[:32]
        return f"{self.KEY_PREFIX}{task_type}:{key_hash}"

    async def get(
        self,
        task_type: str,
        query: str,
        profile: dict | None = None,
        org_id: str | None = None,
    ) -> dict | None:
        """Get cached response. Returns None on miss or if cache unavailable.

        Args:
            org_id: Organization ID for tenant-isolated cache keys.
        """
        if not self._available or not self._client:
            return None
        try:
            key = self._make_key(task_type, query, profile, org_id=org_id)
            cached = await self._client.get(key)
            if cached:
                logger.info("cache_hit: %s %s", task_type, key[-12:])
                return json.loads(cached)
            return None
        except Exception as e:
            logger.warning("cache_get_error: %s %s", task_type, e)
            return None

    async def set(
        self,
        task_type: str,
        query: str,
        result: dict,
        profile: dict | None = None,
        org_id: str | None = None,
    ) -> bool:
        """Cache a response with tenant isolation.

        Args:
            org_id: Organization ID for tenant-isolated cache keys.
        """
        if not self._available or not self._client:
            return False
        try:
            # Only genuine answers / corpus-coverage abstentions are cached.
            cacheable, why = is_cacheable_result(result)
            if not cacheable:
                logger.info("cache_skip: %s reason=%s", task_type, why)
                return False

            key = self._make_key(task_type, query, profile, org_id=org_id)
            ttl = self.TTL_MAP.get(task_type, 1800)
            await self._client.setex(
                key,
                ttl,
                json.dumps(result, ensure_ascii=False),
            )
            logger.info("cache_set: %s ttl=%d %s", task_type, ttl, key[-12:])
            return True
        except Exception as e:
            logger.warning("cache_set_error: %s %s", task_type, e)
            return False

    async def invalidate(
        self, task_type: str, query: str | None = None, profile: dict | None = None
    ) -> bool:
        """Invalidate a specific cache entry or all entries for a task type.

        If query is provided, invalidates the specific key.
        If only task_type is provided, invalidates all entries for that type.
        Returns True if successful.
        """
        if not self._available or not self._client:
            return False
        try:
            if query is not None:
                # Invalidate a specific key
                key = self._make_key(task_type, query, profile)
                await self._client.delete(key)
                logger.info("cache_invalidated: key=%s", key[-12:])
                return True
            else:
                # Invalidate all entries for a task type
                keys = []
                async for key in self._client.scan_iter(f"{self.KEY_PREFIX}{task_type}:*"):
                    keys.append(key)
                if keys:
                    await self._client.delete(*keys)
                    logger.info("cache_invalidated: count=%d type=%s", len(keys), task_type)
                return True
        except Exception as e:
            logger.warning("cache_invalidate_error: %s %s", task_type, e)
            return False

    @property
    def available(self) -> bool:
        return self._available


# Singleton instance
response_cache = ResponseCache()
