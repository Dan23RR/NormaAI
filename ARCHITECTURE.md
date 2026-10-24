# NormaAI - Architecture

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
- **Dense vectors:** paraphrase-multilingual-mpnet-base-v2 (768-dim) via fastembed (configurable: `EMBEDDING_MODEL`)
- **Sparse vectors:** hashed term frequencies (30K vocab, MD5 → index mapping) with Qdrant's `Modifier.IDF`, so BM25-style IDF weighting is computed server-side at query time
- **Fusion:** Reciprocal Rank Fusion with k=60

**Consequences:**
- +15-20% retrieval accuracy on legal benchmark vs. dense-only
- No need for a separate full-text search engine (Elasticsearch)
- Hash-based sparse vectors avoid vocabulary synchronization across nodes
- Point ids are deterministic (`UUID5(celex|lang|article|chunk_index|sha1(text))`): re-seeding an act replaces its chunks (delete per CELEX+lang, then upsert) instead of duplicating them; a `corpus_meta` point records `corpus_as_of`, the indexed acts and the embedding model
- Changing the embedding model or upgrading a pre-IDF collection requires `--recreate` + reseed (the indexer warns at startup)

### ADR-2: Row-Level Security (RLS) for Multi-Tenancy

**Status:** Accepted  
**Context:** Multiple organizations share the same PostgreSQL database. Application-level filtering is error-prone and requires every query to include `WHERE org_id = ...`.

**Decision:** Use PostgreSQL RLS policies with `SET LOCAL app.current_org_id` set at session start via SQLAlchemy events.

**Consequences:**
- Data isolation enforced at database level - impossible to leak cross-tenant data
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
- Async graph uses native `.ainvoke()` - no thread pool blocking

### ADR-4: Chain-of-Verification (CoVe) Anti-Hallucination

**Status:** Accepted  
**Context:** In the legal domain, hallucinated citations or incorrect regulatory thresholds can have serious business consequences. Standard RAG confidence scores are insufficient.

**Decision:** Implement a 5-phase verification pipeline:
1. **Draft** - Generate initial LLM response
2. **Planning** - Extract claims and generate verification questions
3. **Independent Verification** - Answer each question in isolated context
4. **Revision** - Correct the draft based on verification results
5. **Citation Validation** - Verify every CELEX/URN against EUR-Lex/Normattiva APIs

**Consequences:**
- 2-5x increase in latency for verified responses (mitigated by SSE streaming)
- Every CELEX/URN citation is validated against the live EUR-Lex/Normattiva APIs at generation time, so a hallucinated identifier is caught before it reaches the user (engineered and unit-tested at MVP scale; not yet measured against a production-volume benchmark)
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

- `ADMIT_HIGH` (trust ≥ 0.85) - skip CoVe, answer directly
- `ADMIT_MID` - proceed to the legacy CoVe gate
- `ABSTAIN` (trust < 0.50) - return an abstention, flag for expert review

**Consequences:**
- K-1 extra LLM calls per gated request (parallelized; bounded by the LLM semaphore)
- Abstention becomes a first-class outcome - in a legal product, "I'm not sure"
  beats a confident error
- Config: `SNC_ENABLED`, `SNC_K`, `SNC_THETA_HIGH`, `SNC_THETA_LOW`
- **Off by default** (`SNC_ENABLED=false`, since 2026-10): the layer is opt-in
  per deployment because of its LLM cost and because a failed resample batch
  (provider/network error) degrades into an abstention. When the resamples fail
  the abstention is reported as `snc_degraded` (not `snc_low_trust`) and is
  never cached.

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
    → Grounding guard → Citation verifier (word for word) → Confidence Check
    → [if < 0.85] → CoVe 5-phase verification → Response
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
    → CitationEvents (per-citation, with the verifier's fields)
    → [CoVe] → ThinkingEvents → VerificationEvents
    → DoneEvent (confidence, token count, review flag, citation counters,
                 caveats, related frameworks, abstention reason, corpus date)
```

## Verifica deterministica delle citazioni

A Q&A citation is shown as "Verificata" only when the passage it quotes was
found, word for word, in one of the chunks retrieved for that answer. The check
is deterministic, with no LLM involved: `src/agents/citation_verifier.py` (pure
functions), run by the Q&A agent node right after the grounding guard (whose
`grounded` verdict is kept as it is) and again on the answer the SNC layer
serves.

**Rule.** The quote (`quote_snippet`) and the chunk text are normalized (NFKC,
casefold, typographic quotes and apostrophes to ASCII, every dash to `-`,
Unicode spaces to a space, soft hyphens and zero-width characters removed,
whitespace collapsed; the quote also loses surrounding quotes, punctuation and
ellipses). A quote shorter than 20 characters or 4 words is never verified (too
generic). Chunks are searched by level: the cited framework and article
(`"article"`; `Art. 50`, `articolo 50`, `50`, `50(1)`, `art. 50, par. 1` all
name article 50), then any chunk of the framework (`"framework"`), then every
chunk (`"any"`). Within a level the quote must be a substring of one chunk
(`"exact"`); a quote with omissions (`[...]`, `...`, `…`) is split there and
every segment of at least 12 characters must appear in the same chunk, in
order. Failing that, a span of the chunk whose difflib ratio with the quote is
at least 0.92 is accepted (`"fuzzy"`: punctuation or OCR differences).

**Fields.** Every citation gets, on a copy (the model's dicts are never
modified, and anything the model put in these keys is overwritten):

| Field | Verified citation | Unverified |
|-------|-------------------|------------|
| `verified` | `true` | `false` |
| `match` | `"exact"` / `"fuzzy"` | `null` |
| `level` | `"article"` / `"framework"` / `"any"` | `null` |
| `chunk_id` | Qdrant point id of the matching chunk | `null` |
| `celex` | base act (`32024R1689`, never a consolidated id) | `null` |
| `article`, `paragraph` | where the passage is (`"Art. 50"`, `"2"`) | `null` |
| `lang`, `consolidated_as_of` | language and version date of that text | `null` |
| `url` | `https://eur-lex.europa.eu/legal-content/{IT\|EN}/TXT/?uri=CELEX:{celex}`, built server-side in the chunk's language | `null` |
| `official_quote` | the exact span of the official text that matched | `null` |

The answer carries `verified_citations` and `citations_total`.

**Policy** (`CITATION_VERIFICATION`, `Settings.citation_verification`, default
`flag`). When an answer is not an abstention, has citations and none is
verified: `flag` serves it with `requires_expert_review = true`, confidence
capped at 0.6 and the caveat *"Nessuno dei passaggi citati è stato ritrovato
testualmente nei testi del corpus: verifica le fonti prima di usarla."* (its
English twin when the request language is English); such an answer may be
cached. `strict` replaces it with an abstention
(`abstention_reason = "unverified_citations"`, citations emptied, counters
kept), which is never cached and skips CoVe. The policy is idempotent and is
re-applied where an answer is delivered (`POST /qa`, fresh and cached; the SSE
stream; after CoVe, which revises the text but cannot clear the flag), so a
cached answer follows the current setting. The cache key carries a version
(`CACHE_KEY_VERSION = 2`) so answers cached before the verifier are never
served.

**Prompt.** Every source in the Q&A context is labelled
`[FRAMEWORK, Art. N] | CELEX … | act title | paragraphs | language`; the model is
told to cite the article exactly as labelled and to copy `quote_snippet`
verbatim from the labelled source, marking omissions with `[...]`.

**Golden set.** `tests/validation/metrics.py::verified_citation_rate` reports
the share of verified citations per case (`SuiteResult.avg_verified_citation_rate`);
it is informational and does not change the pass thresholds.

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

# Coverage gate. CI enforces a floor of 84% today (real coverage is ~88%,
# src/bizdev omitted). See .github/workflows/ci.yml for the authoritative,
# CI-enforced value.
pytest tests/ --cov=src --cov-fail-under=84
```
