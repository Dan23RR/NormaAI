# NormaAI - Architecture

> Architecture Decision Records and technical deep-dive for contributors.
> Operations: [docs/RUNBOOK.md](docs/RUNBOOK.md) · [docs/BACKUP_STRATEGY.md](docs/BACKUP_STRATEGY.md) · [SECURITY.md](SECURITY.md)

## System Overview

```
Frontend (Next.js 16, TypeScript; frontend/src/app/app/*: chiedi, ambito, monitoraggio, clienti, report, impostazioni, admin)
        │ HTTPS, Server-Sent Events
        ▼
FastAPI (src/api/main.py): JWT RS256, per-route rate limits, request id, security headers, CORS
        │
        ├── /api/v1/qa, /gap-analysis, /monitor (+ /stream) ── LangGraph (src/agents/graph.py)
        │       retrieve (Qdrant hybrid) → agent node (LLM) → SNC (off by default)
        │       → confidence check → [enable_cove and confidence < 0.85] CoVe
        │       Q&A only: citation verifier, word for word, on every answer
        │
        ├── /api/v1/documents/* ── src/document_check (no LLM)
        │       extract → official texts (CELLAR, Normattiva open data) → check → store
        │       weekly cron: python -m src.pipeline --action recheck-documents
        │
        └── auth, clients, alerts, conversations, reports, gdpr, data, system
        │
        ▼
Qdrant 1.20 (corpus + tenant uploads) · PostgreSQL 16 (RLS on tenant tables) · Redis 7 (cache,
token blacklist, lockout, quota) · optional Prometheus, Grafana, Jaeger, Sentry
```

## Design Decisions (ADRs)

### ADR-1: Hybrid Search (Dense + Sparse + RRF)

**Status:** Accepted  
**Context:** Legal documents contain both exact terms (article numbers, CELEX identifiers, thresholds) and semantic concepts (sustainability, due diligence). Pure dense search misses exact matches; pure keyword search misses paraphrases.

**Decision:** Use hybrid search with:
- **Dense vectors:** paraphrase-multilingual-mpnet-base-v2 (768-dim) via fastembed, the default of `EMBEDDING_MODEL`; the best measured runs of `docs/MODELS.md` use multilingual-e5-large (1024-dim) instead
- **Sparse vectors:** hashed term frequencies (30K vocab, MD5 → index mapping) with Qdrant's `Modifier.IDF`, so BM25-style IDF weighting is computed server-side at query time
- **Fusion:** Reciprocal Rank Fusion with k=60
- **Named articles:** an article the question names with its act ("art. 35, paragrafo 7, del GDPR") is looked up directly and fused as a third ranking (`src/nlp/embedding/article_refs.py`, docs/MODELS.md section 3.2)
- **Reranker:** a cross-encoder can rerank the fused candidates; the code is in `src/nlp/embedding/reranker.py` and is off unless `RERANKER_MODEL_DIR` is set

**Consequences:**
- Retrieval quality is measured, not assumed: `tests/validation/retrieval_eval.py` counts the questions of the golden set whose expected article is among the first 15 results, and `docs/MODELS.md` records the figure for every model tried (no comparison with dense-only search has been run)
- No need for a separate full-text search engine (Elasticsearch)
- Hash-based sparse vectors avoid vocabulary synchronization across nodes
- Point ids are deterministic (`UUID5(celex|lang|article|chunk_index|sha1(text))`): re-seeding an act replaces its chunks (delete per CELEX+lang, then upsert) instead of duplicating them; a `corpus_meta` point records `corpus_as_of`, the indexed acts and the embedding model
- Changing the embedding model or upgrading a pre-IDF collection requires `--recreate` + reseed (the indexer warns at startup)

### ADR-2: Row-Level Security (RLS) for Multi-Tenancy

**Status:** Accepted  
**Context:** Multiple organizations share the same PostgreSQL database. Application-level filtering is error-prone and requires every query to include `WHERE org_id = ...`.

**Decision:** Use PostgreSQL RLS policies on `current_setting('app.current_org_id')`.
`db_manager.session(org_id=...)` (`src/db/engine.py`) sets it transaction-local
(`set_config(..., true)`) at the start of every transaction through an `after_begin`
listener, and a pool check-in hook resets it, so a pooled connection never carries a
previous tenant's value.

**Consequences:**
- RLS is enabled and forced on `clients`, `alerts`, `assessments`, `conversations`,
  `parent_documents` (migration 007), `document_checks` and `document_dependencies`
  (migration 009). `users` and `organizations` have none, by design (migration 007): login,
  token refresh and `/auth/me` read them before an organisation is known.
- RLS is a second line, not the only one: every query of the routers also filters on the
  caller's `org_id`.
- **RLS is bypassed by a superuser or the table owner.** The default compose file connects
  the app as `normaai`, the image's superuser; only the overlay `docker-compose.rls.yml`
  (role `normaai_app`, created by `scripts/setup_app_role.sql`) makes the policies bite.
  Migrations still run as the owner.
- `scripts/validate_rls_two_tenant.py` and a CI step with a non-superuser role test the
  isolation.

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
5. **Citation Validation** - Check every CELEX identifier against the registry of indexed acts

**Consequences:**
- 2-5x increase in latency for the responses that go through it
- A CELEX identifier is accepted when it is well formed and belongs to an indexed act; anything else is reported as unverified. The code has a branch for a live EUR-Lex lookup, but nothing wires the client it needs, so no live lookup happens today
- It runs only when a request asks for it (`enable_cove`) and the answer's confidence is under 0.85; the web interface never asks, and the `COVE_ENABLED` setting only appears in the startup summary. The guarantee the product relies on is the deterministic citation verifier described below, which runs on every answer

### ADR-5: JWT RS256 with Refresh Token Rotation

**Status:** Accepted  
**Context:** The API needs stateless authentication with support for token revocation and multi-device sessions.

**Decision:** Use RS256 (RSA asymmetric) JWT with:
- 60-minute access token TTL (`ACCESS_TOKEN_EXPIRE_MINUTES`)
- 7-day refresh token with family tracking
- Redis-backed blacklist for immediate revocation (fail-closed with `APP_ENV=production`)
- Replay attack detection via token family chains

**Consequences:**
- Public key can be shared with downstream services for verification
- The API loads one key pair (`JWT_PRIVATE_KEY_PATH`, `JWT_PUBLIC_KEY_PATH`, `src/auth/security.py`).
  Rotating it is a file swap and a restart, with no database change, and every token signed
  with the old key stops being accepted at once: every user signs in again
- Without a key pair the API signs with HS256 and `APP_SECRET_KEY` in development, and
  refuses to start in production
- Redis TTL auto-cleans expired tokens
- The frontend keeps both tokens in `localStorage` (`frontend/src/lib/auth.ts`)

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

## Data Flow

### Regulatory Q&A Flow

```
User Question → Injection telemetry (logs only) → Retrieve (Qdrant hybrid)
    → [no passage retrieved] → abstention decided in code, the model is not called
    → Route → QA Agent (LLM) → Grounding guard → Citation verifier (word for word)
    → Confidence Check → Response with citations
    → [only when the request sets enable_cove] → CoVe 5-phase verification → Response
```

### Ingestion Pipeline Flow

```
TRACKED_ACTS (18 EU acts) → EUR-Lex SPARQL metadata → latest CELLAR consolidated text
    (original act when none) → XHTML per language (EN, IT) → Legal Chunker
    → Contextual Enrichment → Hybrid Embedding (Dense + Sparse) → Qdrant re-index per act + language
```

`python -m src.pipeline --action seed` runs it; `--action update` looks for new EUR-Lex
content and is run by hand (the in-process `AcquisitionScheduler` is off,
`ACQUISITION_SCHEDULER_ENABLED=false`). The nightly `--action check-freshness` compares the
consolidated version indexed for each act with the latest one in CELLAR and stores the outcome
in `system_state`, shown as `freshness` by `GET /api/v1/stats`; it does not reseed.

**No Italian law is indexed.** With `DATA_SOURCE=both` (the default) or `normattiva` the seed
also calls `seed_normattiva`, which uses the old client in `src/crawler/normattiva/client.py`.
The endpoints that client calls under `https://www.normattiva.it/opendata/api/` answered on
2026-11-11 with HTTP 409 and a page of the Poligrafico's protection systems; the client logs
the error and returns nothing, so the seed indexes no Italian passage. The document check
reads Italian law through the newer open data API instead (below).

### SSE Streaming Flow

```
Request → Agent Graph → Draft PhaseChangeEvent
    → TokenEvents (the finished answer cut into 80-char blocks: not token by token;
                   src/agents/streaming_llm.py exists but nothing calls it)
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
(`"exact"`); a quote with omissions (`[...]`, `...`, the ellipsis character U+2026) is split there and
every segment of at least 12 characters must appear in the same chunk, in
order. Failing that, a span of the chunk whose difflib ratio with the quote is
at least 0.92 is accepted (`"fuzzy"`) only when the words agree
(`wording_differences`): every number, every number word and every word under
five letters ("non", "o", "e", "may", "not") must be identical. What is
forgiven: punctuation, accents, a word split or joined at a line break, and one
wrong, missing or extra letter (not the first) inside a longer ordinary word.

**A close match is not a verification** (2026-11-11). A quote that says "entro
48 ore" where the article says "entro 72 ore" has a ratio above 0.99 and used to
be shown as verified. It now stays unverified and carries what was almost
matched: `near_quote` (the official wording), `near_article` (where it is) and
`differences` (`[{"quoted": "48", "official": "72"}]`). The search goes on
after a near match: the literal wording may be in another provision. A chunk
that carries an `org_id` is a document uploaded by a tenant and never verifies
a quote. A literal quote can still leave out context that changes its meaning
(the "non" just before it): the interface shows the official passage in place.
The effect of the stricter rule on the golden-set share of verified citations
has not been measured yet (it needs a live run); it can only lower it.

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
| `amending_celex`, `amending_article` | only for an article verified in the text of the act that amends it (below): that act and article; `url` is its page | `null` |
| `near_quote`, `near_article`, `differences` | `null` | set when a passage almost matched: its official wording, where it is, the words that differ |

The answer carries `verified_citations` and `citations_total`.

**Articles quoted by amending acts** (decided 2026-10-27,
`src/agents/quoted_articles.py`, run by `retrieve_node` on the chunks it keeps).
An amending act quotes whole articles of the act it amends; the chunker labels
such a passage with the amending act's own article and records the quoted one
(`quoted_article`, `amended_celex`). Such a passage is cited:

1. from the consolidated text, when the corpus holds the amended act and its
   article contains the passage's own words: the passage is replaced by that
   chunk (the prompt label names the amending act), so the answer cites the
   law as it stands and never a consolidated version older than the amendment;
2. otherwise as the amended act's article, cut where the quotation ends:
   labelled `[CELEX, Art. N]` in the prompt and verified as that article, with
   `amending_celex` / `amending_article` saying where its wording was found
   (the interface shows it under the source). Only for the first part of a
   quoted unit, which surely starts with the quoted article;
3. as retrieved in every other case (a later part that may already hold the
   next amendments, or one that starts with an amending instruction).

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
`[FRAMEWORK, Art. N] | CELEX <id> | act title | par. N | lang XX` (`_chunk_label` in
`src/agents/llm.py`, which also names the amending act when there is one); the model is
told to cite the article exactly as labelled and to copy `quote_snippet`
verbatim from the labelled source, marking omissions with `[...]`.

**Golden set.** `tests/validation/metrics.py::verified_citation_rate` reports
the share of verified citations per case (`SuiteResult.avg_verified_citation_rate`);
it is informational and does not change the pass thresholds.

## Document check

`src/document_check` checks the legal references of a document a user already has against
the official texts, with no language model. User guide, outcomes and measurements:
[docs/DOCUMENT_CHECK.md](docs/DOCUMENT_CHECK.md).

```
document (.docx .pdf .html .txt .md, in memory) → extract.py (acts, provisions, quotes; no network)
    → sources.default_source(): EU acts from CELLAR (official.py), Italian acts from Normattiva (normattiva.py)
    → check.py: provision exists in the text in force? quote word for word (citation_verifier)?
                in force on the document's date? → findings in four groups
    → report.py (HTML, Italian) · build_lock (provisions relied on) · service.py (store, API)
```

**Sources and versions.**

- EU law (`official.py`): any act cited by number, as its CELEX. The versions are the act
  as adopted followed by its CELLAR consolidated texts, oldest first
  (`02024R1689-20260727` is the AI Act as consolidated on 27 July 2026). Articles are rebuilt
  with the corpus chunker, so a provision is labelled as the Q&A labels it. A text is
  downloaded once per version and language and cached on disk; the list of versions is asked
  again after a day. When CELLAR gives no text for the newest version the check reads the
  newest one it can and says so.
- Italian law (`normattiva.py`): state acts resolved to their URN:NIR and read article by
  article from the Normattiva open data API (`POST .../atto/dettaglio-atto-urn`, with
  `!vig=<day>` for the wording in force on a day), never the whole act. Each article has its
  own timeline, so a "version" of an Italian provision is the day its text in force was read.
  One request at a time, cached per article. Regional laws, ministerial decrees, d.P.C.M.,
  circulars and annexes are recognised and reported as not covered.
- Neither source is the official text: the report says so for both and credits Normattiva
  (CC BY 4.0).

**Quotes.** Each quote goes through `src/agents/citation_verifier.py` (same normalisation and
thresholds as the Q&A): in the cited provision, then elsewhere in the act (EU law), then in
the earlier versions, newest first. Found only in an earlier wording: outdated, shown then and
now. Close to the text in force but with different words: altered, with the differing words.

**Lock file.** `build_lock(check)` gives `{"documento", "controllato_il", "data_documento",
"lingua", "dipendenze"}`; each dependency carries `fonte` (`eurlex` or `normattiva`; missing
means `eurlex`), `atto` (CELEX or URN:NIR), `nome`, `versione`, `consolidato_al`, `articolo`,
`chiave`, `lingua`, `impronta` (SHA-256 of the normalised text), `testo` and `riferimenti`.
The command line writes it as `*.norma-lock.json`.

**Re-check.** `recheck(lock, source)` reads each provision in force again and compares it with
the stored text: `invariato`, `cambiato`, `soppresso` or `non_disponibile` (mapped to the
dependency states `current`, `changed`, `removed`, `unavailable`). The document itself is not
needed.

**HTTP API and jobs** (`src/api/routers/documents.py`, `src/document_check/service.py`). The
check runs in a small thread pool away from the event loop (`DOCUMENT_CHECK_WORKERS`, 4), with
a time limit (`DOCUMENT_CHECK_TIMEOUT_SECONDS`, 120), at most `DOCUMENT_CHECK_CONCURRENCY_PER_ORG`
(2) jobs per organisation at once, at most `DOCUMENT_CHECKS_MAX_PER_ORG` (1,000) stored checks,
and caps on the file (10 MB), its text (400,000 characters) and the references (300). The
API re-check (`POST /checks/{id}/recheck`) and the weekly job
(`python -m src.pipeline --action recheck-documents`, `src/document_check/surveillance.py`)
use the same `service.apply_recheck`: a provision that changed for the first time sets
`needs_review` on the check and writes one alert for the document. The weekly job asks each
distinct provision once for all organisations, then works organisation by organisation in a
session with that tenant's context, and sends one digest email per user who has not turned it
off (`users.notify_document_changes`). Running it twice writes no second alert and sends no
second email (`serialize.next_state`, `review_notified_at`). No digest is sent without the
API's public address (`API_PUBLIC_URL` or `API_DOMAIN`), which the unsubscribe link needs; the
link carries a token signed with `APP_SECRET_KEY` (`src/auth/tokens.py`).

**What is stored and what is not.** The uploaded file is read in memory (the spill-to-disk
threshold of the multipart parser is raised above the largest body the route accepts) and neither the file nor its text is written to
disk, stored or logged. Stored, per check: file name, SHA-256 of the file, document date, check
and re-check times, language, status and counts, and the findings, each with at most 160
characters of the document around its reference, the quotes and the outcome
(`serialize.CONTEXT_LIMIT`). Stored, per provision cited: source, act, article, version, the
official text of the day of the check and its fingerprint, how the document cited it
(`cited_as`), its state and the last change found. The official texts the check downloads are
cached on disk (`NORMAAI_TEXT_CACHE`, `data/texts` in the container): copies of public texts,
nothing of a document.

## Documents tables and row-level security

Migration `009_document_checks` (`alembic/versions/009_document_checks.py`):

| Table / column | Holds | RLS |
|---|---|---|
| `document_checks` | one row per checked document: `org_id`, `client_id` (optional), `created_by`, `filename`, `document_sha256`, `document_date`, `lang`, `watch`, `status`, `needs_review`, `counts`, `findings` (JSONB), `checked_at`, `rechecked_at`, `review_notified_at` | enabled and forced: `document_checks_org_isolation` on `org_id`, `document_checks_org_insert` for INSERT |
| `document_dependencies` | the provisions each check relies on: `check_id`, `org_id`, `source`, `act`, `name`, `article`, `key`, `lang`, `version`, `as_of`, `fingerprint`, `official_text`, `cited_as`, `state`, `changed_at`, `checked_at`, `change` | the same two policies on `org_id` |
| `system_state` | key-value state that belongs to no tenant (the outcome of the nightly freshness check) | none, like `regulations` |
| `users.notify_document_changes` | the digest email on or off, default on | `users` has no RLS (ADR-2) |
| `alerts.document_check_id` | the check a surveillance alert is about; such an alert may have no client | the `alerts` policies of 007 are replaced: an alert is visible through its client or through its document check, when either belongs to the organisation |

Deleting a check deletes its dependencies and alerts (`ON DELETE CASCADE`); deleting a client
or an organisation deletes its checks. The GDPR export gives the checks and their
dependencies (without the official text of the law), and the erasure deletes them
(`src/api/routers/gdpr.py`). The downgrade puts the 007 alert policies back and
deletes the alerts that have no client. As with every tenant table, the policies bite only
when the app connects as a non-superuser role (ADR-2).

## Module Boundaries

| Module | Responsibility | Dependencies |
|--------|---------------|-------------|
| `src/api/` | HTTP routing, middleware, SSE formatting | FastAPI, auth |
| `src/agents/` | LangGraph orchestration, LLM calls, citation verifier, CoVe, SNC | LangGraph, LLM providers |
| `src/document_check/` | Document check: extraction, official texts, statuses, lock file, re-check, report, storage, surveillance | `src/agents/citation_verifier.py`, `src/crawler/eurlex`, httpx |
| `src/auth/` | JWT, roles, invites, signed tokens, brute-force protection | Redis, cryptography |
| `src/crawler/` | EUR-Lex SPARQL and CELLAR (`eurlex/`); old Normattiva client and URN tools (`normattiva/`, its endpoints are blocked) | httpx, SPARQLWrapper |
| `src/nlp/` | Chunking, embedding, indexing, named-article lookup, reranker | fastembed, Qdrant, onnxruntime |
| `src/db/` | SQLAlchemy models, async engine, RLS context | SQLAlchemy, asyncpg |
| `src/` | Config, cache, quotas, audit log, email, pipeline, resilience, observability | Pydantic, Redis, Resend, OTel |

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
                    │  Role / staff check      │
                    │  (route by route)        │
                    └────────┬────────────────┘
                             │
                    ┌────────▼────────────────┐
                    │  Prompt-injection         │
                    │  telemetry (logs only)    │
                    └────────┬────────────────┘
                             │
                    ┌────────▼────────────────┐
                    │  org_id filter + RLS      │
                    │  set_config per txn       │
                    └────────┬────────────────┘
                             │
                    ┌────────▼────────────────┐
                    │  Business Logic           │
                    └──────────────────────────┘
```

- **Rate limits** are per route (`@limiter.limit`); the auth routes and the unsubscribe link
  count per client IP behind the trusted proxy, the others per user when a token is sent and
  per IP otherwise (`src/api/rate_limit.py`).
- **Roles.** `require_role("admin")` guards invites, GDPR export and erasure and
  `/api/v1/metrics`; `require_staff` (`STAFF_EMAILS`) guards the corpus crawl. The `viewer`
  role is refused only on the routes of the documents API that check, re-check or delete;
  on every other route a viewer can do what a member can.
- **Prompt injection.** `src/agents/sanitization.py` only logs suspicious phrasing; it does
  not change the input. What limits the damage is structural: a fixed instruction at the top
  of every agent prompt to treat the passages, the profile and the question as data, and,
  for Q&A answers, the citation verifier.

## Running Tests

```bash
# Targeted runs
python -m pytest tests/test_citation_verifier.py tests/test_document_check.py -q
python -m pytest tests/test_documents_router.py tests/test_migration_009.py -q

# How many tests there are today
python -m pytest --collect-only -q | tail -1

# Full suite with the coverage floor CI enforces (84 %, .github/workflows/ci.yml);
# slow on a laptop: run_tests.ps1 runs it tier by tier
python -m pytest tests/ --cov=src --cov-fail-under=84
```
