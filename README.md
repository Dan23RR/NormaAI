# NormaAI — EU Regulatory Intelligence Platform

> AI-powered compliance monitoring across 7 EU regulatory frameworks with real-time EUR-Lex integration, anti-hallucination verification, and Italian legislation support.

[![CI](https://github.com/danielculotta/normaai/actions/workflows/ci.yml/badge.svg)](https://github.com/danielculotta/normaai/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## Overview

NormaAI monitors 7 major EU regulatory frameworks in real-time and provides AI-powered compliance intelligence for enterprises:

| Framework | Full Name | Status |
|-----------|-----------|--------|
| **CSRD** | Corporate Sustainability Reporting Directive | Active |
| **CSDDD** | Corporate Sustainability Due Diligence Directive | Active |
| **AI Act** | EU Artificial Intelligence Act | Active |
| **DORA** | Digital Operational Resilience Act | Active |
| **NIS2** | Network and Information Security Directive | Active |
| **EU Taxonomy** | Sustainable Finance Taxonomy Regulation | Active |
| **GDPR** | General Data Protection Regulation | Active |

### Core Capabilities

- **Regulatory Q&A** — Ask questions about EU regulations, get cited answers grounded in official texts
- **Gap Analysis** — Compliance assessment with per-requirement scoring and remediation plans
- **Impact Monitor** — Real-time analysis of regulatory changes on your company
- **EUR-Lex Crawler** — Automated SPARQL-based ingestion from official EU legislative database
- **Normattiva Crawler** — Italian implementing legislation via Open Data API (D.Lgs., Leggi)
- **CoVe Anti-Hallucination** — 5-phase Chain-of-Verification pipeline for citation accuracy
- **SSE Streaming** — Real-time streamed responses with verification progress events

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        FastAPI Gateway                       │
│          JWT Auth · Rate Limiting · Request Tracking          │
├──────────┬──────────┬──────────┬───────────────────────────┤
│   Q&A    │   Gap    │ Monitor  │     EUR-Lex Crawler        │
│  Agent   │ Analyst  │  Agent   │     (SPARQL Client)        │
├──────────┴──────────┴──────────┴───────────────────────────┤
│                    LangGraph Orchestrator                     │
│        Router → Retrieve → Agent → Confidence Check          │
├─────────────────────────────────────────────────────────────┤
│  Qdrant (Hybrid Search)  │  PostgreSQL  │  Redis (Cache)    │
│  BGE-base + BM25 + RRF   │  SQLAlchemy  │                   │
├─────────────────────────────────────────────────────────────┤
│              Document Processing Pipeline                    │
│        dots.ocr · Docling · BeautifulSoup (fallback)         │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- A Google (Gemini) or Anthropic API key

### 1. Clone & Configure

```bash
git clone https://github.com/danielculotta/normaai.git
cd normaai
cp .env.example .env
# Edit .env with your API keys and settings
```

### 2. Generate JWT Keys

NormaAI uses RSA key pairs for JWT token signing. Generate them before starting:

```bash
openssl genrsa -out jwt_private.pem 2048
openssl rsa -in jwt_private.pem -pubout -out jwt_public.pem
```

These files are git-ignored and must be generated locally by each developer.

### 3. Generate App Secret Key

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
# Copy the output into APP_SECRET_KEY in your .env file
```

### 4. Start Infrastructure

```bash
docker compose up -d postgres qdrant redis
```

### 5. Install Dependencies

```bash
# Using Poetry (recommended)
poetry install

# With observability extras
poetry install -E observability
```

### 6. Initialize Database

```bash
# The database is auto-initialized by the docker-entrypoint script
# For manual migration:
alembic upgrade head
```

### 7. Seed Regulatory Data

```bash
python -m src.pipeline seed
```

### 8. Run the Server

```bash
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

Visit http://localhost:8000 for the landing page, http://localhost:8000/docs for Swagger UI.

### Docker Deployment

```bash
# Full stack (app + infrastructure)
docker compose up -d

# Build only
docker compose build app
```

## API Reference

### Authentication

All intelligence endpoints require JWT authentication:

```bash
# Register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "securepassword", "org_name": "Acme Srl"}'

# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "securepassword"}'
```

### Intelligence Endpoints

| Endpoint | Method | Auth | Rate Limit | Description |
|----------|--------|------|------------|-------------|
| `/api/v1/qa` | POST | Required | 10/min | Regulatory Q&A with citations |
| `/api/v1/qa/stream` | POST | Required | 10/min | Streaming Q&A with SSE events |
| `/api/v1/gap-analysis` | POST | Required | 5/min | Compliance gap analysis |
| `/api/v1/gap-analysis/stream` | POST | Required | 5/min | Streaming gap analysis |
| `/api/v1/monitor` | POST | Required | 10/min | Regulatory change impact |
| `/api/v1/monitor/stream` | POST | Required | 10/min | Streaming monitor analysis |
| `/api/v1/crawl` | POST | Required | 2/min | Trigger EUR-Lex crawl |

### System Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/health` | GET | Public | Liveness probe (process up) |
| `/readyz` | GET | Public | Readiness probe (503 when Qdrant/LLM unavailable) |
| `/api/v1/stats` | GET | Public | System health and statistics |
| `/api/v1/processors` | GET | Public | Document processing engine status |
| `/api/v1/metrics` | GET | Admin | Detailed request metrics |
| `/api/v1/metrics/prometheus` | GET | Scrape token / Admin | Prometheus exposition format |

### Example: Q&A

```bash
curl -X POST http://localhost:8000/api/v1/qa \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Does a company with 800 employees need to report under CSRD after the Omnibus changes?",
    "company_profile": {
      "name": "TechCorp Srl",
      "sector": "Technology",
      "employee_count": 800,
      "revenue_eur": 50000000,
      "jurisdictions": ["IT"]
    }
  }'
```

## Project Structure

```
normaai/
├── src/
│   ├── api/                       # FastAPI app, routers, middleware
│   ├── agents/                    # LangGraph orchestration & LLM nodes
│   ├── auth/                      # JWT, RBAC, brute-force protection
│   ├── crawler/eurlex/            # EUR-Lex SPARQL client
│   ├── db/                        # SQLAlchemy models & async engine
│   ├── nlp/
│   │   ├── chunking/              # Legal-aware document chunking
│   │   ├── embedding/             # Qdrant hybrid indexer (dense + sparse)
│   │   └── processing/            # OCR & document processors
│   ├── config.py                  # Pydantic settings
│   ├── cache.py                   # Redis response cache (org-scoped)
│   ├── pipeline.py                # Ingestion orchestrator
│   └── resilience.py              # Circuit breaker & concurrency limiter
├── frontend/                      # Next.js 14 dashboard (TypeScript)
├── prompts/                       # LLM prompt templates
├── tests/                         # pytest + validation framework
├── alembic/                       # Database migrations
├── infra/                         # Prometheus, Grafana, Jaeger configs
├── scripts/                       # Database init scripts
├── .github/workflows/ci.yml       # CI/CD pipeline
├── Dockerfile                     # Multi-stage production build
├── docker-compose.yml             # Full stack orchestration
└── pyproject.toml                 # Dependencies & tooling config
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| **API Framework** | FastAPI 0.115+ with async/await |
| **Agent Orchestration** | LangGraph (StateGraph) |
| **LLM Providers** | Google Gemini 2.5 Flash / Anthropic Claude Sonnet 4.5 |
| **Vector Database** | Qdrant 1.12 (hybrid: BGE-base dense + BM25 sparse + RRF) |
| **Relational Database** | PostgreSQL 16 with SQLAlchemy 2.0 async |
| **Cache** | Redis 7 |
| **Authentication** | JWT RS256 + bcrypt password hashing |
| **Document Processing** | dots.ocr + IBM Docling + BeautifulSoup |
| **Embedding Model** | BAAI/bge-base-en-v1.5 (768d) |
| **Regulatory Data** | EUR-Lex SPARQL endpoint |
| **Frontend** | Next.js 14, TypeScript, Tailwind CSS, Recharts |
| **Observability** | OpenTelemetry + Sentry (optional) |
| **CI/CD** | GitHub Actions |
| **Containerization** | Docker multi-stage builds |

## Configuration

All configuration is managed through environment variables (loaded from `.env`).
See [`.env.example`](.env.example) for the complete list with documentation.

Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `gemini` | LLM provider: `gemini` or `anthropic` |
| `GOOGLE_API_KEY` | — | Google Gemini API key |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL connection string |
| `QDRANT_HOST` | `localhost` | Qdrant hostname |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `APP_SECRET_KEY` | — | Application secret (min 64 chars) |
| `APP_ENV` | `development` | Environment: development/staging/production |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated CORS origins |

## Development

```bash
# One-time: install pre-commit hooks (gitleaks + ruff before every commit)
pip install pre-commit && pre-commit install

# Run tests
pytest tests/ -v --cov=src

# Lint
ruff check src/ tests/

# Type check
mypy src/

# Format
ruff format src/ tests/
```

CI (GitHub Actions): lint+types, backend tests (Postgres/Qdrant/Redis services),
frontend tests+build, Docker build+health, Gitleaks (full history), Bandit, Trivy
(fs+image), CodeQL, CycloneDX SBOM. Releases (`v*.*.*` tags) publish a scanned
image to GHCR with attached SBOM (`.github/workflows/release.yml`).

## Operations

- [docs/RUNBOOK.md](docs/RUNBOOK.md) — incident response, deploy/rollback, maintenance cadence
- [docs/BACKUP_STRATEGY.md](docs/BACKUP_STRATEGY.md) — RPO 24h / RTO 1h, daily `pg_dump`, monthly restore test
- Observability: Prometheus alert rules ([infra/prometheus.rules.yml](infra/prometheus.rules.yml)) +
  provisioned Grafana dashboard "NormaAI — Health" (auto-loaded at `localhost:3001`)

## Security

See [SECURITY.md](SECURITY.md) for the vulnerability disclosure policy and key rotation schedule.

- JWT authentication (RS256) with organization-scoped tokens and RBAC
- Row-Level Security (RLS) in PostgreSQL for multi-tenant data isolation
- Input sanitization against prompt injection attacks
- Rate limiting on all intelligence endpoints
- Brute-force protection with Redis-backed lockout
- Non-root Docker containers with read-only filesystem
- Secret detection: gitleaks pre-commit hook + full-history scan in CI, Trivy, Bandit, CodeQL

## Regulatory Context

NormaAI is built with deep understanding of the EU regulatory landscape post-Omnibus I (Directive (EU) 2026/470, published OJ 26 February 2026, in force 18 March 2026):

- **CSRD scope narrowed** to 1,000+ employees (raised from 250)
- **ESRS data points reduced** by 61% from original Set 1
- **CSDDD transposition** deadline: 26 July 2028, first compliance: 26 July 2029
- **VSME Standard** voluntary — flagged for early adoption when beneficial

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines and how to submit changes.

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.

## Project Status

**Current release:** MVP / Pre-Production (v0.3.0 — see `pyproject.toml`)
**Last verified end-to-end:** 2026-04-28 — **312/312 tests passing** (99% empirical pass rate)

### Shipped (verified empirically, G1)

| Component | Status | Evidence |
|-----------|--------|----------|
| Backend API | ✅ Production-ready | 8 routers, 33+ endpoints across `src/api/routers/` + `src/auth/router.py` |
| LangGraph Orchestration | ✅ Complete | `src/agents/graph.py`, `nodes.py`, `router.py` |
| Hybrid Search (RRF) | ✅ Complete | `tests/test_hybrid_search.py` (13 tests, 100% pass) |
| JWT Auth + RLS | ✅ Complete | `alembic/versions/002_enable_rls_policies.py` |
| CoVe Anti-Hallucination | ✅ Integrated | `src/agents/cove/` + 4 prompt templates |
| SSE Streaming | ✅ Connected | `src/api/streaming/sse.py` |
| EUR-Lex Crawler | ✅ Complete | `src/crawler/eurlex/client.py` (18 tests) |
| Normattiva Crawler | ✅ Integrated | `src/crawler/normattiva/` (15 tests) |
| Frontend Dashboard (Next.js 14) | ✅ Complete | 31 pages under `frontend/src/app/dashboard/` |
| **Public Landing Page (IT)** | ✅ Complete (G2) | `frontend/src/app/page.tsx` |
| Alembic Migrations | ✅ Complete | 4 revisions: 001 schema, 002 RLS, 003 temporal, 004 normattiva+CoVe |
| Test suite | ✅ **312/312 PASS** | 17 files, run tier-by-tier via `run_tests.ps1` |

### Test pass rate per tier (2026-04-28)

```
TIER 1 - Pure unit (no infra)    38/38   100%
TIER 2 - DB/Auth (sqlite)        57/57   100%
TIER 3 - Cache (Redis mock)      30/30   100%
TIER 4 - Hybrid Search (Qdrant)  13/13   100%
TIER 5 - LLM/Agents              60/60   100%
TIER 6 - External APIs           30/30   100% (+3 skipped network tests)
TIER 7 - API integration         36/36   100%
TIER 8 - Monte Carlo             48/48   100%
                                 ─────  ────
                                312/312  100%
```

---

Built with LangGraph + Qdrant Hybrid Search + EUR-Lex SPARQL + Normattiva Open Data
