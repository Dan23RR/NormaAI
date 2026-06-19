"""Security hardening: X-Forwarded-For anti-spoofing + brute-force degradation.

- get_client_ip must read the IP appended by our trusted proxy, never the
  client-forgeable leftmost X-Forwarded-For entry.
- Brute-force protection must degrade to a bounded in-memory counter when Redis
  is down, instead of failing fully open.

Pure logic + async; no real Redis/DB.
"""

from __future__ import annotations

import types

from src.audit import get_client_ip
from src.auth.brute_force import MAX_ATTEMPTS, BruteForceProtection


def _request(headers=None, client_host="10.0.0.1"):
    client = types.SimpleNamespace(host=client_host) if client_host else None
    return types.SimpleNamespace(headers=headers or {}, client=client)


def _patch_proxies(monkeypatch, count):
    from src.config import Settings

    s = Settings(trusted_proxy_count=count, app_secret_key="x" * 40)
    monkeypatch.setattr("src.config.get_settings", lambda: s)


# ── X-Forwarded-For anti-spoofing ────────────────────────────────────────


def test_xff_uses_proxy_appended_ip_not_spoofed_first(monkeypatch):
    _patch_proxies(monkeypatch, 1)
    # Client forged "1.1.1.1"; our single proxy appended the real 203.0.113.7.
    req = _request({"X-Forwarded-For": "1.1.1.1, 203.0.113.7"})
    assert get_client_ip(req) == "203.0.113.7"


def test_xff_single_entry_from_proxy(monkeypatch):
    _patch_proxies(monkeypatch, 1)
    req = _request({"X-Forwarded-For": "203.0.113.7"})
    assert get_client_ip(req) == "203.0.113.7"


def test_xff_two_trusted_proxies(monkeypatch):
    _patch_proxies(monkeypatch, 2)
    # XFF: spoofed, realclient, proxy1 -> real is index len-2 = 1.
    req = _request({"X-Forwarded-For": "9.9.9.9, 203.0.113.7, 10.1.0.2"})
    assert get_client_ip(req) == "203.0.113.7"


def test_xff_ignored_when_no_trusted_proxy(monkeypatch):
    _patch_proxies(monkeypatch, 0)
    # No proxy in front: ignore the forgeable header, use the socket peer.
    req = _request({"X-Forwarded-For": "1.1.1.1"}, client_host="203.0.113.7")
    assert get_client_ip(req) == "203.0.113.7"


def test_xreal_ip_used_when_no_xff(monkeypatch):
    _patch_proxies(monkeypatch, 1)
    req = _request({"X-Real-IP": "203.0.113.9"})
    assert get_client_ip(req) == "203.0.113.9"


def test_falls_back_to_socket_peer(monkeypatch):
    _patch_proxies(monkeypatch, 1)
    req = _request({}, client_host="203.0.113.5")
    assert get_client_ip(req) == "203.0.113.5"


# ── Brute-force in-memory fallback (Redis down) ───────────────────────────


async def _no_redis():
    return None


async def test_bruteforce_memory_fallback_locks_out(monkeypatch):
    bf = BruteForceProtection()
    monkeypatch.setattr(bf, "_get_redis", _no_redis)
    # The first MAX_ATTEMPTS are allowed (return None), then it locks out.
    for _ in range(MAX_ATTEMPTS):
        assert await bf.check_and_increment("user@x.io", "1.2.3.4") is None
    msg = await bf.check_and_increment("user@x.io", "1.2.3.4")
    assert msg is not None and "locked" in msg.lower()


async def test_bruteforce_memory_reset_clears(monkeypatch):
    bf = BruteForceProtection()
    monkeypatch.setattr(bf, "_get_redis", _no_redis)
    for _ in range(MAX_ATTEMPTS):
        await bf.check_and_increment("user@x.io", "1.2.3.4")
    await bf.reset("user@x.io")
    # After reset the window is fresh.
    assert await bf.check_and_increment("user@x.io", "1.2.3.4") is None
    assert await bf.get_remaining_attempts("user@x.io") == MAX_ATTEMPTS - 1


async def test_bruteforce_memory_isolates_accounts(monkeypatch):
    bf = BruteForceProtection()
    monkeypatch.setattr(bf, "_get_redis", _no_redis)
    for _ in range(MAX_ATTEMPTS):
        await bf.check_and_increment("victim@x.io", "1.2.3.4")
    # A different account is unaffected by the victim's lockout.
    assert await bf.check_and_increment("other@x.io", "1.2.3.4") is None
