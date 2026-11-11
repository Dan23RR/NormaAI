# Security Policy

## Reporting a Vulnerability

Email **info@normaai.org** with subject `[SECURITY] NormaAI`.
Please include reproduction steps and impact assessment. Do not open a
public GitHub issue for security reports.

- Acknowledgement: within **48 hours**
- Triage & severity assessment: within **5 business days**
- Fix or mitigation for confirmed critical/high findings: within **30 days**

No bug bounty is offered at this stage; credit is given in release notes
unless you prefer otherwise.

## Supported Versions

Only the latest `main` branch and the most recent tagged release receive
security fixes.

## Security Architecture (summary)

Full details: [ARCHITECTURE.md](ARCHITECTURE.md), "Security Model" and ADR-2 (row-level security).

| Layer | Control |
|---|---|
| Transport | HTTPS on Vercel for the frontend; in production Caddy terminates TLS in front of the API (`docker-compose.prod.yml`, `infra/Caddyfile`) and the API sends HSTS (`src/api/middleware.py`) |
| AuthN | JWT RS256, 60-minute access token, 7-day refresh token with family tracking and reuse detection; Redis blacklist, fail-closed in production; bcrypt off the event loop |
| Registration | Invite-only by default (`REGISTRATION_MODE=invite`): single-use, expiring codes stored hashed; `open` / `closed` modes; email verification (`REQUIRE_EMAIL_VERIFICATION` gates the intelligence endpoints and the document check) |
| AuthZ | Roles `admin`, `member`, `viewer`, checked route by route (see "Known gaps"); staff allowlist (`STAFF_EMAILS`) for corpus crawl and cross-organisation invites; every tenant query filters on `org_id`, with PostgreSQL row-level security behind it when the app runs as a non-superuser role (`docker-compose.rls.yml`) |
| Brute force | Redis-backed lockout, 5 attempts / 5 min, keyed on email (bounded in-memory fallback during a Redis outage); per-IP rate limits on register (5/h), login (10/min), refresh (30/min) behind the trusted-proxy IP |
| Abuse / cost | Daily LLM quota per organisation (`LLM_DAILY_QUOTA_PER_ORG`, default 200), `X-Quota-Remaining` header; the document check has its own hourly limit (`DOCUMENT_CHECK_RATE_LIMIT`, 30/hour) and caps on size, references, concurrent and stored checks |
| Input | Typed validation and length caps; prompt-injection patterns are logged (`src/agents/sanitization.py`), not removed |
| Output | Every Q&A citation is checked word for word against the retrieved corpus text (numbers and short words must coincide; a tenant's upload never counts as official text); abstention in code when nothing is retrieved; CoVe only on request. Gap-analysis and monitor answers are not checked |
| Secrets | `.env` + `*.pem` gitignored; gitleaks in pre-commit and CI (full history) |
| Container | Multi-stage build, non-root user, read-only root filesystem, `cap_drop: ALL` |
| Supply chain | Dependabot, Trivy (fs + image, report-only in CI; blocking on fixable critical/high in `release.yml`), Bandit, CodeQL, CycloneDX SBOM |

## What the document check stores

`POST /api/v1/documents/check` reads the uploaded file in memory. The file and its text are
not written to disk, not stored and not logged; error logs carry the error type, never its
message, which could quote the document.

Stored in PostgreSQL, under row-level security on `org_id` (tables `document_checks` and
`document_dependencies`, migration 009):

- the file name, the SHA-256 of the file, the document date given by the user, the language,
  the check and re-check times;
- the findings: for each reference, at most 160 characters of the document around it, the
  quotes, the outcome and the official wording it was compared with;
- for each provision the document cites: act, article, version, the official text of the day
  of the check and its SHA-256, how the document cited it, and the changes found later.

Not stored: the document, its full text, any part of it beyond those excerpts and quotes.
The official texts downloaded from CELLAR and Normattiva are cached on disk
(`NORMAAI_TEXT_CACHE`); they are public texts, and the requests to those services carry an
act, an article and a date, nothing of the document. A check is deleted with
`DELETE /api/v1/documents/checks/{id}` (its provisions and alerts go with it), and by the
organisation's GDPR erasure (`POST /api/v1/gdpr/erase`, admin). Backups keep a deleted row for
up to 30 days ([docs/BACKUP_STRATEGY.md](docs/BACKUP_STRATEGY.md), section 4).

## Key Rotation

The cadence matches [docs/RUNBOOK.md](docs/RUNBOOK.md) section 10 (quarterly rotation and
access review); section 8 there is the procedure after an incident.

| Secret | Rotation | Procedure and effect |
|---|---|---|
| JWT RSA key pair (`data/jwt_private.pem`, `data/jwt_public.pem` on the server) | 90 days, or at once on suspicion | Generate a new pair, replace the files, restart the app. The API loads one pair, so every access and refresh token signed with the old key is refused at once and every user signs in again. To end one user's sessions without rotating, revoke through the Redis blacklist |
| `APP_SECRET_KEY` | On suspicion | Regenerate (`secrets.token_urlsafe(64)`; the API refuses to start in production with the default or a key under 32 characters), restart. Outstanding email-verification links and digest unsubscribe links stop working |
| LLM API keys (`GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `MISTRAL_API_KEY`) | 90 days | Provider console, then update `.env` or the secrets manager and restart |
| Resend API key | 90 days | resend.com/api-keys: revoke the old one, generate a new one, update `.env` |
| `PROMETHEUS_BEARER_TOKEN` | 180 days | Regenerate, update `.env` (also read by `infra/prometheus.yml`) |

After an incident: contain (rotate the compromised secret as above), assess whether personal
data are involved and whether the supervisory authority must be notified within 72 hours
(GDPR art. 33), document the timeline, add the lesson to the runbook (RUNBOOK section 8).

## Known gaps

These are known, not yet fixed, and stated here so that nobody relies on a control that does
not exist:

- **Tokens in browser storage.** The web app keeps the access and refresh tokens in
  `localStorage` (`frontend/src/lib/auth.ts`), not in HTTP-only cookies.
- **No password reset.** The auth API has no reset flow (`src/auth/router.py`).
- **No multi-factor authentication and no single sign-on.**
- **Audit events are log lines.** `src/audit.py` writes them through the logger
  `normaai.audit`; there is no audit table, and the lines are lost when the container is
  recreated (every deploy does it) and are in no backup.
- **The `viewer` role is enforced only on the documents API** (check, re-check, delete).
  Everywhere else a viewer has the rights of a member.
- **Row-level security needs the overlay.** Without `docker-compose.rls.yml` the app connects
  as the database superuser, which bypasses the policies: isolation then rests on the
  `org_id` filters of the queries alone.
- **Prompt-injection detection is telemetry.** It logs; it blocks nothing.
- **Backups not yet exercised.** As of 2026-11-11 no backup has reached a real off-site
  repository and no restore has been done (docs/BACKUP_STRATEGY.md).

Reports about anything else are welcome at the address at the top of this file.
