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
| AuthN | JWT RS256; 15-minute access token (`ACCESS_TOKEN_TTL`); refresh token rotated at every use (`REFRESH_TOKEN_TTL`, 7 days) with family tracking and reuse detection; no session is refreshed past 30 days from its sign-in (`SESSION_MAX_LIFETIME_DAYS`); logout revokes the session on the server (the access token, its refresh family and the refresh token); on every request the account is read from the database (it must exist, be active, belong to the token's organisation and not have ended its sessions; role and staff come from there, at most `AUTH_ACCOUNT_CACHE_SECONDS`, 30, late); Redis blacklist, fail-closed in production; bcrypt off the event loop |
| Registration | Invite-only by default (`REGISTRATION_MODE=invite`): single-use, expiring codes stored hashed; `open` / `closed` modes; email verification (`REQUIRE_EMAIL_VERIFICATION` gates the intelligence endpoints, the PDF reports and the document check). An invite verifies the invitee's address only when NormaAI minted it (`scripts/create_invite.py` or staff); an organisation admin's invitee confirms it with the link |
| Password reset | `POST /api/v1/auth/password-reset` mails a single-use link valid `PASSWORD_RESET_TOKEN_TTL_MINUTES` (30); only the SHA-256 of its secret is stored; the answer is the same whether or not the address has an account, and no second link goes out within 5 minutes; using it (`/password-reset/confirm`) ends every session of the account and confirms its email. Staff can mint the same link from the command line (`scripts/staff.py reset-password`) |
| AuthZ | Roles `admin`, `member`, `viewer`: a `viewer` only reads (clients, alerts and documents refuse its writes); an `admin` manages members (`/api/v1/auth/members`: the last active admin can be neither demoted nor removed) and invites, deletes clients and runs the GDPR export and erasure. Staff (corpus crawl, cross-organisation invites) is the `users.is_staff` flag, set only with `scripts/staff.py` and honoured only on a verified email: no setting, registration or token claim makes anyone staff. Every tenant query filters on `org_id`, with PostgreSQL row-level security behind it when the app runs as a non-superuser role (`docker-compose.rls.yml`) |
| Brute force | Redis-backed lockout, 5 attempts / 5 min, keyed on email (bounded in-memory fallback during a Redis outage); per-IP rate limits on register (5/h), login (10/min), refresh (30/min), password reset (5/h) behind the trusted-proxy IP; every other route without a limit of its own has `RATE_LIMIT_DEFAULT` (100/min). The counters live in Redis, shared by all API processes (`RATE_LIMIT_STORAGE_URI`, else `REDIS_URL`); while Redis does not answer they are counted in each process's memory, with a warning |
| Abuse / cost | Daily LLM quota per organisation (`LLM_DAILY_QUOTA_PER_ORG`, default 200), `X-Quota-Remaining` header, on the intelligence endpoints and on the PDF reports (one unit per framework analysed); the document check has its own hourly limit (`DOCUMENT_CHECK_RATE_LIMIT`, 30/hour) and caps on size, references, concurrent and stored checks |
| Surface | With `APP_ENV=production` the API serves no `/docs`, `/redoc` or `/openapi.json` |
| Input | Typed validation and length caps; prompt-injection patterns are logged (`src/agents/sanitization.py`), not removed |
| Output | Every Q&A citation is checked word for word against the retrieved corpus text (numbers and short words must coincide; a tenant's upload never counts as official text); abstention in code when nothing is retrieved; CoVe only on request. Gap-analysis and monitor answers are not checked. The PDF reports are marked as AI-generated (AI Act art. 50(2)): document information and XMP metadata (`AIGenerated: true`, the generating system and model) and a line on every page |
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
The legacy route `POST /api/v1/documents/upload`, which put a document's text in the
organisation's search index, is closed (410 Gone); text it indexed before it closed is
deleted by the GDPR erasure.
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
| JWT RSA key pair (`data/jwt_private.pem`, `data/jwt_public.pem` on the server) | 90 days, or at once on suspicion | Generate a new pair, replace the files, restart the app. The API loads one pair, so every access and refresh token signed with the old key is refused at once and every user signs in again. To end one user's sessions without rotating: `python scripts/staff.py end-sessions <email>` |
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
  `localStorage` (`frontend/src/lib/auth.ts`), not in HTTP-only cookies, so a script
  injected into the site could read them. What limits the damage today: access tokens
  last 15 minutes, logout revokes the session on the server, no session outlives 30 days,
  and every request is checked against the account. Moving to cookies means: the API sets
  `HttpOnly`, `Secure`, `SameSite` cookies (the refresh one limited to the refresh path),
  a CSRF token checked on every state-changing request and an `Origin` check, credentialed
  CORS for the site only, and a web app that sends credentials on every call (uploads and
  streaming included) and no longer reads the tokens; not done yet.
- **No multi-factor authentication and no single sign-on.**
- **Audit events are log lines.** `src/audit.py` writes them through the logger
  `normaai.audit`; there is no audit table, and the lines are lost when the container is
  recreated (every deploy does it) and are in no backup.
- **Conversations are personal.** A `viewer` can still start and delete its own Chiedi
  conversations: nobody else sees them.
- **Row-level security needs the overlay.** Without `docker-compose.rls.yml` the app connects
  as the database superuser, which bypasses the policies: isolation then rests on the
  `org_id` filters of the queries alone.
- **Prompt-injection detection is telemetry.** It logs; it blocks nothing.
- **Backups not yet exercised.** As of 2026-11-11 no backup has reached a real off-site
  repository and no restore has been done (docs/BACKUP_STRATEGY.md).

Reports about anything else are welcome at the address at the top of this file.
