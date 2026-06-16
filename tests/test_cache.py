"""Tests for the Redis caching layer (src.cache.ResponseCache).

Tests are grouped into:
- Cache key generation (determinism, normalization, isolation)
- TTL configuration per task type
- Graceful degradation when Redis is unavailable
- Round-trip cache behavior with a mocked Redis client
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.cache import ResponseCache

# ------------------------------------------------------------------ #
#  Fixtures                                                           #
# ------------------------------------------------------------------ #


@pytest.fixture
def cache():
    """Cache instance (no live Redis -- tests use _make_key directly
    or mock the Redis client)."""
    return ResponseCache()


def _run(coro):
    """Helper to run async code in sync tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ------------------------------------------------------------------ #
#  Cache Key Generation                                               #
# ------------------------------------------------------------------ #


class TestCacheKeyGeneration:
    def test_same_inputs_produce_same_key(self, cache):
        key1 = cache._make_key("qa", "What is CSRD?")
        key2 = cache._make_key("qa", "What is CSRD?")
        assert key1 == key2

    def test_different_queries_produce_different_keys(self, cache):
        key1 = cache._make_key("qa", "What is CSRD?")
        key2 = cache._make_key("qa", "What is GDPR?")
        assert key1 != key2

    def test_different_task_types_produce_different_keys(self, cache):
        key1 = cache._make_key("qa", "test query")
        key2 = cache._make_key("gap_analysis", "test query")
        assert key1 != key2

    def test_case_insensitive_queries(self, cache):
        key1 = cache._make_key("qa", "What is CSRD?")
        key2 = cache._make_key("qa", "what is csrd?")
        assert key1 == key2

    def test_whitespace_normalized(self, cache):
        key1 = cache._make_key("qa", "What is CSRD?")
        key2 = cache._make_key("qa", "  What is CSRD?  ")
        assert key1 == key2

    def test_profile_affects_key(self, cache):
        profile = {"name": "Test Srl", "sector": "Manufacturing"}
        key1 = cache._make_key("qa", "test", profile=profile)
        key2 = cache._make_key("qa", "test", profile=None)
        assert key1 != key2

    def test_different_profiles_produce_different_keys(self, cache):
        p1 = {"name": "Company A", "sector": "Tech"}
        p2 = {"name": "Company B", "sector": "Finance"}
        key1 = cache._make_key("qa", "test", profile=p1)
        key2 = cache._make_key("qa", "test", profile=p2)
        assert key1 != key2

    def test_profile_key_order_independent(self, cache):
        """JSON key ordering should not affect the cache key."""
        p1 = {"name": "Test", "sector": "Tech"}
        p2 = {"sector": "Tech", "name": "Test"}
        key1 = cache._make_key("qa", "test", profile=p1)
        key2 = cache._make_key("qa", "test", profile=p2)
        assert key1 == key2

    def test_key_has_correct_prefix(self, cache):
        key = cache._make_key("qa", "test")
        assert key.startswith("normaai:llm:qa:")

    def test_key_contains_task_type(self, cache):
        key = cache._make_key("gap_analysis", "test")
        assert ":gap_analysis:" in key

    def test_key_length_is_bounded(self, cache):
        """Even very long queries should produce reasonably sized keys."""
        long_query = "x" * 10_000
        key = cache._make_key("qa", long_query)
        # prefix + task + ":" + 16-char hash
        assert len(key) < 100


# ------------------------------------------------------------------ #
#  TTL Configuration                                                  #
# ------------------------------------------------------------------ #


class TestCacheTTL:
    def test_qa_ttl_is_1_hour(self):
        assert ResponseCache.TTL_MAP["qa"] == 3600

    def test_gap_analysis_ttl_is_30_min(self):
        assert ResponseCache.TTL_MAP["gap_analysis"] == 1800

    def test_monitor_ttl_is_15_min(self):
        assert ResponseCache.TTL_MAP["monitor"] == 900

    def test_all_ttls_are_positive(self):
        for task, ttl in ResponseCache.TTL_MAP.items():
            assert ttl > 0, f"{task} TTL should be positive"

    def test_monitor_has_shortest_ttl(self):
        """Monitor data is most time-sensitive."""
        assert ResponseCache.TTL_MAP["monitor"] < ResponseCache.TTL_MAP["qa"]
        assert ResponseCache.TTL_MAP["monitor"] < ResponseCache.TTL_MAP["gap_analysis"]


# ------------------------------------------------------------------ #
#  Graceful Degradation (Redis unavailable)                           #
# ------------------------------------------------------------------ #


class TestCacheAvailability:
    def test_get_returns_none_when_redis_unavailable(self, cache):
        """Cache should gracefully return None when Redis is down."""
        result = _run(cache.get("qa", "test"))
        assert result is None

    def test_set_returns_false_when_redis_unavailable(self, cache):
        """Cache should return False on write failure."""
        result = _run(cache.set("qa", "test", {"answer": "test"}))
        assert result is False

    def test_invalidate_returns_false_when_redis_unavailable(self, cache):
        result = _run(cache.invalidate("qa", "test"))
        assert result is False


# ------------------------------------------------------------------ #
#  Round-trip behavior with mocked Redis                              #
# ------------------------------------------------------------------ #


class TestCacheRoundTrip:
    @pytest.fixture
    def mock_redis(self):
        """Mock async Redis client with in-memory storage."""
        store = {}
        client = AsyncMock()

        async def mock_get(key):
            return store.get(key)

        async def mock_setex(key, ttl, value):
            store[key] = value

        async def mock_delete(key):
            store.pop(key, None)

        async def mock_ping():
            return True

        client.get = AsyncMock(side_effect=mock_get)
        client.setex = AsyncMock(side_effect=mock_setex)
        client.delete = AsyncMock(side_effect=mock_delete)
        client.ping = AsyncMock(side_effect=mock_ping)
        return client, store

    def test_set_then_get(self, cache, mock_redis):
        """Stored value should be retrievable."""
        client, store = mock_redis
        cache._client = client
        cache._available = True

        payload = {
            "answer": "CSRD is the Corporate Sustainability Reporting Directive.",
            "confidence_score": 0.92,
        }
        success = _run(cache.set("qa", "What is CSRD?", payload))
        assert success is True

        result = _run(cache.get("qa", "What is CSRD?"))
        assert result is not None
        assert result["answer"] == payload["answer"]
        assert result["confidence_score"] == 0.92

    def test_get_missing_key_returns_none(self, cache, mock_redis):
        client, store = mock_redis
        cache._client = client
        cache._available = True
        result = _run(cache.get("qa", "nonexistent query"))
        assert result is None

    def test_invalidate_removes_entry(self, cache, mock_redis):
        client, store = mock_redis
        cache._client = client
        cache._available = True

        _run(cache.set("qa", "test query", {"answer": "test"}))
        assert _run(cache.get("qa", "test query")) is not None

        _run(cache.invalidate("qa", "test query"))
        assert _run(cache.get("qa", "test query")) is None

    def test_set_calls_setex_with_correct_ttl(self, cache, mock_redis):
        client, store = mock_redis
        cache._client = client
        cache._available = True

        _run(cache.set("monitor", "test", {"data": "value"}))
        # setex should have been called with ttl=900 (monitor TTL)
        client.setex.assert_called_once()
        call_args = client.setex.call_args
        assert call_args[0][1] == 900  # TTL for monitor

    def test_different_task_types_are_isolated(self, cache, mock_redis):
        """qa and gap_analysis caches should not collide."""
        client, store = mock_redis
        cache._client = client
        cache._available = True

        _run(cache.set("qa", "CSRD question", {"answer": "QA answer"}))
        _run(cache.set("gap_analysis", "CSRD question", {"answer": "Gap answer"}))

        qa_result = _run(cache.get("qa", "CSRD question"))
        gap_result = _run(cache.get("gap_analysis", "CSRD question"))

        assert qa_result["answer"] == "QA answer"
        assert gap_result["answer"] == "Gap answer"
