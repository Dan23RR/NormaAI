"""Tests for org-scoped cache key isolation (RLS tenant isolation).

Verifies that cache keys include org_id so that Organization A's cached
responses are never served to Organization B — even for identical queries.
"""

import pytest

from src.cache import ResponseCache


@pytest.fixture
def cache():
    return ResponseCache()


class TestOrgIsolation:
    def test_same_org_same_key(self, cache):
        """Same org + same query = same cache key."""
        key1 = cache._make_key("qa", "What is CSRD?", org_id="org-123")
        key2 = cache._make_key("qa", "What is CSRD?", org_id="org-123")
        assert key1 == key2

    def test_different_orgs_different_keys(self, cache):
        """Different orgs = different cache keys, even for identical queries."""
        key1 = cache._make_key("qa", "What is CSRD?", org_id="org-A")
        key2 = cache._make_key("qa", "What is CSRD?", org_id="org-B")
        assert key1 != key2

    def test_org_id_none_vs_present(self, cache):
        """Query without org_id produces different key than with org_id."""
        key1 = cache._make_key("qa", "test query", org_id=None)
        key2 = cache._make_key("qa", "test query", org_id="org-123")
        assert key1 != key2

    def test_org_isolation_with_profile(self, cache):
        """Org isolation works even with identical company profiles."""
        profile = {"name": "Test Srl", "sector": "Manufacturing"}
        key1 = cache._make_key("qa", "test", profile=profile, org_id="org-A")
        key2 = cache._make_key("qa", "test", profile=profile, org_id="org-B")
        assert key1 != key2

    def test_org_isolation_across_task_types(self, cache):
        """Org isolation works for all task types."""
        for task_type in ["qa", "gap_analysis", "monitor"]:
            key1 = cache._make_key(task_type, "query", org_id="org-X")
            key2 = cache._make_key(task_type, "query", org_id="org-Y")
            assert key1 != key2, f"Org isolation failed for {task_type}"

    def test_key_is_deterministic_with_org(self, cache):
        """Same inputs always produce the same key (including org_id)."""
        profile = {"name": "Corp", "sector": "Finance"}
        key1 = cache._make_key("qa", "question", profile=profile, org_id="org-99")
        key2 = cache._make_key("qa", "question", profile=profile, org_id="org-99")
        assert key1 == key2
