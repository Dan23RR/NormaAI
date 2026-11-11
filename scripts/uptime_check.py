#!/usr/bin/env python3
"""External uptime check for the public site and, when configured, the API.

Run every 30 minutes by .github/workflows/uptime.yml on a GitHub-hosted runner,
so it keeps watching when the production server is gone. Standard library only:
the runner's own python3 runs it and nothing is installed.

    python3 scripts/uptime_check.py site
    python3 scripts/uptime_check.py api            # needs API_BASE_URL
    python3 scripts/uptime_check.py site --issue   # also keeps the issue "Uptime: <host>"

Exit status: 0 when every check passes, 1 when at least one fails, 2 when the
configuration is unusable.

Environment
    SITE_URL          the public site, default https://normaai.org
    SITE_MARKER       text every checked page must contain, default "NormaAI"
    API_BASE_URL      the API, e.g. https://api.example.org (target "api")
    API_EXPECTED_IP   optional, comma-separated: the only addresses the API host
                      may resolve to
    MIN_CERT_DAYS     fail when a certificate expires sooner, default 14
    GITHUB_TOKEN, GITHUB_REPOSITORY   needed by --issue (set by GitHub Actions)

What it never does: print an IP address (the run log and the issue are public)
or copy text received from the checked hosts into the log or the issue. Only
status codes and words chosen in this file are reported.
"""

import argparse
import ipaddress
import json
import os
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

USER_AGENT = "normaai-uptime-check"
SITE_PATHS = (
    ("home", "/"),
    ("scope-csrd", "/scope-csrd.html"),
    ("scope-aiact", "/scope-aiact.html"),
)
LOGIN_PATH = "/api/v1/auth/login"
# GET /readyz (src/api/routers/system.py): {"status": "ready" | "not_ready",
# "checks": {"qdrant": "up" | "down", "llm": ..., "corpus": ...}}, 200 or 503.
# "corpus" is up only when the collection holds at least one point.
READYZ_CHECKS = ("qdrant", "llm", "corpus")
ISSUE_AUTHOR = "github-actions[bot]"
SIGNATURE = re.compile(r"<!-- uptime-failing: ([a-z0-9,-]*) -->")
MAX_BODY_BYTES = 2_000_000


class ConfigError(Exception):
    """A variable the check needs is missing or malformed."""


# ─── Results ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class Result:
    """Outcome of one check. ``detail`` is built from words chosen in this file."""

    check: str
    title: str
    ok: bool
    detail: str


def plain(text: object, limit: int = 160) -> str:
    """One line of harmless characters, safe in a log command or a Markdown table."""
    cleaned = re.sub(r"[^A-Za-z0-9 .,:;()/_=+'-]", " ", str(text))
    return re.sub(r" {2,}", " ", cleaned).strip()[:limit]


# ─── HTTP ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Response:
    status: int
    headers: Mapping[str, str]
    body: bytes


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


def _opener(follow_redirects: bool) -> urllib.request.OpenerDirector:
    # No proxy from the environment: the probe must reach the host itself.
    handlers: list[urllib.request.BaseHandler] = [urllib.request.ProxyHandler({})]
    if not follow_redirects:
        handlers.append(_NoRedirect())
    return urllib.request.build_opener(*handlers)


def fetch(
    url: str,
    *,
    method: str = "GET",
    headers: Mapping[str, str] | None = None,
    data: bytes | None = None,
    timeout: float = 20.0,
    follow_redirects: bool = True,
) -> Response:
    """One HTTP request. A 3xx (when not followed), 4xx or 5xx answer is returned, not raised."""
    request = urllib.request.Request(
        url, method=method, data=data, headers={"User-Agent": USER_AGENT, **(headers or {})}
    )
    try:
        with _opener(follow_redirects).open(request, timeout=timeout) as reply:
            return Response(reply.status, reply.headers, reply.read(MAX_BODY_BYTES))
    except urllib.error.HTTPError as error:
        body = error.read(MAX_BODY_BYTES) if error.fp is not None else b""
        error.close()
        return Response(error.code, error.headers, body)


def _reason(error: Exception) -> str:
    """The error's own words (OS, resolver or TLS library), made harmless."""
    reason = getattr(error, "verify_message", None) or getattr(error, "reason", None) or error
    return f"{type(error).__name__}: {plain(reason, 80)}"


def _problem(error: Exception) -> str:
    return f"no answer ({_reason(error)})"


# ─── Checks ──────────────────────────────────────────────────────


def check_page(check: str, url: str, marker: str) -> Result:
    title = f"GET {url}"
    try:
        reply = fetch(url)
    except (OSError, ValueError) as error:
        return Result(check, title, False, _problem(error))
    if reply.status != 200:
        return Result(check, title, False, f"HTTP {reply.status}")
    if marker not in reply.body.decode("utf-8", errors="replace"):
        return Result(check, title, False, "HTTP 200, but the expected text is not in the page")
    return Result(check, title, True, "HTTP 200, expected text found")


def cert_days_left(host: str, port: int = 443, timeout: float = 20.0) -> float:
    """Days until the certificate the host presents expires (it must be valid)."""
    context = ssl.create_default_context()
    with (
        socket.create_connection((host, port), timeout=timeout) as raw,
        context.wrap_socket(raw, server_hostname=host) as tls,
    ):
        certificate = tls.getpeercert()
    not_after = str((certificate or {})["notAfter"])
    return (ssl.cert_time_to_seconds(not_after) - time.time()) / 86400


def check_certificate(
    url: str, min_days: int, days_left: Callable[[str, int], float] = cert_days_left
) -> Result:
    parts = urlsplit(url)
    host = parts.hostname or ""
    title = f"TLS certificate of {host}"
    try:
        days = days_left(host, parts.port or 443)
    except (OSError, ValueError, KeyError) as error:
        return Result("tls", title, False, f"not valid or not reachable ({_reason(error)})")
    if days < min_days:
        return Result("tls", title, False, f"expires in {int(days)} days, fewer than {min_days}")
    return Result("tls", title, True, f"expires in {int(days)} days")


def check_readyz(base_url: str) -> Result:
    title = f"GET {base_url}/readyz"
    try:
        reply = fetch(f"{base_url}/readyz", follow_redirects=False)
    except (OSError, ValueError) as error:
        return Result("readyz", title, False, _problem(error))
    try:
        payload = json.loads(reply.body.decode("utf-8", errors="replace"))
    except ValueError:
        payload = None
    checks = payload.get("checks") if isinstance(payload, dict) else None
    if not isinstance(payload, dict) or not isinstance(checks, dict):
        return Result("readyz", title, False, f"HTTP {reply.status}, not the expected JSON")
    down = [name for name in READYZ_CHECKS if checks.get(name) != "up"]
    if reply.status == 200 and payload.get("status") == "ready" and not down:
        return Result("readyz", title, True, "ready, corpus not empty")
    not_up = ", ".join(down) if down else "none listed"
    return Result("readyz", title, False, f"HTTP {reply.status}, not ready; not up: {not_up}")


def check_cors(base_url: str, origin: str) -> Result:
    """The preflight a browser sends before POSTing the login form from the site."""
    title = f"CORS preflight of {LOGIN_PATH} from {origin}"
    try:
        reply = fetch(
            f"{base_url}{LOGIN_PATH}",
            method="OPTIONS",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
            follow_redirects=False,
        )
    except (OSError, ValueError) as error:
        return Result("cors", title, False, _problem(error))
    allowed = reply.headers.get("Access-Control-Allow-Origin", "") == origin
    if reply.status == 200 and allowed:
        return Result("cors", title, True, "the origin is allowed")
    header = "is the origin" if allowed else "missing or different"
    return Result(
        "cors",
        title,
        False,
        f"HTTP {reply.status}, Access-Control-Allow-Origin {header}: see CORS_ORIGINS on the server",
    )


def resolve(host: str) -> set[str]:
    """Every A and AAAA address of ``host``, in canonical form."""
    addresses: set[str] = set()
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            found = socket.getaddrinfo(host, None, family=family, type=socket.SOCK_STREAM)
        except socket.gaierror:
            continue
        addresses.update(str(ipaddress.ip_address(str(item[4][0]))) for item in found)
    return addresses


def check_dns(
    base_url: str, expected: str, resolver: Callable[[str], set[str]] = resolve
) -> Result:
    """The API host must resolve to the expected addresses and to nothing else.

    A stale record that points to an address somebody else holds would let them
    answer for the API. Addresses are compared, never printed.
    """
    host = urlsplit(base_url).hostname or ""
    title = f"DNS of {host}"
    try:
        wanted = {
            str(ipaddress.ip_address(item.strip())) for item in expected.split(",") if item.strip()
        }
    except ValueError:
        return Result("dns", title, False, "API_EXPECTED_IP is not a list of IP addresses")
    try:
        found = resolver(host)
    except (OSError, ValueError) as error:
        return Result("dns", title, False, _problem(error))
    if not found:
        return Result("dns", title, False, "the name does not resolve")
    if found != wanted:
        return Result(
            "dns",
            title,
            False,
            f"resolves to {len(found)} address(es), not to the {len(wanted)} expected",
        )
    return Result("dns", title, True, "resolves to the expected address only")


def with_retries(check: Callable[[], Result], attempts: int = 3, pause: float = 5.0) -> Result:
    """Run a check again before calling it failed: one lost packet is not an outage."""
    result = check()
    for _ in range(attempts - 1):
        if result.ok:
            break
        time.sleep(pause)
        result = check()
    return result


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def site_checks(site_url: str, marker: str, min_cert_days: int) -> list[Callable[[], Result]]:
    checks: list[Callable[[], Result]] = [
        (lambda c=check, p=path: check_page(c, f"{site_url}{p}", marker))
        for check, path in SITE_PATHS
    ]
    if site_url.startswith("https://"):
        checks.append(lambda: check_certificate(site_url, min_cert_days))
    return checks


def api_checks(
    api_url: str, site_url: str, expected_ip: str, min_cert_days: int
) -> list[Callable[[], Result]]:
    checks: list[Callable[[], Result]] = [
        lambda: check_readyz(api_url),
        lambda: check_cors(api_url, origin_of(site_url)),
    ]
    if api_url.startswith("https://"):
        checks.append(lambda: check_certificate(api_url, min_cert_days))
    if expected_ip.strip():
        checks.append(lambda: check_dns(api_url, expected_ip))
    return checks


# ─── The issue "Uptime: <host>" ──────────────────────────────────


class GitHub:
    """The few REST calls the issue needs, with the workflow's own token."""

    def __init__(
        self,
        token: str,
        repository: str,
        api_url: str = "https://api.github.com",
        send: Callable[..., Response] = fetch,
    ) -> None:
        self._token = token
        self._base = f"{api_url.rstrip('/')}/repos/{repository}"
        self._send = send

    def _call(self, method: str, path: str, payload: dict[str, object] | None = None) -> object:
        reply = self._send(
            f"{self._base}{path}",
            method=method,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
            # The token must not follow a redirect to another host.
            follow_redirects=False,
        )
        if reply.status >= 300:
            raise RuntimeError(f"GitHub API {method} {path}: HTTP {reply.status}")
        return json.loads(reply.body.decode("utf-8")) if reply.body else None

    def find_open_issue(self, title: str) -> dict[str, object] | None:
        """The open issue with this exact title that the workflow itself opened."""
        for page in range(1, 11):
            issues = self._call("GET", f"/issues?state=open&per_page=100&page={page}")
            if not isinstance(issues, list) or not issues:
                return None
            for issue in issues:
                author = (issue.get("user") or {}).get("login")
                if (
                    issue.get("title") == title
                    and "pull_request" not in issue
                    and author == ISSUE_AUTHOR
                ):
                    return dict(issue)
            if len(issues) < 100:
                return None
        return None

    def create_issue(self, title: str, body: str) -> None:
        self._call("POST", "/issues", {"title": title, "body": body})

    def update_issue(self, number: object, **fields: object) -> None:
        self._call("PATCH", f"/issues/{number}", dict(fields))

    def comment(self, number: object, body: str) -> None:
        self._call("POST", f"/issues/{number}/comments", {"body": body})


def signature(results: list[Result]) -> str:
    return ",".join(sorted(result.check for result in results if not result.ok))


def results_table(results: list[Result]) -> str:
    rows = ["| Check | Result |", "|---|---|"]
    rows += [
        f"| {plain(result.title)} | {'ok' if result.ok else 'FAILED'}: {plain(result.detail)} |"
        for result in results
    ]
    return "\n".join(rows)


def issue_body(host: str, results: list[Result], when: str, run_url: str, owner: str) -> str:
    lines = [
        f"The uptime check of **{plain(host)}** failed. Last run: {when}.",
        "",
        results_table(results),
        "",
        "What to do: docs/RUNBOOK.md, section 1.",
        "",
        "`.github/workflows/uptime.yml` rewrites this text at every failed run, adds a "
        "comment when the set of failing checks changes, and closes the issue at the "
        "first run that passes.",
    ]
    if run_url:
        lines += ["", f"Run: {run_url}"]
    if owner:
        lines += ["", f"cc @{plain(owner)}"]
    lines += ["", f"<!-- uptime-failing: {signature(results)} -->"]
    return "\n".join(lines)


def sync_issue(
    github: GitHub, host: str, results: list[Result], when: str, run_url: str, owner: str
) -> str:
    """Open, update or close the one issue of this target. Returns what was done."""
    title = f"Uptime: {host}"
    failing = signature(results)
    issue = github.find_open_issue(title)
    if failing:
        body = issue_body(host, results, when, run_url, owner)
        if issue is None:
            github.create_issue(title, body)
            return "opened"
        previous = SIGNATURE.search(str(issue.get("body") or ""))
        github.update_issue(issue["number"], body=body)
        if previous is None or previous.group(1) != failing:
            github.comment(
                issue["number"],
                f"The failing checks changed at {when}: now {failing.replace(',', ', ')}.",
            )
            return "updated, with a comment"
        return "updated"
    if issue is None:
        return "nothing to do"
    note = f"Recovered: every check passed at {when}."
    github.comment(issue["number"], f"{note} Run: {run_url}" if run_url else note)
    github.update_issue(issue["number"], state="closed", state_reason="completed")
    return "closed"


# ─── Command line ────────────────────────────────────────────────


def http_url(name: str, value: str) -> str:
    value = value.strip().rstrip("/")
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.path or parts.query:
        raise ConfigError(f"{name} must look like https://host, without a path")
    return value


def report(results: list[Result], host: str) -> None:
    for result in results:
        print(f"[{'PASS' if result.ok else 'FAIL'}] {result.title}: {result.detail}")
        if not result.ok and os.environ.get("GITHUB_ACTIONS") == "true":
            message = f"{plain(host)} - {plain(result.title)}: {plain(result.detail)}"
            print(f"::error title=Uptime::{message}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        failed = any(not result.ok for result in results)
        heading = f"Uptime of {plain(host)}: {'FAILED' if failed else 'ok'}"
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(f"### {heading}\n\n{results_table(results)}\n\n")


def build_checks(target: str, env: Mapping[str, str]) -> tuple[str, list[Callable[[], Result]]]:
    """The URL being watched and its checks, from the environment."""
    site_url = http_url("SITE_URL", env.get("SITE_URL") or "https://normaai.org")
    try:
        min_cert_days = int(env.get("MIN_CERT_DAYS") or 14)
    except ValueError:
        raise ConfigError("MIN_CERT_DAYS must be a whole number of days") from None
    if target == "site":
        return site_url, site_checks(site_url, env.get("SITE_MARKER") or "NormaAI", min_cert_days)
    if not (env.get("API_BASE_URL") or "").strip():
        raise ConfigError("API_BASE_URL is not set: nothing to check for the target api")
    api_url = http_url("API_BASE_URL", env["API_BASE_URL"])
    expected_ip = env.get("API_EXPECTED_IP") or ""
    return api_url, api_checks(api_url, site_url, expected_ip, min_cert_days)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("target", choices=("site", "api"))
    parser.add_argument(
        "--issue",
        action="store_true",
        help='open, update or close the issue "Uptime: <host>" (GITHUB_TOKEN, GITHUB_REPOSITORY)',
    )
    args = parser.parse_args(argv)
    env = os.environ

    try:
        watched, checks = build_checks(args.target, env)
    except ConfigError as error:
        print(f"::error title=Uptime::{plain(error)}")
        return 2

    results = [with_retries(check) for check in checks]
    host = urlsplit(watched).hostname or watched
    report(results, host)

    if args.issue:
        when = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        run_url = ""
        if env.get("GITHUB_RUN_ID") and env.get("GITHUB_REPOSITORY"):
            server = env.get("GITHUB_SERVER_URL") or "https://github.com"
            run_url = f"{server}/{env['GITHUB_REPOSITORY']}/actions/runs/{env['GITHUB_RUN_ID']}"
        try:
            github = GitHub(
                env["GITHUB_TOKEN"],
                env["GITHUB_REPOSITORY"],
                env.get("GITHUB_API_URL") or "https://api.github.com",
            )
            owner = env.get("GITHUB_REPOSITORY_OWNER") or ""
            print(f"issue: {sync_issue(github, host, results, when, run_url, owner)}")
        except (KeyError, OSError, RuntimeError, ValueError) as error:
            # The exit status says how the watched host is, not how the issue went.
            print(f"::warning title=Uptime issue::not updated ({plain(error)})")
    return 1 if any(not result.ok for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
