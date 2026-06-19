"""Deeper-flow tests for the public /api/v1/leads funnel (src/api/routers/leads.py).

test_leads.py already covers VALIDATION (422s) and schema/openapi shape. This
file adds the *behavioural* flow that those tests deliberately skip:

- successful 201: lead persisted (db.add + commit) AND a signed download_url
  returned in the response body;
- idempotent re-submit within 24h: an existing recent lead short-circuits the
  insert and the response message/URL reflect the existing lead;
- per-IP DB rate-limit -> 429 once >= RATE_LIMIT_MAX_PER_IP recent leads exist;
- the Resend email-send path: send_codex_email is invoked with the captured
  email + absolute URL, success flips the response message and writes
  last_email_sent_at; a send failure records email_error and degrades the
  message gracefully (still 201);
- referer / user-agent / source / ip tracking persisted on the Lead row.

Isolation notes (CRITICAL - this module's old fixture caused sys.modules
pollution)
--------------------------------------------------------------------------------
We replicate test_leads.py's fixture EXACTLY: a bare ``TestClient(app)`` (no
``with`` context manager, so lifespan startup/shutdown never runs), lifespan
deps patched, and ``src.db.engine`` / the indexer replaced by MagicMock in
``sys.modules`` *before* importing the app. Under that patch the router's
``get_db_session`` dependency is itself a MagicMock, so we never touch the real
sqlite test.db: instead we inject a fake AsyncSession via
``app.dependency_overrides`` (keyed off the router module's own
``get_db_session`` object, which is exactly what FastAPI registered as the
route dependency) and patch ``src.api.routers.leads.send_codex_email``.

Anti-pollution guarantees, so this file is safe in ANY suite order:
- the ``client`` fixture clears ``app.dependency_overrides`` on teardown;
- an autouse fixture evicts ``src.api.main`` + ``src.api.routers.*`` +
  ``src.auth.router`` from ``sys.modules`` after every test, so the modules
  bound here (against the MagicMock engine) do not leak into sibling files that
  re-import the routers (mirrors test_critical_routers.py's _restore_module_cache).
"""

from __future__ import annotations

import sys
import uuid
from unittest.mock import MagicMock, patch

import pytest

# ──────────────────────────────────────────────────────────────────────────
#  Fake async DB session (no real engine, no real test.db)
# ──────────────────────────────────────────────────────────────────────────


class _CountResult:
    def __init__(self, value: int) -> None:
        self._value = value

    def scalar(self):
        return self._value


class _LeadResult:
    def __init__(self, lead) -> None:  # noqa: ANN001
        self._lead = lead

    def scalar_one_or_none(self):
        return self._lead


class _FakeSession:
    """Minimal AsyncSession stand-in for create_lead's access pattern.

    Dispatches ``execute`` by rendered SQL:
      - ``SELECT count(`` -> _ip_recent_count    -> .scalar()
      - ``SELECT`` (other) -> _find_recent_lead   -> .scalar_one_or_none()
      - ``UPDATE``        -> email-tracking write -> recorded, no return contract
    Records everything the assertions care about (added leads, commits,
    rendered UPDATE statements).
    """

    def __init__(self, *, ip_recent_count: int = 0, existing_lead=None) -> None:  # noqa: ANN001
        self._ip_recent_count = ip_recent_count
        self._existing_lead = existing_lead
        self.added: list = []
        self.commit_count = 0
        self.refreshed: list = []
        self.update_statements: list[str] = []
        self.rolled_back = False
        self.closed = False

    async def execute(self, stmt, *args, **kwargs):  # noqa: ANN001
        text = str(stmt).lstrip()
        upper = text.upper()
        if upper.startswith("SELECT COUNT("):
            return _CountResult(self._ip_recent_count)
        if upper.startswith("SELECT"):
            return _LeadResult(self._existing_lead)
        if upper.startswith("UPDATE"):
            self.update_statements.append(text)
            return MagicMock(name="update_result")
        raise AssertionError(f"unexpected SQL in fake session: {text[:60]!r}")

    def add(self, obj) -> None:  # noqa: ANN001 - sync, like real Session.add
        self.added.append(obj)

    async def commit(self) -> None:
        self.commit_count += 1

    async def refresh(self, obj) -> None:  # noqa: ANN001
        # Real refresh would load server-generated columns; the only one the
        # handler reads afterwards is ``id``. The ORM default is uuid4 but that
        # only fires on a real flush, so assign one here if missing.
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        self.refreshed.append(obj)

    async def rollback(self) -> None:  # pragma: no cover - happy paths don't hit it
        self.rolled_back = True

    async def close(self) -> None:
        self.closed = True


# ──────────────────────────────────────────────────────────────────────────
#  Fixtures (mirror test_leads.py EXACTLY) + anti-pollution
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _evict_app_modules():
    """Evict app/router modules imported here (bound to the MagicMock engine)
    after each test, so they never leak into sibling test files that re-import
    the routers against the real engine. Mirrors
    test_critical_routers.py::_restore_module_cache.
    """
    yield
    for name in list(sys.modules):
        if (
            name == "src.api.main"
            or name.startswith("src.api.routers")
            or name == "src.auth.router"
        ):
            sys.modules.pop(name, None)


@pytest.fixture
def app_objects():
    """Import the FastAPI app with heavy lifespan deps mocked and the DB engine
    replaced by a MagicMock in sys.modules. Yields (app, leads_module).

    Clears ``app.dependency_overrides`` on teardown so injected fakes never leak.
    """
    with (
        patch("src.api.lifespan.validate_settings_or_exit") as mock_settings,
        patch("src.api.lifespan.db_manager", create=True),
        patch.dict(
            "sys.modules",
            {
                "src.nlp.embedding.indexer": MagicMock(),
                "src.db.engine": MagicMock(),
            },
        ),
    ):
        from src.config import get_settings

        mock_settings.return_value = get_settings()

        from src.api.main import app, app_state, limiter

        app_state.qdrant_available = True
        app_state.llm_available = True
        limiter.enabled = False  # disable slowapi decorator limiter; DB limit still tested

        import src.api.routers.leads as leads_module

        try:
            yield app, leads_module
        finally:
            app.dependency_overrides.clear()


@pytest.fixture
def client(app_objects):
    from fastapi.testclient import TestClient

    app, _leads = app_objects
    # raise_server_exceptions=False so a 500 surfaces as a response, not a raise,
    # keeping assertions about status codes meaningful even on unexpected paths.
    return TestClient(app, raise_server_exceptions=True)


def _override_db(app, leads_module, session: _FakeSession) -> None:
    """Inject ``session`` for the router's get_db_session dependency."""

    async def _fake_get_db_session():
        yield session

    app.dependency_overrides[leads_module.get_db_session] = _fake_get_db_session


# ──────────────────────────────────────────────────────────────────────────
#  Successful capture (201): persistence + signed download_url
# ──────────────────────────────────────────────────────────────────────────


class TestSuccessfulCapture:
    def test_new_lead_persisted_and_download_url_returned(self, app_objects, client):
        app, leads_module = app_objects
        session = _FakeSession(ip_recent_count=0, existing_lead=None)
        _override_db(app, leads_module, session)

        with patch.object(leads_module, "send_codex_email", return_value=(True, None)):
            r = client.post(
                "/api/v1/leads",
                json={"email": "founder@acme.example", "org_name": "Acme Srl", "role": "CFO"},
            )

        assert r.status_code == 201
        body = r.json()
        assert body["ok"] is True
        # A signed, relative download URL must be returned for a fresh lead.
        assert body["download_url"], "expected a download_url for a new lead"
        assert body["download_url"].startswith("/api/v1/codex/download?t=")

        # The lead was actually persisted (add + commit), not just echoed.
        assert len(session.added) == 1
        lead = session.added[0]
        assert lead.email == "founder@acme.example"
        assert lead.org_name == "Acme Srl"
        assert lead.role == "CFO"
        assert lead.status == "new"
        assert session.commit_count >= 1

    def test_download_url_token_validates_round_trip(self, app_objects, client):
        """The token embedded in the returned URL must verify back to the
        persisted lead's id (real HMAC round-trip, not a placeholder)."""
        app, leads_module = app_objects
        session = _FakeSession()
        _override_db(app, leads_module, session)

        with patch.object(leads_module, "send_codex_email", return_value=(True, None)):
            r = client.post("/api/v1/leads", json={"email": "verify@acme.example"})

        assert r.status_code == 201
        url = r.json()["download_url"]
        token = url.split("t=", 1)[1]
        lead = session.added[0]
        assert leads_module.verify_download_token(token) == lead.id

    def test_default_source_applied_when_omitted(self, app_objects, client):
        app, leads_module = app_objects
        session = _FakeSession()
        _override_db(app, leads_module, session)

        with patch.object(leads_module, "send_codex_email", return_value=(True, None)):
            r = client.post("/api/v1/leads", json={"email": "nosrc@acme.example"})

        assert r.status_code == 201
        assert session.added[0].source == "codex_download"


# ──────────────────────────────────────────────────────────────────────────
#  Idempotent re-submit within 24h
# ──────────────────────────────────────────────────────────────────────────


class TestIdempotentResubmit:
    def test_existing_lead_within_24h_short_circuits_insert(self, app_objects, client):
        """If a recent lead exists for the email, no new row is inserted and the
        SAME lead's signed URL is returned with the 'already requested' message."""
        app, leads_module = app_objects
        existing = leads_module.Lead(
            id=uuid.uuid4(),
            email="dup@acme.example",
            source="codex_download",
            status="new",
        )
        session = _FakeSession(ip_recent_count=0, existing_lead=existing)
        _override_db(app, leads_module, session)

        with patch.object(leads_module, "send_codex_email", return_value=(True, None)) as send:
            r = client.post("/api/v1/leads", json={"email": "dup@acme.example"})

        assert r.status_code == 201
        body = r.json()
        assert body["ok"] is True
        # No new lead persisted on the idempotent path.
        assert session.added == []
        # No second email sent on a duplicate request.
        send.assert_not_called()
        # URL returned points at the EXISTING lead (token verifies to its id).
        token = body["download_url"].split("t=", 1)[1]
        assert leads_module.verify_download_token(token) == existing.id
        # Message reflects the duplicate-within-24h branch.
        assert "già" in body["message"].lower() or "again" in body["message"].lower()


# ──────────────────────────────────────────────────────────────────────────
#  Per-IP DB rate limit -> 429
# ──────────────────────────────────────────────────────────────────────────


class TestRateLimit:
    def test_too_many_recent_leads_from_ip_returns_429(self, app_objects, client):
        """At/above RATE_LIMIT_MAX_PER_IP recent leads from an IP, the funnel
        rejects with 429 BEFORE persisting or emailing."""
        app, leads_module = app_objects
        at_limit = leads_module.RATE_LIMIT_MAX_PER_IP
        session = _FakeSession(ip_recent_count=at_limit, existing_lead=None)
        _override_db(app, leads_module, session)

        with patch.object(leads_module, "send_codex_email", return_value=(True, None)) as send:
            r = client.post("/api/v1/leads", json={"email": "spam@acme.example"})

        assert r.status_code == 429
        # Nothing persisted, nothing emailed when rate-limited.
        assert session.added == []
        send.assert_not_called()

    def test_just_below_limit_is_allowed(self, app_objects, client):
        """One below the threshold still succeeds (boundary is >=, not >)."""
        app, leads_module = app_objects
        below = leads_module.RATE_LIMIT_MAX_PER_IP - 1
        session = _FakeSession(ip_recent_count=below, existing_lead=None)
        _override_db(app, leads_module, session)

        with patch.object(leads_module, "send_codex_email", return_value=(True, None)):
            r = client.post("/api/v1/leads", json={"email": "ok@acme.example"})

        assert r.status_code == 201
        assert len(session.added) == 1


# ──────────────────────────────────────────────────────────────────────────
#  Resend email-send path
# ──────────────────────────────────────────────────────────────────────────


class TestEmailSendPath:
    def test_email_sent_with_absolute_url_and_message_reflects_success(self, app_objects, client):
        app, leads_module = app_objects
        session = _FakeSession()
        _override_db(app, leads_module, session)

        with patch.object(leads_module, "send_codex_email", return_value=(True, None)) as send:
            r = client.post(
                "/api/v1/leads",
                json={"email": "mailme@acme.example", "org_name": "Beta Industries"},
            )

        assert r.status_code == 201
        send.assert_called_once()
        kwargs = send.call_args.kwargs
        assert kwargs["to_email"] == "mailme@acme.example"
        # recipient_name is the first token of org_name.
        assert kwargs["recipient_name"] == "Beta"
        # The EMAIL gets the ABSOLUTE url (response carries the RELATIVE one).
        assert kwargs["download_url"].startswith("http")
        assert kwargs["download_url"].endswith(r.json()["download_url"])
        # Success message variant.
        assert "email" in r.json()["message"].lower()
        # last_email_sent_at written via a follow-up UPDATE.
        assert any("last_email_sent_at" in s for s in session.update_statements)

    def test_email_failure_records_error_and_degrades_message(self, app_objects, client):
        """A real send failure (non-'smtp_not_configured') must not break the
        201 response, must persist the error, and must change the message to the
        'download with the link' variant."""
        app, leads_module = app_objects
        session = _FakeSession()
        _override_db(app, leads_module, session)

        with patch.object(
            leads_module, "send_codex_email", return_value=(False, "ResendError: 422 invalid")
        ):
            r = client.post("/api/v1/leads", json={"email": "fail@acme.example"})

        assert r.status_code == 201
        body = r.json()
        assert body["download_url"].startswith("/api/v1/codex/download?t=")
        # Degraded message: NOT the "inviato via email" success copy.
        assert "email" not in body["message"].lower()
        # email_error persisted via UPDATE; last_email_sent_at NOT written.
        assert any("email_error" in s for s in session.update_statements)
        assert not any("last_email_sent_at" in s for s in session.update_statements)

    def test_smtp_not_configured_does_not_write_error_row(self, app_objects, client):
        """'smtp_not_configured' is benign (no Resend key in dev): no email_error
        UPDATE, no last_email_sent_at, but still 201 with a usable link."""
        app, leads_module = app_objects
        session = _FakeSession()
        _override_db(app, leads_module, session)

        with patch.object(
            leads_module, "send_codex_email", return_value=(False, "smtp_not_configured")
        ):
            r = client.post("/api/v1/leads", json={"email": "dev@acme.example"})

        assert r.status_code == 201
        assert r.json()["download_url"].startswith("/api/v1/codex/download?t=")
        # No tracking UPDATE for the benign not-configured case.
        assert not any("email_error" in s for s in session.update_statements)
        assert not any("last_email_sent_at" in s for s in session.update_statements)


# ──────────────────────────────────────────────────────────────────────────
#  Referer / source / tracking persisted on the Lead row
# ──────────────────────────────────────────────────────────────────────────


class TestTracking:
    def test_referer_and_user_agent_tracked_on_lead(self, app_objects, client):
        app, leads_module = app_objects
        session = _FakeSession()
        _override_db(app, leads_module, session)

        with patch.object(leads_module, "send_codex_email", return_value=(True, None)):
            r = client.post(
                "/api/v1/leads",
                json={"email": "track@acme.example", "source": "newsletter"},
                headers={
                    "referer": "https://normaai.org/codex",
                    "user-agent": "PyTest-UA/1.0",
                },
            )

        assert r.status_code == 201
        lead = session.added[0]
        assert lead.source == "newsletter"
        assert lead.referer == "https://normaai.org/codex"
        assert lead.user_agent == "PyTest-UA/1.0"

    def test_long_referer_is_truncated_to_500_chars(self, app_objects, client):
        """The handler slices referer/user-agent to 500 chars before storing."""
        app, leads_module = app_objects
        session = _FakeSession()
        _override_db(app, leads_module, session)

        long_ref = "https://x.example/" + ("a" * 1000)
        with patch.object(leads_module, "send_codex_email", return_value=(True, None)):
            r = client.post(
                "/api/v1/leads",
                json={"email": "longref@acme.example"},
                headers={"referer": long_ref},
            )

        assert r.status_code == 201
        assert len(session.added[0].referer) == 500
        assert session.added[0].referer == long_ref[:500]
