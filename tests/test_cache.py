"""Tests for the Redis caching layer (src.cache.ResponseCache).

Tests are grouped into:
- Cache key generation (determinism, normalization, isolation)
- TTL configuration per task type
- Graceful degradation when Redis is unavailable
- Round-trip cache behavior with a mocked Redis client
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.cache import CACHEABLE_ABSTENTION_REASONS, ResponseCache, is_cacheable_result

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


def _settings(**update):
    from src.config import get_settings

    return get_settings().model_copy(update=update)


class TestKeyFollowsWhatProducedTheAnswer:
    """An answer is served only for the language it was written in and the
    corpus, provider and model it came from."""

    def test_language_is_part_of_the_key(self, cache):
        italian = cache._make_key("qa", "Entro quando?", org_id="o", language="it")
        english = cache._make_key("qa", "Entro quando?", org_id="o", language="en")
        assert italian != english
        assert italian == cache._make_key("qa", "Entro quando?", org_id="o", language=" IT ")

    def test_corpus_version_is_part_of_the_key(self, cache):
        with patch("src.cache.get_settings", return_value=_settings(corpus_as_of="2026-10-24")):
            old_corpus = cache._make_key("qa", "q", org_id="o", language="it")
        with patch("src.cache.get_settings", return_value=_settings(corpus_as_of="2026-11-18")):
            new_corpus = cache._make_key("qa", "q", org_id="o", language="it")
        with patch(
            "src.cache.get_settings",
            return_value=_settings(
                corpus_as_of="2026-11-18", qdrant_collection="eu_regulations_e5"
            ),
        ):
            other_collection = cache._make_key("qa", "q", org_id="o", language="it")
        assert len({old_corpus, new_corpus, other_collection}) == 3

    def test_provider_and_model_are_part_of_the_key(self, cache):
        haiku = _settings(llm_provider="anthropic", anthropic_model_analysis="claude-haiku-5-5")
        sonnet = _settings(llm_provider="anthropic", anthropic_model_analysis="claude-sonnet-5-5")
        mistral = _settings(llm_provider="mistral")
        keys = set()
        for settings in (haiku, sonnet, mistral):
            with patch("src.cache.get_settings", return_value=settings):
                keys.add(cache._make_key("qa", "q", org_id="o", language="it"))
        assert len(keys) == 3

    def test_corpus_version_reads_collection_and_corpus_date(self):
        from src.cache import corpus_version

        with patch(
            "src.cache.get_settings",
            return_value=_settings(
                qdrant_collection="eu_regulations_e5", corpus_as_of="2026-11-18"
            ),
        ):
            assert corpus_version() == "eu_regulations_e5@2026-11-18"
        with patch("src.cache.get_settings", return_value=_settings(corpus_as_of="")):
            assert corpus_version().endswith("@")

    def test_round_trip_needs_the_same_language(self, cache):
        store = {}
        client = AsyncMock()
        client.get = AsyncMock(side_effect=lambda key: store.get(key))
        client.setex = AsyncMock(side_effect=lambda key, ttl, value: store.__setitem__(key, value))
        cache._client, cache._available = client, True
        answer = {"answer": "Entro 72 ore.", "confidence_score": 0.9}
        assert _run(cache.set("qa", "Entro quando?", answer, org_id="o", language="it"))
        assert _run(cache.get("qa", "Entro quando?", org_id="o", language="it")) == answer
        assert _run(cache.get("qa", "Entro quando?", org_id="o", language="en")) is None


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

    def test_default_setting_keeps_the_map(self):
        with patch("src.cache.get_settings", return_value=_settings(cache_ttl_seconds=3600)):
            assert [ResponseCache.ttl_seconds(t) for t in ("qa", "gap_analysis", "monitor")] == [
                3600,
                1800,
                900,
            ]

    def test_cache_ttl_seconds_scales_every_task(self):
        # CACHE_TTL_SECONDS was never read: setting it changed nothing.
        with patch("src.cache.get_settings", return_value=_settings(cache_ttl_seconds=600)):
            assert [ResponseCache.ttl_seconds(t) for t in ("qa", "gap_analysis", "monitor")] == [
                600,
                300,
                150,
            ]

    def test_set_uses_the_configured_ttl(self, cache):
        client = AsyncMock()
        cache._client, cache._available = client, True
        with patch("src.cache.get_settings", return_value=_settings(cache_ttl_seconds=7200)):
            assert _run(cache.set("qa", "q", {"answer": "a", "confidence_score": 0.9}))
        assert client.setex.call_args.args[1] == 7200

    @pytest.mark.parametrize("ttl", [0, -5])
    def test_zero_turns_the_cache_off(self, cache, ttl):
        client = AsyncMock()
        client.get = AsyncMock(return_value='{"answer": "cached before"}')
        cache._client, cache._available = client, True
        with patch("src.cache.get_settings", return_value=_settings(cache_ttl_seconds=ttl)):
            assert _run(cache.set("qa", "q", {"answer": "a", "confidence_score": 0.9})) is False
            assert _run(cache.get("qa", "q")) is None
        client.setex.assert_not_called()
        client.get.assert_not_called()


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


# ------------------------------------------------------------------ #
#  Cache honesty: failures and transient abstentions are never cached #
# ------------------------------------------------------------------ #


class TestCacheability:
    """Only genuine answers and genuine "the corpus does not cover this"
    abstentions may be cached. Errors and abstentions caused by provider /
    network conditions used to be pinned for the full TTL (an hour for Q&A)."""

    def test_genuine_answer_is_cacheable(self):
        ok, why = is_cacheable_result(
            {"answer": "CSRD applies.", "citations": [], "confidence_score": 0.9}
        )
        assert ok and why == "ok"

    def test_corpus_coverage_abstention_is_cacheable(self):
        for reason in CACHEABLE_ABSTENTION_REASONS:
            ok, _ = is_cacheable_result(
                {"answer": "Not covered.", "abstention_reason": reason, "confidence_score": 0.9}
            )
            assert ok, reason

    def test_llm_answer_saying_corpus_lacks_information_is_cacheable(self):
        # The qa_bot prompt makes the model SAY the database lacks the answer:
        # a stable fact about the corpus, cached like any genuine answer.
        ok, _ = is_cacheable_result(
            {
                "answer": "I don't have sufficient information in my regulatory database.",
                "citations": [],
                "confidence_score": 0.4,
                "requires_expert_review": True,
            }
        )
        assert ok

    @pytest.mark.parametrize(
        "result, expected_reason",
        [
            ({"error": "LLM timed out", "error_code": "llm_timeout"}, "error_result"),
            ({"error": "legacy error without code", "confidence_score": 0.9}, "error_result"),
            ({"answer": "x", "error_code": "retrieval_unavailable"}, "error_result"),
            (
                {"answer": "...", "abstention_reason": "snc_degraded", "confidence_score": 0.4},
                "abstention:snc_degraded",
            ),
            (
                {"answer": "...", "abstention_reason": "snc_low_trust", "confidence_score": 0.4},
                "abstention:snc_low_trust",
            ),
            ({"answer": "raw text", "parse_warning": "not JSON"}, "unparsed_llm_output"),
            ({"raw_response": "[1, 2]", "confidence_score": 0.0}, "unparsed_llm_output"),
            ({"answer": "x", "confidence_score": 0.05}, "low_confidence"),
            ({"answer": "x", "confidence_score": "n/a"}, "low_confidence"),
            ("not a dict", "not_a_dict"),
        ],
    )
    def test_failures_and_transient_abstentions_are_not_cacheable(self, result, expected_reason):
        ok, why = is_cacheable_result(result)
        assert ok is False
        assert why == expected_reason

    def test_set_refuses_network_caused_abstention(self, cache):
        client = AsyncMock()
        cache._client = client
        cache._available = True
        abstention = {
            "answer": "La verifica automatica non è stata completata.",
            "citations": [],
            "confidence_score": 0.4,
            "requires_expert_review": True,
            "abstention_reason": "snc_degraded",
        }
        assert _run(cache.set("qa", "What is CSRD?", abstention)) is False
        client.setex.assert_not_called()

    def test_set_refuses_error_payload(self, cache):
        client = AsyncMock()
        cache._client = client
        cache._available = True
        error = {"error": "Rate limited", "error_code": "llm_rate_limited", "confidence_score": 0.0}
        assert _run(cache.set("qa", "What is CSRD?", error)) is False
        client.setex.assert_not_called()


class TestCitationPolicyCacheability:
    """The unverified-citation policy (src.agents.citation_verifier): a FLAGGED
    answer is a genuine answer and may be cached; the strict-mode abstention
    describes one generation, not the corpus, and is never cached."""

    @staticmethod
    def _unverified():
        return {
            "answer": "Risposta.",
            "citations": [{"framework": "GDPR", "verified": False}],
            "verified_citations": 0,
            "citations_total": 1,
            "confidence_score": 0.9,
        }

    def test_flagged_answer_is_cacheable(self):
        from src.agents.citation_verifier import apply_unverified_policy

        flagged = apply_unverified_policy(self._unverified(), mode="flag")
        assert flagged["requires_expert_review"] is True
        assert is_cacheable_result(flagged) == (True, "ok")

    def test_strict_abstention_is_not_cacheable(self):
        from src.agents.citation_verifier import apply_unverified_policy

        abstention = apply_unverified_policy(self._unverified(), mode="strict")
        assert "unverified_citations" not in CACHEABLE_ABSTENTION_REASONS
        assert is_cacheable_result(abstention) == (False, "abstention:unverified_citations")

    def test_set_refuses_the_strict_abstention(self, cache):
        from src.agents.citation_verifier import apply_unverified_policy

        client = AsyncMock()
        cache._client = client
        cache._available = True
        abstention = apply_unverified_policy(self._unverified(), mode="strict")
        assert _run(cache.set("qa", "What is CSRD?", abstention)) is False
        client.setex.assert_not_called()

    def test_key_version_keeps_entries_of_an_older_shape_out(self, cache):
        # Entries cached before the citation verifier (no verified flags, no
        # counters) live under keys that the current version never computes.
        import src.cache as cache_module

        current = cache._make_key("qa", "What is CSRD?", org_id="org-1")
        with patch.object(cache_module, "CACHE_KEY_VERSION", 1):
            older = cache._make_key("qa", "What is CSRD?", org_id="org-1")
        assert current != older
        assert current.startswith("normaai:llm:qa:")
