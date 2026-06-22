#!/usr/bin/env python3
"""End-to-end two-tenant isolation check against a RUNNING NormaAI API.

This is the staging gate from docs/DEPLOY_READINESS.md S2. Run it AFTER switching
the app to the non-superuser ``normaai_app`` role (the RLS overlay), to confirm
two things at once:

  1. The app still WORKS under FORCE ROW LEVEL SECURITY - register creates the
     org + first user, and create-client inserts a row. If the INSERT policies
     or the register ``set_config`` are wrong, these fail (the role can't write).
  2. Tenants are ISOLATED end-to-end - org B never sees org A's client, by list
     and by direct id (IDOR), and vice-versa.

What it does NOT prove: that the DB role is actually non-superuser. A superuser
bypasses RLS and this script would still pass on the app-level filters alone.
Confirm the role separately:
    psql "$DATABASE_URL" -c "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user;"
    # expect: f | f
and let the gated CI test (tests/test_rls_pool_isolation.py) cover the DB layer.

Usage:
    python scripts/validate_rls_two_tenant.py [BASE_URL]
    BASE_URL defaults to $NORMAAI_BASE_URL or http://localhost:8000
Exit code 0 = all checks passed; 1 = a failure (safe to use as a deploy gate).
"""

from __future__ import annotations

import os
import sys
import uuid

import httpx

BASE_URL = (
    sys.argv[1]
    if len(sys.argv) > 1
    else os.environ.get("NORMAAI_BASE_URL", "http://localhost:8000")
).rstrip("/")

PASSWORD = "Rls-Validate-" + uuid.uuid4().hex[:10]  # meets the 8-char minimum


def _fail(msg: str) -> None:
    print(f"  FAIL: {msg}")
    print("\nRESULT: FAILED - tenant isolation or write path is broken. Do NOT onboard")
    print("two real customers on this instance. See docs/DEPLOY_READINESS.md S2.")
    sys.exit(1)


def _register(client: httpx.Client, label: str) -> str:
    """Register a fresh org + admin and return the access token."""
    suffix = uuid.uuid4().hex[:8]
    body = {
        "email": f"rls-{label}-{suffix}@example.com",
        "password": PASSWORD,
        "name": f"RLS Test {label}",
        "organization_name": f"RLS-Org-{label}-{suffix}",
    }
    r = client.post("/auth/register", json=body)
    if r.status_code != 201:
        _fail(
            f"register org {label} returned {r.status_code} (expected 201) - the "
            f"non-superuser role likely cannot INSERT org/user under FORCE RLS "
            f"(check scripts/setup_app_role.sql policies + register set_config). Body: {r.text[:300]}"
        )
    token = r.json().get("access_token")
    if not token:
        _fail(f"register org {label} returned no access_token: {r.text[:200]}")
    print(f"  ok: registered org {label}")
    return token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_client(client: httpx.Client, token: str, name: str) -> str:
    r = client.post("/api/v1/clients", json={"name": name}, headers=_auth(token))
    if r.status_code != 201:
        _fail(
            f"create client '{name}' returned {r.status_code} (expected 201) - the "
            f"role cannot INSERT into clients under FORCE RLS. Body: {r.text[:300]}"
        )
    cid = r.json().get("id")
    print(f"  ok: created client '{name}' (id={cid})")
    return cid


def _list_client_ids(client: httpx.Client, token: str) -> set[str]:
    r = client.get("/api/v1/clients", headers=_auth(token))
    if r.status_code != 200:
        _fail(f"list clients returned {r.status_code}: {r.text[:200]}")
    return {c["id"] for c in r.json()}


def _create_conversation(client: httpx.Client, token: str) -> str:
    r = client.post("/api/v1/conversations", json={}, headers=_auth(token))
    if r.status_code != 201:
        _fail(
            f"create conversation returned {r.status_code} (expected 201) - the role "
            f"cannot write/read conversations under RLS (missing conversations policy? "
            f"run the updated scripts/setup_app_role.sql). Body: {r.text[:300]}"
        )
    cid = (r.json().get("data") or {}).get("id")
    if not cid:
        _fail(
            "create conversation returned no id - the post-insert re-fetch likely hit the "
            "missing conversations read policy (run the updated scripts/setup_app_role.sql)"
        )
    print(f"  ok: created conversation (id={cid})")
    return cid


def _list_conversation_ids(client: httpx.Client, token: str) -> set[str]:
    r = client.get("/api/v1/conversations", headers=_auth(token))
    if r.status_code != 200:
        _fail(f"list conversations returned {r.status_code}: {r.text[:200]}")
    return {c["id"] for c in r.json().get("data", [])}


def main() -> None:
    print(f"Two-tenant RLS isolation check against {BASE_URL}\n")
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        # health probe so a wrong URL fails clearly, not mid-test
        try:
            h = client.get("/health")
            if h.status_code != 200:
                _fail(f"/health returned {h.status_code}; is the API up at {BASE_URL}?")
        except httpx.HTTPError as e:
            _fail(f"cannot reach {BASE_URL}/health: {e}")

        token_a = _register(client, "A")
        token_b = _register(client, "B")

        id_a = _create_client(client, token_a, f"A-SECRET-{uuid.uuid4().hex[:6]}")
        id_b = _create_client(client, token_b, f"B-SECRET-{uuid.uuid4().hex[:6]}")

        print("\nChecking isolation...")
        a_sees = _list_client_ids(client, token_a)
        b_sees = _list_client_ids(client, token_b)

        if id_a not in a_sees:
            _fail("org A cannot see its OWN client (the org filter is over-restrictive)")
        if id_b not in b_sees:
            _fail("org B cannot see its OWN client")
        if id_b in a_sees:
            _fail("CROSS-TENANT LEAK: org A sees org B's client in the list")
        if id_a in b_sees:
            _fail("CROSS-TENANT LEAK: org B sees org A's client in the list")
        print("  ok: each org's client list contains only its own client")

        # IDOR: A fetching B's client by id must be 404 (not 200, not 403-leak)
        r = client.get(f"/api/v1/clients/{id_b}", headers=_auth(token_a))
        if r.status_code != 404:
            _fail(
                f"IDOR: org A fetching org B's client by id returned {r.status_code} "
                f"(expected 404)"
            )
        print("  ok: cross-tenant fetch-by-id is 404 (no IDOR)")

        # Conversations: init_db.sql ENABLEs RLS on this table but creates NO read
        # policy, so a non-superuser role sees zero rows (and the create endpoint's
        # post-insert re-fetch fails). The clients checks above can't catch this -
        # clients has a policy, conversations doesn't until setup_app_role.sql runs.
        print("\nChecking conversations isolation...")
        conv_a = _create_conversation(client, token_a)
        _create_conversation(client, token_b)
        if conv_a not in _list_conversation_ids(client, token_a):
            _fail("org A cannot see its OWN conversation - conversations RLS read policy missing")
        if conv_a in _list_conversation_ids(client, token_b):
            _fail("CROSS-TENANT LEAK: org B sees org A's conversation")
        print("  ok: conversations are isolated and readable by their owner")

    print("\nRESULT: PASSED - register + create work under the role, and the two")
    print("tenants are isolated end-to-end. (Confirm the role is non-superuser")
    print("separately - see the header note.)")
    sys.exit(0)


if __name__ == "__main__":
    main()
