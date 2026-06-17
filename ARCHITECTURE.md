# NormaAI — Architecture

> Architecture Decision Records and technical deep-dive for contributors.
> Operations: [docs/RUNBOOK.md](docs/RUNBOOK.md) · [docs/BACKUP_STRATEGY.md](docs/BACKUP_STRATEGY.md) · [SECURITY.md](SECURITY.md)

## System Overview

```
┌─────────────── Frontend (Next.js 14 + TypeScript) ───────────────┐
│  Dashboard  │  Login  │  Company Profile  │  SSE Streaming UI    │
└──────────────────────────┬───────────────────────────────────────┘
                           │ HTTPS / SSE
┌──────────────────────────▼───────────────────────────────────────┐
│                     FastAPI Gateway (async)                       │
│  ┌─────────┐  ┌──────────┐  ┌───────────┐  ┌────────────────┐  │
│  │ JWT Auth │  │ Rate     │  │ Request   │  │ CORS / Helmet  │  │
│  │ RS256    │  │ Limiter  │  │ Tracking  │  │ Security Hdrs  │  │
│  └─────────┘  └──────────┘  └───────────┘  └────────────────┘  │
├──────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────┐    │
│  │              Intelligence Router                          │    │
│  │  /qa  │  /gap-analysis  │  /monitor  │  /*/stream (SSE)  │    │
│  └──────────────────────┬───────────────────────────────────┘    │
│                         │                                        │
│  ┌──────────────────────▼───────────────────────────────────┐    │
│  │              LangGraph StateGraph                         │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌────────────────┐   │    │
│  │  │ Retrieve     │→│ Route Agent  │→│ Agent Node       │   │    │
│  │  │ (Qdrant)     │  │ (qa/gap/mon) │  │ (async LLM)    │   │    │
│  │  └──────────────┘  └─────────────┘  └───────┬────────┘   │    │
│  │                                              │            │    │
│  │  ┌───────────────────┐  ┌────────────────────▼────────┐  │    │
│  │  │ CoVe Verification  │←│ Confidence Check            │  │    │
│  │  │ (5-phase pipeline) │  │ (threshold: 0.85)          │  │    │
│  │  └───────────────────┘  └────────────────────────────┘   │    │
│  └──────────────────────────────────────────────────────────┘    │
├──────────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐    │
│  │ Qdrant    │  │ Postgres │  │ Redis    │  │ Observability │    │
│  │ Hybrid    │  │ 16 + RLS │  │ Cache    │  │ OTel+Prom    │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

## Design Decisions (ADRs)

### ADR-1: Hybrid Search (Dense + Sparse + RRF)

**Status:** Accepted  
**Context:** Legal documents contain both exact terms (article numbers, CELEX identifiers, thresholds) and semantic concepts (sustainability, due diligence). Pure dense search misses exact matches; pure keyword search misses paraphrases.

**Decision:** Use hybrid search with:
- **Dense vectors:** paraphrase-multilingual-mpnet-base-v2 (768-dim) via fastembed
- **Sparse vectors:** Hash-based BM25 (30K vocab, MD5 → index mapping)
- **Fusion:** Reciprocal Rank Fusion with k=60

**Consequences:**
- +15-20% retrieval accuracy on legal benchmark vs. dense-only
- No need for a separate full-text search engine (Elasticsearch)
- Hash-based sparse vectors avoid vocabulary synchronization across nodes

### ADR-2: Row-Level Security (RLS) for Multi-Tenancy

**Status:** Accepted  
**Context:** Multiple organizations share the same PostgreSQL database. Application-level filtering is error-prone and requires every query to include `WHERE org_id = ...`.

**Decision:** Use PostgreSQL RLS policies with `SET LOCAL app.current_org_id` set at session start via SQLAlchemy events.

**Consequences:**
- Data isolation enforced at database level — impossible to leak cross-tenant data
- No need to audit every SQL query for missing WHERE clauses
- Small performance overhead (~1-2ms per session for SET LOCAL)

### ADR-3: LangGraph for Agent Orchestration

**Status:** Accepted  
**Context:** The system has multiple agent types (QA, Gap Analysis, Monitor) with shared retrieval, conditional routing, and verification steps. A simple sequential pipeline doesn't capture this complexity.

**Decision:** Use LangGraph's StateGraph with:
- Separate sync/async graph compilation
- Conditional edges for routing and CoVe gating
- Thread-safe singleton pattern for graph instances

**Consequences:**
- Clean separation of orchestration (graph.py) from business logic (nodes.py)
- Easy to add new agents without modifying the core graph
- Async graph uses native `.ainvoke()` — no thread pool blocking

### ADR-4: Chain-of-Verification (CoVe) Anti-Hallucination

**Status:** Accepted  
**Context:** In the legal domain, hallucinated citations or incorrect regulatory thresholds can have serious business consequences. Standard RAG confidence scores are insufficient.

**Decision:** Implement a 5-phase verification pipeline:
1. **Draft** — Generate initial LLM response
2. **Planning** — Extract claims and generate verification questions
3. **Independent Verification** — Answer each question in isolated context
4. **Revision** — Correct the draft based on verification results
5. **Citation Validation** — Verify every CELEX/URN against EUR-Lex/Normattiva APIs

**Consequences:**
- 2-5x increase in latency for verified responses (mitigated by SSE streaming)
- Near-zero hallucinated citations in production
- Only triggered when confidence < 0.85 (configurable threshold)

### ADR-6: SNC Trust Layer (Behavioral Trust Clustering)

**Status:** Accepted (2026-05)
**Context:** CoVe verifies *claims after generation*, but says nothing about the
*stability* of the model's behavior on a given query. Unstable queries (where
K samples disagree behaviorally) correlate with hallucination risk before any
claim is checked.

**Decision:** Insert an SNC governance node before the confidence check:
generate K-1 additional samples (default K=3, temperature 0.7), cluster them
behaviorally, compute a closed-form trust score, and route three ways:

- `ADMIT_HIGH` (trust ≥ 0.85) — skip CoVe, answer directly
- `ADMIT_MID` — proceed to the legacy CoVe gate
- `ABSTAIN` (trust < 0.50) — return an abstention, flag for expert review

**Consequences:**
- K-1 extra LLM calls per gated request (parallelized; bounded by the LLM semaphore)
- Abstention becomes a first-class outcome — in a legal product, "I'm not sure"
  beats a confident error
- Config: `SNC_ENABLED`, `SNC_K`, `SNC_THETA_HIGH`, `SNC_THETA_LOW`

### ADR-5: JWT RS256 with Refresh Token Rotation

**Status:** Accepted  
**Context:** The API needs stateless authentication with support for token revocation and multi-device sessions.

**Decision:** Use RS256 (RSA asymmetric) JWT with:
- 15-minute access token TTL
- 7-day refresh token with family tracking
- Redis-backed blacklist for immediate revocation
- Replay attack detection via token family chains

**Consequences:**
- Public key can be shared with downstream services for verification
- Key rotation via file swap without database changes
- Redis TTL auto-cleans expired tokens

## Data Flow

### Regulatory Q&A Flow

```
User Question → Sanitize → Retrieve (Qdrant hybrid) → Route → QA Agent (LLM)
    → Confidence Check → [if < 0.85] → CoVe 5-phase verification → Response
    → [if ≥ 0.85] → Response with citations
```

### Ingestion Pipeline Flow

```
EUR-Lex SPARQL → Metadata → CELLAR XHTML full text → Legal Chunker → Contextual Enrichment
    → Hybrid Embedding (Dense + Sparse) → Qdrant Indexing

Normattiva API → Search → Download Text → Chunk → Enrich → Index
```

### SSE Streaming Flow

```
Request → Agent Graph → Draft PhaseChangeEvent
    → TokenEvents (chunked answer, 80-char blocks)
    → CitationEvents (per-citation)
    → [CoVe] → ThinkingEvents → VerificationEvents
    → DoneEvent (confidence, token count, review flag)
```

## Module Boundaries

| Module | Responsibility | Dependencies |
|--------|---------------|-------------|
| `src/api/` | HTTP routing, middleware, SSE formatting | FastAPI, auth |
| `src/agents/` | LangGraph orchestration, LLM calls, CoVe | LangGraph, LLM providers |
| `src/auth/` | JWT, RBAC, brute-force protection | Redis, cryptography |
| `src/crawler/` | EUR-Lex SPARQL, Normattiva API | httpx, SPARQLWrapper |
| `src/nlp/` | Chunking, embedding, indexing | fastembed, Qdrant |
| `src/db/` | SQLAlchemy models, async engine, RLS | SQLAlchemy, asyncpg |
| `src/` | Config, cache, resilience, observability | Pydantic, Redis, OTel |

## Security Model

```
                    ┌─────────────────────────┐
                    │  Request arrives         │
                    └────────┬────────────────┘
                             │
                    ┌────────▼────────────────┐
                    │  Rate Limiter            │
                    │  (per-endpoint, per-IP)  │
                    └────────┬────────────────┘
                             │
                    ┌────────▼────────────────┐
                    │  JWT RS256 Verification   │
                    │  + Redis blacklist check  │
                    └────────┬────────────────┘
                             │
                    ┌────────▼────────────────┐
                    │  RBAC Role Check         │
                    │  (admin/member/viewer)   │
                    └────────┬────────────────┘
                             │
                    ┌────────▼────────────────┐
                    │  Input Sanitization       │
                    │  (prompt injection, XSS)  │
                    └────────┬────────────────┘
                             │
                    ┌────────▼────────────────┐
                    │  RLS Enforcement          │
                    │  SET LOCAL org_id         │
                    └────────┬────────────────┘
                             │
                    ┌────────▼────────────────┐
                    │  Business Logic           │
                    └──────────────────────────┘
```

## Running Tests

```bash
# Full test suite
pytest tests/ -v --cov=src --cov-report=term-missing

# Specific modules
pytest tests/test_cove.py -v
pytest tests/test_hybrid_search.py -v
pytest tests/test_normattiva_client.py -v
pytest tests/test_api_integration.py -v

# With coverage threshold
pytest tests/ --cov=src --cov-fail-under=60
```
