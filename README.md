# NormaAI

Checks the legal references of a document against the text in force, and tells you when a
provision it cites changes.

[![CI](https://github.com/Dan23RR/NormaAI/actions/workflows/ci.yml/badge.svg)](https://github.com/Dan23RR/NormaAI/actions)

> **In breve.** Controlla i riferimenti di legge dei tuoi documenti sul testo vigente.
> Norme UE e italiane, parola per parola. Con l'avviso quando una norma citata cambia.
> E chiedi: risposte con il passaggio di legge che le sostiene.
>
> Progetto open source (licenza MIT) pensato per consulenti e PMI italiane. Il backend di
> produzione è fermo e in fase di trasloco: gli account sono sospesi fino al nuovo server.
> Il controllo dei documenti si prova da riga di comando, senza account (sotto). Sito:
> [normaai.org](https://normaai.org). La documentazione tecnica è in inglese.

## What it is

NormaAI reads a document (a privacy notice, an AI policy, a contract clause, a note),
finds every reference to EU or Italian law in it, and checks each one against the official
text in force: the article must exist, and every quoted passage must be there word for word.
It records the provisions the document relies on, so a later run (or a weekly job on the
server) says which of them changed. A second surface answers questions on a corpus of 18 EU
acts, and every citation in an answer is checked word for word against the retrieved text by
deterministic code, not by a language model.

## Try the document check (no account, no infrastructure)

You need Python 3.11 or 3.12, the backend dependencies (`poetry install`) and network access
to EUR-Lex and Normattiva. No database, no API key, no `.env`.

```bash
git clone https://github.com/Dan23RR/NormaAI.git && cd NormaAI
poetry install
cat > nota.txt <<'EOF'
Ai sensi dell'articolo 33, paragrafo 1, del regolamento (UE) 2016/679, il titolare notifica la violazione «senza ingiustificato ritardo e, ove possibile, entro 48 ore dal momento in cui ne è venuto a conoscenza».
L'informativa segue l'art. 13 del GDPR, l'art. 100 del GDPR e l'art. 2-ter del d.lgs. 196/2003.
EOF
poetry run python scripts/check_document.py nota.txt
```

What it printed on 2026-11-11 (about 12 seconds with an empty cache):

```
Controllo di nota.txt (11/11/2026): 4 disposizioni citate.
2 da correggere, 0 da controllare, 2 a posto, 0 fuori copertura.
- riga 1, GDPR, art. 33, par. 1: Citazione diversa dal testo ufficiale
- riga 2, GDPR, art. 100: Non esiste nel testo vigente
Report: nota.controllo.html
Disposizioni citate: nota.norma-lock.json
```

The HTML report (in Italian) shows each finding with the official wording and a link to the
text in force; for article 33 it says that the document has "48" where the official text has
"72". The lock file lists the provisions found in force (here GDPR art. 33 and 13, d.lgs.
196/2003 art. 2-ter) with a SHA-256 of their text. Later:

```bash
poetry run python scripts/check_document.py --ricontrolla nota.norma-lock.json   # what changed since
poetry run python scripts/check_document.py policy.docx --data 2026-03-15        # what changed after the document's date
```

Formats: `.docx`, `.pdf` (text layer only, no OCR), `.html`, `.txt`, `.md`. Every outcome,
the citation forms recognised, the cache and the measured run times are in
[docs/DOCUMENT_CHECK.md](docs/DOCUMENT_CHECK.md).

**Where the texts come from.** EU acts from CELLAR, the repository behind EUR-Lex, by CELEX
number: any EU act the document cites, not only the 18 of the Q&A corpus, in the latest
consolidated version CELLAR gives as text, with the earlier versions for outdated quotes.
Italian state acts from the [Normattiva open data API](https://dati.normattiva.it/), article
by article, as in force on a given day. Neither is the official text: EUR-Lex consolidated
texts are documentation (the Official Journal is authentic), and Normattiva's texts are not
official (the Gazzetta Ufficiale prevails). Normattiva data are licensed CC BY 4.0, and the
report says so.

## How verification works

The same rule serves the document check and the Q&A answers
(`src/agents/citation_verifier.py`, pure functions, no network, no language model):

1. Quote and official text are normalised (Unicode form, case, typographic quotes and
   dashes, spaces, soft hyphens).
2. A quote shorter than 20 characters or 4 words is never verified: too generic.
3. The quote must appear as a substring of the official text. A quote with omissions
   (`[...]`) is split there, and each segment of at least 12 characters must appear, in order.
4. Failing that, a span with a similarity ratio of at least 0.92 is accepted only when the
   words agree: every number, every number word and every word under five letters ("non",
   "o", "e", "may", "not") must be identical. What is forgiven: punctuation, accents, a word
   split or joined at a line break, one wrong, missing or extra letter inside a longer word.
5. A close span that differs in a word that matters is **not** a verification. The result
   stays unverified and carries `near_quote` (the official wording), `near_article` (where it
   is) and `differences`.
6. Text uploaded by a tenant never counts as official text.

Example of a near match that is refused: the document quotes article 33(1) GDPR as "entro 48
ore dal momento in cui ne è venuto a conoscenza"; the official text says "entro 72 ore". The
two strings are almost identical, but the numbers differ, so the quote is reported as
"Citazione diversa dal testo ufficiale" with `differences: [{"quoted": "48", "official": "72"}]`.

A literal quote can still leave out context that changes its meaning (a "non" just before
it): the interface and the report show the official passage in place.

## What is and is not covered

| Capability | Status | Where |
|---|---|---|
| Document check, EU law (any act by CELEX, consolidated versions) | wired | `src/document_check/official.py`, `check.py` |
| Document check, Italian state law (Normattiva, article by article) | wired | `src/document_check/normattiva.py` |
| Regional laws, ministerial decrees, circulars, annexes of Italian acts | not built: listed as "fuori copertura" | `src/document_check/extract.py` |
| Case law, authority guidance | not built | |
| Lock file and re-check from the command line | wired | `scripts/check_document.py` |
| Documents HTTP API: check, storage, re-check, HTML report, alerts | wired | `src/api/routers/documents.py`, `src/document_check/service.py` |
| Weekly surveillance of watched documents, digest email | wired, runs as a cron job on the server | `src/document_check/surveillance.py`, `src/email_client.py` |
| Web screen for the document check | not built in this branch | |
| Q&A on 18 EU acts, IT and EN, with word-for-word citation check | wired | `src/agents/nodes.py`, `src/agents/citation_verifier.py` |
| Abstention when retrieval finds nothing (decided in code, no model call) | wired | `_abstain_without_sources` in `src/agents/nodes.py` |
| Italian law in the Q&A corpus | not built | old client in `src/crawler/normattiva/` (see below) |
| Citation check on gap-analysis and monitor answers | not built: only Q&A answers are checked | `src/agents/nodes.py` |
| Chain-of-Verification (CoVe) | partial: only when a request sets `enable_cove`; no live EUR-Lex lookup | `src/agents/cove/` |
| Multi-sampling trust layer (SNC) | wired, off by default (`SNC_ENABLED=false`) | `src/agents/snc_layer.py` |
| Cross-encoder reranker | wired, off by default (no model directory set) | `src/nlp/embedding/reranker.py` |
| Streaming of answers | partial: the answer is sent in 80-character slices after it is generated, not token by token | `src/api/streaming/generators.py` |
| Corpus freshness check against CELLAR | wired, nightly cron; reports, does not reseed | `src/pipeline.py`, `GET /api/v1/stats` |
| Corpus update | partial: by hand (`--action update`); the in-process scheduler is off | `src/pipeline.py`, `src/crawler/scheduler.py` |
| Scope rules (CSRD, CSDDD, AI Act art. 50) and deadline calendar | partial: written by hand in the frontend | `frontend/src/lib/scope`, `frontend/src/lib/obligations` |
| Gap analysis | partial: a requirements checklist written by the model from the retrieved passages and the profile you type, not an assessment of your documents | `src/agents/nodes.py`, `prompts/` |
| PDF reports, GDPR export and erasure (admin) | wired | `src/api/routers/reports.py`, `src/api/routers/gdpr.py` |
| Password reset, multi-factor authentication, single sign-on | not built | |

Each scope rule and calendar date names the source it comes from, with the day it was last
checked (`VERIFIED_ON` in `frontend/src/lib/scope/sources.ts`); in this branch that check was
made against the repository's own pages, not yet against the official texts.

## The Q&A corpus

`TRACKED_ACTS` in `src/crawler/eurlex/client.py` lists 18 EU acts, seeded in English and
Italian (`CORPUS_LANGUAGES=EN,IT`), from the latest CELLAR consolidated text when one exists
(`EURLEX_PREFER_CONSOLIDATED=true`) and from the original publication otherwise (the amending
acts):

| Framework | Acts (CELEX) |
|---|---|
| CSRD | 32022L2464 (CSRD), 32013L0034 (Accounting Directive), 32023R2772 (ESRS Set 1), 32025L0794 (Stop-the-Clock, amending), 32026L0470 (Omnibus I, amending) |
| CSDDD | 32024L1760 |
| AI Act | 32024R1689, 32026R1744 (Digital Omnibus on AI, amending) |
| DORA | 32022R2554, 32024R1773, 32024R1774, 32024R2956 |
| NIS2 | 32022L2555 |
| Taxonomy | 32020R0852, 32023R2486 |
| GDPR | 32016R0679 |
| CRA | 32024R2847, 32025R2392 |

**No Italian law in the Q&A corpus.** The seed still calls the old client in
`src/crawler/normattiva/` when `DATA_SOURCE` is `both` (the default) or `normattiva`. The
endpoints it calls (`https://www.normattiva.it/opendata/api/...`) answered on 2026-11-11 with
HTTP 409 and a page of the Poligrafico's protection systems, so no Italian passage is indexed.
The document check uses the newer open data API instead (`src/document_check/normattiva.py`).
Set `DATA_SOURCE=eurlex` to skip the attempt.

Measured quality is in [docs/MODELS.md](docs/MODELS.md). Golden v2 (101 questions) end to end
on 2026-11-09: 96 / 101 passed, 99.79 % of citations verified word for word, with
multilingual-e5-large embeddings and Claude Haiku 5.5. That is **not** the default
configuration: the code defaults to the mpnet embedding model (`EMBEDDING_MODEL`) and to
Google Gemini (`LLM_PROVIDER=gemini`), which docs/MODELS.md does not report a golden-set run
for.

## Running the full stack

### Prerequisites

- Python 3.11 or 3.12 (`pyproject.toml`), Poetry
- Docker with Compose
- An API key of one language-model provider: Google Gemini (default), Anthropic, OpenRouter or
  Mistral (`LLM_PROVIDER`)
- Node.js for the frontend

### 1. Configure

```bash
cp .env.example .env
# set at least POSTGRES_PASSWORD, APP_SECRET_KEY and the key of your provider
python -c "import secrets; print(secrets.token_urlsafe(64))"   # a value for APP_SECRET_KEY
```

JWT signing uses an RSA key pair. Generate it once (the files are git-ignored):

```bash
openssl genrsa -out jwt_private.pem 2048
openssl rsa -in jwt_private.pem -pubout -out jwt_public.pem
```

Without the pair the API falls back to HS256 in development and refuses to start with
`APP_ENV=production`.

### 2. Infrastructure, schema, corpus

```bash
docker compose up -d postgres qdrant redis
poetry install                           # extras: -E observability, -E openrouter (also Mistral), -E local-llm
alembic upgrade head                     # 9 migrations in alembic/versions/
python -m src.pipeline --action seed     # the 18 acts, EN + IT
python -m src.pipeline --action seed --acts AI_ACT --lang IT   # a subset (CELEX ids or framework names)
python -m src.pipeline --action seed --recreate                # drop and rebuild the Qdrant collection
```

Locally `docker compose` also reads `docker-compose.override.yml`, which publishes Postgres on
5433, Redis on 6380 and Qdrant on 6335: point `DATABASE_URL`, `REDIS_URL` and `QDRANT_PORT` in
`.env` at those ports, or start with `docker compose -f docker-compose.yml`. The seed downloads
from CELLAR and embeds every passage on the CPU: count on a long first run.

### 3. API and frontend

```bash
uvicorn src.api.main:app --reload --port 8000    # Swagger UI at http://localhost:8000/docs
cd frontend && npm ci && NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
```

`docker compose up -d` builds and starts the app container as well, with Prometheus, Grafana
and Jaeger.

### Scheduled jobs

On the server these run from cron, not from the API process
([docs/RUNBOOK.md](docs/RUNBOOK.md), section 10):

```bash
python -m src.pipeline --action check-freshness     # nightly: indexed versions against CELLAR
python -m src.pipeline --action recheck-documents   # weekly: watched documents, alerts, digest email
python -m src.pipeline --action update --days-back 7   # by hand: new EUR-Lex content
```

The digest email needs a Resend key and the public address of the API (`API_PUBLIC_URL` or
`API_DOMAIN`): with neither address no digest is sent.

## API overview

Registration is invite-only by default (`REGISTRATION_MODE=invite`; also `open` or
`closed`). The first invite is minted on the server:

```bash
python scripts/create_invite.py --email founder@example.com
```

| Area | Routes | Notes |
|---|---|---|
| Auth (`/api/v1/auth`) | `POST /register`, `/login`, `/refresh`, `/logout`, `/verify-email`, `/resend-verification`, `POST`/`GET /invites`, `GET /me` | per-IP limits on register, login, refresh, verification |
| Documents (`/api/v1/documents`) | `POST /check`, `GET /checks`, `GET`/`DELETE /checks/{id}`, `POST /checks/{id}/recheck`, `GET /checks/{id}/report`, `GET`/`PATCH /preferences`, `GET`/`POST /unsubscribe` | no language model; own hourly limit (`DOCUMENT_CHECK_RATE_LIMIT`, 30/hour) |
| Intelligence (`/api/v1`) | `POST /qa`, `/gap-analysis`, `/monitor`, each with `/stream` | count against the daily LLM quota per organisation (`LLM_DAILY_QUOTA_PER_ORG`, 200) |
| Conversations, clients, alerts, reports (`/api/v1`) | `/conversations`, `/clients`, `/alerts`, `/reports/*` | |
| Data (`/api/v1`) | `POST /crawl` (staff only, `STAFF_EMAILS`), `POST /documents/upload`, `GET /processors` | an uploaded document is indexed for its organisation and never verifies a citation |
| GDPR (`/api/v1/gdpr`) | `GET /export`, `POST /erase` | admin only |
| System | `GET /health`, `/readyz`, `/api/v1/stats` (with corpus `freshness`), `/api/v1/system/quota`, `/api/v1/metrics` (admin), `/api/v1/metrics/prometheus` (scrape token) | |

`POST /api/v1/documents/check` takes a file (multipart, field `file`, at most 10 MB) or a text:

```bash
curl -X POST http://localhost:8000/api/v1/documents/check \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"text": "Ai sensi dell articolo 13 del GDPR ...", "filename": "nota.txt", "document_date": "2026-03-15"}'
```

The file is read in memory and not kept. What is stored: its name, its SHA-256, the dates,
the findings (the reference, at most 160 characters around it, the quotes, the outcome) and
the official text of each provision it cites. Checking, re-checking and deleting are refused
to the `viewer` role. The full request and response shapes are in the router's docstrings and
at `/docs`.

## Tests and CI

```bash
python -m pytest tests/test_document_check.py tests/test_citation_verifier.py -q   # targeted
python -m pytest --collect-only -q | tail -1                                     # the live count
ruff check src/ tests/ && ruff format --check src/ tests/
cd frontend && npx tsc --noEmit && npx vitest run
```

The full backend suite takes a long time on a laptop; `run_tests.ps1` runs it tier by tier.
CI (`.github/workflows/ci.yml`) runs on every push: ruff, mypy (a strict gate on ten modules),
the backend suite on Postgres, Qdrant and Redis with a coverage floor of 84 %, a schema-drift
gate (`alembic upgrade head` then `alembic check`), frontend type check, tests and build, a
Docker build with a health check, Gitleaks, Bandit, Trivy (report-only), CodeQL
(`codeql.yml`) and a CycloneDX SBOM. `release.yml` publishes an image to GHCR on a `v*.*.*`
tag and fails on fixable critical or high findings. `validation.yml` is a self-test of the
evaluation harness on canned outputs, not a measurement; `uptime.yml` checks the public site
and, once configured, the API every 30 minutes.

## Operations

- [docs/DEPLOY_CHECKLIST.md](docs/DEPLOY_CHECKLIST.md): putting a new server in production.
- [docs/RUNBOOK.md](docs/RUNBOOK.md): incidents, deploy and rollback, recurring jobs.
- [docs/BACKUP_STRATEGY.md](docs/BACKUP_STRATEGY.md): nightly encrypted off-site copies with
  restic. Data loss (RPO) up to 24 hours with a working nightly job; time to be back (RTO) not
  measured. As of 2026-11-11 no backup has been sent to a real repository and no restore has
  been done.

## Limits and known gaps

- **No production backend today.** The server was lost in September 2026 and is being
  rebuilt; accounts are suspended. The public site, the two static scope checkers
  (`frontend/public/scope-csrd.html`, `scope-aiact.html`) and a demo mode with declared sample
  data work. No customer is claimed.
- **Sessions.** Access and refresh tokens are kept in the browser's `localStorage`
  (`frontend/src/lib/auth.ts`). There is no password reset, no multi-factor authentication
  and no single sign-on.
- **Roles.** `viewer` is enforced only on the documents routes; elsewhere a viewer can do what
  a member can.
- **Audit trail.** Audit events are log lines (logger `normaai.audit`), not rows of a table,
  and are lost when the container is recreated.
- **Tenant isolation in the database** needs the overlay `docker-compose.rls.yml`: without it
  the app connects as the database superuser, which bypasses row-level security, and isolation
  rests on the queries' `org_id` filters alone.
- **Verifier.** The literal-wording rule (from 2026-11-11) has not been measured on the golden
  set yet; it can only lower the share of verified citations. Gap-analysis and monitor answers
  are not checked.
- **Models.** The EU-hosted option (`LLM_PROVIDER=mistral`) has never been called with a real
  key and is not measured. The measured configuration is not the default (see "The Q&A
  corpus").
- **Freshness.** A Q&A citation is checked against the corpus as seeded; the nightly
  freshness job reports a newer consolidated version, it does not reseed.
- **Monitoring.** No Alertmanager is connected: the Prometheus rules are seen only by opening
  Prometheus. `uptime.yml` is the only check that warns anyone.
- **Old wording in code.** The OpenAPI description in `src/api/main.py` and the page served at
  `/` by the API (`src/api/landing.py`) still describe the product of spring 2026.

## Security

See [SECURITY.md](SECURITY.md) for how to report a vulnerability, the controls in place, key
rotation and the known gaps, and [ARCHITECTURE.md](ARCHITECTURE.md) for the design.

## Contributing and licence

See [CONTRIBUTING.md](CONTRIBUTING.md). MIT licence, see [LICENSE](LICENSE).
