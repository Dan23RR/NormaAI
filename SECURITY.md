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

Full details: [ARCHITECTURE.md](ARCHITECTURE.md) § Security Model.

| Layer | Control |
|---|---|
| Transport | HTTPS/HSTS (Vercel frontend; TLS termination required in front of the API in production) |
| AuthN | JWT RS256, 15-min access / 7-day refresh with family tracking; Redis blacklist **fail-closed in production** |
| AuthZ | RBAC (admin/member/viewer) + PostgreSQL Row-Level Security per organization |
| Brute force | Redis-backed lockout, 5 attempts / 5 min, keyed on email (fail-open by design during Redis outage — documented trade-off) |
| Input | Prompt-injection sanitization + typed profile validation + length caps |
| Output | CoVe 5-phase verification; citations validated against EUR-Lex/Normattiva |
| Secrets | `.env` + `*.pem` gitignored; gitleaks in pre-commit and CI (full history) |
| Container | Multi-stage build, non-root user, read-only rootfs, `cap_drop: ALL` |
| Supply chain | Dependabot, Trivy (fs + image), Bandit, CodeQL, CycloneDX SBOM per release |

## Key Rotation

| Secret | Rotation | Procedure |
|---|---|---|
| JWT RSA keypair | 90 days or on suspicion | Generate new pair, deploy, old access tokens expire in 15 min |
| `APP_SECRET_KEY` | On suspicion | Regenerate (`secrets.token_urlsafe(64)`), restart |
| LLM API keys | 90 days | Provider console → update `.env`/secrets manager |
| Resend API key | 90 days | resend.com/api-keys → revoke old, generate new |
| `PROMETHEUS_BEARER_TOKEN` | 180 days | Regenerate, update `.env` + `infra/prometheus.yml` env |

## Known Accepted Risks

A small number of low-severity hardening items are tracked internally and
addressed on the schedule above. Responsible-disclosure reports for anything
not listed here are welcome at the contact at the top of this file.
