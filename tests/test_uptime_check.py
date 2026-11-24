"""scripts/uptime_check.py: the checks behind .github/workflows/uptime.yml.

Every HTTP check runs against a server started on 127.0.0.1 for the test, so
the real request (method, path, headers) and the real parsing are exercised
without leaving the machine. The certificate and DNS checks take their lookup
as an argument; GitHub's REST API is played by the same local server.
"""

import importlib.util
import json
import socket
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "uptime_check.py"
_spec = importlib.util.spec_from_file_location("uptime_check", SCRIPT)
uptime = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(uptime)

READY = {"status": "ready", "checks": {"qdrant": "up", "llm": "up", "corpus": "up"}}
ORIGIN = "https://normaai.org"
# Documentation addresses (RFC 5737, RFC 3849): they belong to nobody.
EXPECTED_V4 = "192.0.2.10"
OTHER_V4 = "198.51.100.7"


class _Handler(BaseHTTPRequestHandler):
    def _serve(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self.server.seen.append(
            {
                "method": self.command,
                "path": self.path,
                "headers": {name.lower(): value for name, value in self.headers.items()},
                "json": json.loads(body) if body else None,
            }
        )
        status, headers, payload = self.server.routes.get(
            (self.command, self.path), (404, {}, b"not found")
        )
        if not isinstance(payload, bytes):
            payload = json.dumps(payload).encode()
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


# http.server looks the handler up by the name do_<METHOD>.
for _method in ("GET", "POST", "PATCH", "OPTIONS"):
    setattr(_Handler, f"do_{_method}", _Handler._serve)


@pytest.fixture
def server():
    """A local HTTP server: ``routes[(method, path)] = (status, headers, body)``."""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    httpd.routes = {}
    httpd.seen = []
    httpd.url = f"http://127.0.0.1:{httpd.server_address[1]}"
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


@pytest.fixture(autouse=True)
def _no_waiting(monkeypatch):
    monkeypatch.setattr(uptime.time, "sleep", lambda seconds: None)


# ─── Pages ───────────────────────────────────────────────────────


def test_page_with_the_expected_text_passes(server):
    server.routes[("GET", "/")] = (200, {}, b"<title>NormaAI: risposte</title>")
    result = uptime.check_page("home", f"{server.url}/", "NormaAI")
    assert result.ok
    assert server.seen[0]["headers"]["user-agent"] == "normaai-uptime-check"


def test_page_without_the_expected_text_fails(server):
    # A parked domain or an error page that still answers 200.
    server.routes[("GET", "/")] = (200, {}, b"<title>Domain for sale</title>")
    result = uptime.check_page("home", f"{server.url}/", "NormaAI")
    assert not result.ok
    assert "expected text is not in the page" in result.detail
    assert "Domain for sale" not in result.detail


def test_page_error_status_fails(server):
    result = uptime.check_page("scope-csrd", f"{server.url}/scope-csrd.html", "NormaAI")
    assert not result.ok
    assert result.detail == "HTTP 404"


def test_page_on_a_host_that_does_not_answer_fails(server):
    url = server.url
    server.shutdown()
    server.server_close()
    result = uptime.check_page("home", f"{url}/", "NormaAI")
    assert not result.ok
    assert result.detail.startswith("no answer")


def test_site_checks_cover_the_three_pages(server):
    for path in ("/", "/scope-csrd.html", "/scope-aiact.html"):
        server.routes[("GET", path)] = (200, {}, b"NormaAI")
    # http: no certificate to check. https adds the certificate check.
    results = [check() for check in uptime.site_checks(server.url, "NormaAI", 14)]
    assert [(r.check, r.ok) for r in results] == [
        ("home", True),
        ("scope-csrd", True),
        ("scope-aiact", True),
    ]
    assert len(uptime.site_checks("https://normaai.org", "NormaAI", 14)) == 4


# ─── /readyz ─────────────────────────────────────────────────────


def test_readyz_ready_passes(server):
    server.routes[("GET", "/readyz")] = (200, {"Content-Type": "application/json"}, READY)
    result = uptime.check_readyz(server.url)
    assert result.ok
    assert result.detail == "ready, corpus not empty"


def test_readyz_with_an_empty_corpus_fails(server):
    body = {"status": "not_ready", "checks": {"qdrant": "up", "llm": "up", "corpus": "down"}}
    server.routes[("GET", "/readyz")] = (503, {}, body)
    result = uptime.check_readyz(server.url)
    assert not result.ok
    assert result.detail == "HTTP 503, not ready; not up: corpus"


def test_readyz_names_every_dependency_that_is_down(server):
    body = {"status": "not_ready", "checks": {"qdrant": "down", "llm": "down", "corpus": "up"}}
    server.routes[("GET", "/readyz")] = (503, {}, body)
    assert uptime.check_readyz(server.url).detail.endswith("not up: qdrant, llm")


def test_readyz_ready_without_the_corpus_check_fails(server):
    # "ready" is not enough: the corpus check itself must say "up".
    server.routes[("GET", "/readyz")] = (
        200,
        {},
        {"status": "ready", "checks": {"qdrant": "up", "llm": "up"}},
    )
    result = uptime.check_readyz(server.url)
    assert not result.ok
    assert "corpus" in result.detail


@pytest.mark.parametrize("body", [b"<html>It works!</html>", b"[]", b'{"status": "ready"}'])
def test_readyz_from_another_server_fails(server, body):
    server.routes[("GET", "/readyz")] = (200, {}, body)
    result = uptime.check_readyz(server.url)
    assert not result.ok
    assert result.detail == "HTTP 200, not the expected JSON"


def test_readyz_does_not_copy_text_from_the_host(server):
    body = {"status": "<script>x</script>", "checks": {"corpus": "@everyone", "llm": "up"}}
    server.routes[("GET", "/readyz")] = (503, {}, body)
    detail = uptime.check_readyz(server.url).detail
    assert "script" not in detail
    assert "@" not in detail


def test_readyz_redirect_is_not_followed(server):
    server.routes[("GET", "/readyz")] = (302, {"Location": f"{server.url}/elsewhere"}, b"")
    server.routes[("GET", "/elsewhere")] = (200, {}, READY)
    result = uptime.check_readyz(server.url)
    assert not result.ok
    assert result.detail.startswith("HTTP 302")
    assert [request["path"] for request in server.seen] == ["/readyz"]


# ─── CORS preflight of the login route ───────────────────────────


def test_cors_preflight_allowed_passes(server):
    server.routes[("OPTIONS", "/api/v1/auth/login")] = (
        200,
        {"Access-Control-Allow-Origin": ORIGIN, "Access-Control-Allow-Credentials": "true"},
        b"OK",
    )
    result = uptime.check_cors(server.url, ORIGIN)
    assert result.ok
    sent = server.seen[0]
    assert (sent["method"], sent["path"]) == ("OPTIONS", "/api/v1/auth/login")
    assert sent["headers"]["origin"] == ORIGIN
    assert sent["headers"]["access-control-request-method"] == "POST"
    assert sent["headers"]["access-control-request-headers"] == "content-type"


def test_cors_preflight_refused_fails(server):
    # What Starlette answers when the origin is not in CORS_ORIGINS.
    server.routes[("OPTIONS", "/api/v1/auth/login")] = (400, {}, b"Disallowed CORS origin")
    result = uptime.check_cors(server.url, ORIGIN)
    assert not result.ok
    assert "HTTP 400" in result.detail
    assert "CORS_ORIGINS" in result.detail


def test_cors_preflight_allowing_another_origin_fails(server):
    server.routes[("OPTIONS", "/api/v1/auth/login")] = (
        200,
        {"Access-Control-Allow-Origin": "http://localhost:3000"},
        b"OK",
    )
    result = uptime.check_cors(server.url, ORIGIN)
    assert not result.ok
    assert "localhost" not in result.detail


def test_origin_is_the_site_without_its_path():
    assert uptime.origin_of("https://normaai.org") == ORIGIN
    assert uptime.origin_of("https://normaai.org/login") == ORIGIN


# ─── Certificate ─────────────────────────────────────────────────


def test_certificate_with_enough_days_passes():
    result = uptime.check_certificate(ORIGIN, 14, days_left=lambda host, port: 65.4)
    assert result.ok
    assert result.detail == "expires in 65 days"


def test_certificate_under_the_limit_fails():
    seen = []

    def days_left(host, port):
        seen.append((host, port))
        return 13.9

    result = uptime.check_certificate("https://api.normaai.org", 14, days_left=days_left)
    assert not result.ok
    assert result.detail == "expires in 13 days, fewer than 14"
    assert seen == [("api.normaai.org", 443)]


def test_certificate_that_does_not_verify_fails():
    def days_left(host, port):
        error = ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] ...")
        error.verify_message = "certificate has expired"  # set by the TLS library
        raise error

    result = uptime.check_certificate(ORIGIN, 14, days_left=days_left)
    assert not result.ok
    assert result.detail == (
        "not valid or not reachable (SSLCertVerificationError: certificate has expired)"
    )


# ─── DNS ─────────────────────────────────────────────────────────


def test_dns_matching_the_expected_address_passes():
    result = uptime.check_dns("https://api.normaai.org", EXPECTED_V4, lambda host: {EXPECTED_V4})
    assert result.ok


def test_dns_with_a_stale_extra_record_fails_without_printing_addresses():
    result = uptime.check_dns(
        "https://api.normaai.org", EXPECTED_V4, lambda host: {EXPECTED_V4, OTHER_V4}
    )
    assert not result.ok
    assert result.detail == "resolves to 2 address(es), not to the 1 expected"
    assert EXPECTED_V4 not in result.title + result.detail
    assert OTHER_V4 not in result.title + result.detail


def test_dns_pointing_elsewhere_fails():
    result = uptime.check_dns("https://api.normaai.org", EXPECTED_V4, lambda host: {OTHER_V4})
    assert not result.ok
    assert OTHER_V4 not in result.detail


def test_dns_that_does_not_resolve_fails():
    result = uptime.check_dns("https://api.normaai.org", EXPECTED_V4, lambda host: set())
    assert not result.ok
    assert result.detail == "the name does not resolve"


def test_dns_accepts_a_list_and_compares_ipv6_in_canonical_form():
    result = uptime.check_dns(
        "https://api.normaai.org",
        f"{EXPECTED_V4}, 2001:DB8:0:0:0:0:0:1",
        lambda host: {EXPECTED_V4, "2001:db8::1"},
    )
    assert result.ok


def test_dns_with_a_malformed_expectation_fails():
    result = uptime.check_dns("https://api.normaai.org", "not-an-address", lambda host: set())
    assert not result.ok
    assert "API_EXPECTED_IP" in result.detail


def test_resolve_collects_a_and_aaaa_records_in_canonical_form(monkeypatch):
    asked = []

    def getaddrinfo(host, port, family=0, type=0):
        asked.append((host, family))
        if family == socket.AF_INET:
            return [(family, type, 6, "", (EXPECTED_V4, 0))] * 2  # one address, listed twice
        return [(family, type, 6, "", ("2001:DB8:0:0:0:0:0:1", 0, 0, 0))]

    monkeypatch.setattr(uptime.socket, "getaddrinfo", getaddrinfo)
    assert uptime.resolve("api.normaai.org") == {EXPECTED_V4, "2001:db8::1"}
    assert asked == [("api.normaai.org", socket.AF_INET), ("api.normaai.org", socket.AF_INET6)]


def test_resolve_of_a_name_with_an_a_record_only(monkeypatch):
    def getaddrinfo(host, port, family=0, type=0):
        if family == socket.AF_INET6:
            raise socket.gaierror(socket.EAI_NONAME, "no AAAA record")
        return [(family, type, 6, "", (EXPECTED_V4, 0))]

    monkeypatch.setattr(uptime.socket, "getaddrinfo", getaddrinfo)
    assert uptime.resolve("api.normaai.org") == {EXPECTED_V4}


def test_resolve_of_a_name_without_records_is_empty(monkeypatch):
    def getaddrinfo(host, port, family=0, type=0):
        raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")

    monkeypatch.setattr(uptime.socket, "getaddrinfo", getaddrinfo)
    assert uptime.resolve("gone.normaai.org") == set()


def test_api_checks_add_dns_only_when_an_address_is_expected(server):
    assert len(uptime.api_checks(server.url, ORIGIN, "", 14)) == 2
    assert len(uptime.api_checks(server.url, ORIGIN, EXPECTED_V4, 14)) == 3
    # https adds the certificate of the API host.
    assert len(uptime.api_checks("https://api.normaai.org", ORIGIN, EXPECTED_V4, 14)) == 4


# ─── Retries and text ────────────────────────────────────────────


def test_a_check_is_tried_again_before_it_fails():
    outcomes = [False, False, True]
    calls = []

    def check():
        calls.append(1)
        return uptime.Result("home", "GET /", outcomes[len(calls) - 1], "x")

    assert uptime.with_retries(check).ok
    assert len(calls) == 3


def test_a_check_that_keeps_failing_fails_after_three_attempts():
    calls = []

    def check():
        calls.append(1)
        return uptime.Result("home", "GET /", False, "HTTP 500")

    assert not uptime.with_retries(check).ok
    assert len(calls) == 3


def test_plain_keeps_nothing_that_markdown_or_the_runner_would_interpret():
    text = uptime.plain("ok\n::set-output name=x::y | [link](http://evil) @someone `code` 100%")
    assert text == "ok ::set-output name=x::y link (http://evil) someone code 100"
    for character in "\n|[]@`%<>*#":
        assert character not in text
    assert len(uptime.plain("x" * 500)) == 160


# ─── The issue ───────────────────────────────────────────────────


def _results(*failing):
    return [
        uptime.Result(check, f"check {check}", check not in failing, "detail")
        for check in ("readyz", "cors", "tls")
    ]


def _issue(number, title, body="", login="github-actions[bot]", **extra):
    return {"number": number, "title": title, "body": body, "user": {"login": login}, **extra}


class FakeGitHub:
    def __init__(self, issue=None):
        self.issue = issue
        self.calls = []

    def find_open_issue(self, title):
        self.calls.append(("find", title))
        return self.issue

    def create_issue(self, title, body):
        self.calls.append(("create", title, body))

    def update_issue(self, number, **fields):
        self.calls.append(("update", number, fields))

    def comment(self, number, body):
        self.calls.append(("comment", number, body))


def _sync(github, results):
    return uptime.sync_issue(
        github, "api.normaai.org", results, "2026-11-11 10:07 UTC", "https://run", "owner-login"
    )


def test_first_failure_opens_the_issue():
    github = FakeGitHub()
    assert _sync(github, _results("readyz")) == "opened"
    (_, title), (_, created_title, body) = github.calls
    assert title == created_title == "Uptime: api.normaai.org"
    assert "| check readyz | FAILED: detail |" in body
    assert "| check cors | ok: detail |" in body
    assert "cc @owner-login" in body
    assert "https://run" in body
    assert body.endswith("<!-- uptime-failing: readyz -->")


def test_same_failure_again_rewrites_the_issue_without_a_comment():
    open_issue = _issue(7, "Uptime: api.normaai.org", "old\n<!-- uptime-failing: readyz -->")
    github = FakeGitHub(open_issue)
    assert _sync(github, _results("readyz")) == "updated"
    assert [call[0] for call in github.calls] == ["find", "update"]
    assert github.calls[1][1] == 7
    assert "2026-11-11 10:07 UTC" in github.calls[1][2]["body"]


def test_a_different_failure_adds_one_comment():
    open_issue = _issue(7, "Uptime: api.normaai.org", "old\n<!-- uptime-failing: readyz -->")
    github = FakeGitHub(open_issue)
    assert _sync(github, _results("readyz", "cors")) == "updated, with a comment"
    assert [call[0] for call in github.calls] == ["find", "update", "comment"]
    assert "now cors, readyz" in github.calls[2][2]


def test_recovery_comments_and_closes_the_issue():
    github = FakeGitHub(_issue(7, "Uptime: api.normaai.org"))
    assert _sync(github, _results()) == "closed"
    assert github.calls[1][:2] == ("comment", 7)
    assert "Recovered" in github.calls[1][2]
    assert github.calls[2] == ("update", 7, {"state": "closed", "state_reason": "completed"})


def test_all_well_and_no_issue_does_nothing():
    github = FakeGitHub()
    assert _sync(github, _results()) == "nothing to do"
    assert github.calls == [("find", "Uptime: api.normaai.org")]


def _github(server):
    return uptime.GitHub("token-123", "owner/repo", api_url=server.url)


def test_find_open_issue_takes_only_the_workflow_s_own_issue(server):
    server.routes[("GET", "/repos/owner/repo/issues?state=open&per_page=100&page=1")] = (
        200,
        {},
        [
            _issue(1, "Uptime: normaai.org", pull_request={}),
            _issue(2, "Uptime: normaai.org", login="somebody-else"),
            _issue(3, "Uptime: api.normaai.org"),
            _issue(4, "Uptime: normaai.org"),
        ],
    )
    found = _github(server).find_open_issue("Uptime: normaai.org")
    assert found["number"] == 4
    headers = server.seen[0]["headers"]
    assert headers["authorization"] == "Bearer token-123"
    assert headers["accept"] == "application/vnd.github+json"


def test_find_open_issue_reads_the_next_page(server):
    base = "/repos/owner/repo/issues?state=open&per_page=100&page="
    server.routes[("GET", f"{base}1")] = (200, {}, [_issue(n, "other") for n in range(100)])
    server.routes[("GET", f"{base}2")] = (200, {}, [_issue(321, "Uptime: normaai.org")])
    assert _github(server).find_open_issue("Uptime: normaai.org")["number"] == 321


def test_find_open_issue_without_a_match(server):
    server.routes[("GET", "/repos/owner/repo/issues?state=open&per_page=100&page=1")] = (
        200,
        {},
        [],
    )
    assert _github(server).find_open_issue("Uptime: normaai.org") is None


def test_github_writes_send_json_to_the_right_endpoints(server):
    server.routes[("POST", "/repos/owner/repo/issues")] = (201, {}, {"number": 9})
    server.routes[("PATCH", "/repos/owner/repo/issues/9")] = (200, {}, {"number": 9})
    server.routes[("POST", "/repos/owner/repo/issues/9/comments")] = (201, {}, {"id": 1})
    github = _github(server)
    github.create_issue("Uptime: normaai.org", "body")
    github.update_issue(9, state="closed", state_reason="completed")
    github.comment(9, "Recovered")
    assert [request["json"] for request in server.seen] == [
        {"title": "Uptime: normaai.org", "body": "body"},
        {"state": "closed", "state_reason": "completed"},
        {"body": "Recovered"},
    ]


def test_github_error_status_raises(server):
    with pytest.raises(RuntimeError, match="HTTP 404"):
        _github(server).create_issue("Uptime: normaai.org", "body")


def test_the_token_does_not_follow_a_redirect(server):
    path = "/repos/owner/repo/issues?state=open&per_page=100&page=1"
    server.routes[("GET", path)] = (302, {"Location": f"{server.url}/elsewhere"}, b"")
    server.routes[("GET", "/elsewhere")] = (200, {}, [])
    with pytest.raises(RuntimeError, match="HTTP 302"):
        _github(server).find_open_issue("Uptime: normaai.org")
    assert [request["path"] for request in server.seen] == [path]


# ─── Command line ────────────────────────────────────────────────


@pytest.fixture
def env(monkeypatch, server):
    for name in (
        "SITE_URL",
        "SITE_MARKER",
        "API_BASE_URL",
        "API_EXPECTED_IP",
        "MIN_CERT_DAYS",
        "GITHUB_ACTIONS",
        "GITHUB_STEP_SUMMARY",
        "GITHUB_TOKEN",
        "GITHUB_REPOSITORY",
        "GITHUB_REPOSITORY_OWNER",
        "GITHUB_RUN_ID",
        "GITHUB_API_URL",
        "GITHUB_SERVER_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SITE_URL", server.url)
    return monkeypatch


def _site_up(server):
    for path in ("/", "/scope-csrd.html", "/scope-aiact.html"):
        server.routes[("GET", path)] = (200, {}, b"NormaAI")


def test_main_site_all_well(env, server, capsys):
    _site_up(server)
    assert uptime.main(["site"]) == 0
    out = capsys.readouterr().out
    assert out.count("[PASS]") == 3
    assert "FAIL" not in out


def test_main_site_with_a_missing_page_fails(env, server, capsys, tmp_path):
    _site_up(server)
    del server.routes[("GET", "/scope-aiact.html")]
    summary = tmp_path / "summary.md"
    env.setenv("GITHUB_ACTIONS", "true")
    env.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert uptime.main(["site"]) == 1
    out = capsys.readouterr().out
    assert f"[FAIL] GET {server.url}/scope-aiact.html: HTTP 404" in out
    assert "::error title=Uptime::127.0.0.1 - GET" in out
    # Three attempts for the failing page, one for each of the others.
    assert [r["path"] for r in server.seen].count("/scope-aiact.html") == 3
    assert "### Uptime of 127.0.0.1: FAILED" in summary.read_text(encoding="utf-8")


def test_main_site_marker_from_the_environment(env, server):
    _site_up(server)
    env.setenv("SITE_MARKER", "Another name")
    assert uptime.main(["site"]) == 1


def test_main_api_all_well(env, server, capsys):
    env.setenv("SITE_URL", ORIGIN)
    env.setenv("API_BASE_URL", f"{server.url}/")
    server.routes[("GET", "/readyz")] = (200, {}, READY)
    server.routes[("OPTIONS", "/api/v1/auth/login")] = (
        200,
        {"Access-Control-Allow-Origin": ORIGIN},
        b"OK",
    )
    assert uptime.main(["api"]) == 0
    assert capsys.readouterr().out.count("[PASS]") == 2
    assert server.seen[1]["headers"]["origin"] == ORIGIN


def test_main_api_without_its_variable_is_a_configuration_error(env, capsys):
    assert uptime.main(["api"]) == 2
    assert "API_BASE_URL is not set" in capsys.readouterr().out


@pytest.mark.parametrize("value", ["normaai.org", "ftp://normaai.org", "https://normaai.org/x"])
def test_main_rejects_a_malformed_url(env, value, capsys):
    env.setenv("SITE_URL", value)
    assert uptime.main(["site"]) == 2
    assert "SITE_URL must look like" in capsys.readouterr().out


def test_main_opens_the_issue_through_the_api(env, server, capsys):
    _site_up(server)
    server.routes[("GET", "/")] = (500, {}, b"boom")
    listing = "/repos/owner/repo/issues?state=open&per_page=100&page=1"
    server.routes[("GET", listing)] = (200, {}, [])
    server.routes[("POST", "/repos/owner/repo/issues")] = (201, {}, {"number": 1})
    env.setenv("GITHUB_TOKEN", "token-123")
    env.setenv("GITHUB_REPOSITORY", "owner/repo")
    env.setenv("GITHUB_REPOSITORY_OWNER", "owner")
    env.setenv("GITHUB_RUN_ID", "42")
    env.setenv("GITHUB_API_URL", server.url)
    assert uptime.main(["site", "--issue"]) == 1
    assert "issue: opened" in capsys.readouterr().out
    created = server.seen[-1]["json"]
    assert created["title"] == "Uptime: 127.0.0.1"
    assert "https://github.com/owner/repo/actions/runs/42" in created["body"]
    assert "cc @owner" in created["body"]
    assert "<!-- uptime-failing: home -->" in created["body"]


def test_main_keeps_the_site_s_verdict_when_the_issue_cannot_be_updated(env, server, capsys):
    _site_up(server)
    env.setenv("GITHUB_TOKEN", "token-123")
    env.setenv("GITHUB_REPOSITORY", "owner/repo")
    env.setenv("GITHUB_API_URL", server.url)  # answers 404 to the issue listing
    assert uptime.main(["site", "--issue"]) == 0
    assert "::warning title=Uptime issue::not updated" in capsys.readouterr().out


def test_main_without_a_token_still_reports_the_checks(env, server, capsys):
    _site_up(server)
    assert uptime.main(["site", "--issue"]) == 0
    assert "::warning title=Uptime issue::not updated" in capsys.readouterr().out
