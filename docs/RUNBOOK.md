# NormaAI - Runbook operativo

> Procedure per incidenti e operazioni ricorrenti. Pubblico: Daniel (founder-operator)
> e qualsiasi agente LLM in co-work. Aggiornare a ogni incidente reale (post-mortem in fondo).

## 0. Vista d'insieme

```
Vercel (frontend, fra1) ──rewrite /api/v1──▶ api.normaai.org (FastAPI, Docker)
                                              ├── PostgreSQL 16 (RLS multi-tenant)
                                              ├── Qdrant v1.20 (hybrid search)
                                              ├── Redis 7 (cache + blacklist + lockout)
                                              └── Ollama Qwen (opzionale, local LLM)
Observability: Prometheus :9090 · Grafana :3001 · Jaeger :16686
```

Comandi base:

```powershell
docker compose ps                      # stato servizi
docker compose logs -f app             # log applicazione
docker compose restart app             # riavvio app (ultima risorsa, vedi §2)
curl http://localhost:8000/health      # liveness
curl http://localhost:8000/readyz      # readiness (503 = dipendenze giù)
```

## 1. Diagnosi rapida (primi 5 minuti)

1. `curl /health` → se non risponde: processo/container morto → §2.
2. `curl /readyz` → 503: guarda `checks` nel body (qdrant/llm down) → §3/§4.
3. Grafana → dashboard "NormaAI - Health": 5xx rate, circuit breakers, p95.
4. Prometheus → http://localhost:9090/alerts per alert attivi.
5. `docker compose logs --tail 100 app` → cerca `circuit_open`, `*_failed`, tracebacks.

## 2. App down (health check rosso)

```powershell
docker compose ps                       # exited? unhealthy?
docker compose logs --tail 200 app
docker compose up -d app                # restart pulito
```

- Crash loop all'avvio → quasi sempre config: `validate_settings_or_exit` stampa
  il motivo (APP_SECRET_KEY corta, chiavi JWT mancanti in production, LLM key assente).
- `pg_isready` fallisce → §5 Postgres.
- Dopo il restart verifica `/readyz` E fai un login di prova.

## 3. Qdrant down / retrieval degradato

Sintomi: `/readyz` 503 con `qdrant: down`, alert `QdrantCircuitOpen`, risposte Q&A vuote o rifiutate.

```powershell
curl http://localhost:6333/healthz
docker compose logs --tail 100 qdrant
docker compose restart qdrant
```

- Il circuit breaker qdrant si richiude da solo (recovery 30s) dopo che il servizio torna su.
- Collection corrotta/persa → re-seed: `python -m src.pipeline --action seed` (~minuti, usa EUR-Lex).
  Il seed è idempotente (id dei chunk deterministici, re-index per atto/lingua): rilanciarlo non duplica nulla.
  Un singolo atto o framework: `--acts 32022L2464` / `--acts DORA`; una sola lingua: `--lang IT`.
- Log di avvio `collection_sparse_modifier_missing` o `collection_embedding_model_mismatch` → la collection è
  stata creata con la vecchia configurazione (sparse senza IDF o altro modello di embedding): ricreala con
  `python -m src.pipeline --action seed --recreate`.
- `python -m src.pipeline --action stats` mostra `corpus.corpus_as_of` (data del seed) e gli atti indicizzati
  (CELEX, lingua, versione consolidata).
- Atti di modifica che citano articoli dell'atto modificato (per esempio «Article 2a» nell'art. 25 del
  regolamento (UE) 2020/852): dal 2026-10-27 il chunker dà a quei passaggi l'articolo dell'atto di modifica
  e registra l'articolo citato (`quoted_article`) e l'atto modificato (`amended_celex`); prima uscivano come
  "Art. ?" o come falsi articoli dell'atto di modifica. Una collection indicizzata prima si corregge senza
  riscaricare gli atti: `python scripts/relabel_quoted_articles.py` (prova, non scrive) e poi `--apply`,
  una volta per collection, con QDRANT_COLLECTION, EMBEDDING_MODEL ed EMBEDDING_DIMENSION di quella collection.
- I dati Qdrant sono **ricostruibili** dal crawl: non è una perdita dati permanente.
- **Aggiornare Qdrant.** Server (immagine in `docker-compose.yml`, `docker-compose.infra.yml` e nella CI)
  e `qdrant-client` (`pyproject.toml`) vanno alla stessa minor: il client avvisa se distano più di una.
  I dati su disco sono compatibili solo tra due minor consecutive, quindi un volume creato con una
  versione più vecchia passa da tutte le minor intermedie, una per volta. Dalla 1.16 alla 1.20:
  ```powershell
  docker compose stop qdrant
  docker volume ls | findstr qdrant_data          # il nome del volume, con il prefisso del progetto
  foreach ($v in "v1.17.1", "v1.18.3", "v1.19.2") {
    docker run -d --name qdrant-upgrade -p 127.0.0.1:6333:6333 -v <volume>:/qdrant/storage qdrant/qdrant:$v
    # aspetta che http://localhost:6333/healthz risponda e che i log non mostrino errori, poi:
    docker rm -f qdrant-upgrade
  }
  docker compose up -d qdrant                     # parte con l'immagine nuova
  ```
  In alternativa si ricrea la collection con il seed (`--recreate`). Un server nuovo parte vuoto e non
  ha questo problema.

## 4. LLM provider down (Gemini/Anthropic)

Sintomi: alert `LLMCircuitOpen` o `LLMErrorRateHigh`, 503 sulle risposte intelligence.

1. Status page provider (status.cloud.google.com / status.anthropic.com).
2. Quota/billing: errore `429`/`RESOURCE_EXHAUSTED` nei log = quota esaurita, non outage.
3. Failover manuale di provider (richiede chiave dell'altro provider in `.env`):
   ```powershell
   # in .env:  LLM_PROVIDER=anthropic   (o gemini)
   docker compose restart app
   ```
4. Il circuito si richiude da solo (recovery 60s) quando il provider torna.

## 5. Postgres down / corrotto

Sintomi: app crash-loop, errori `asyncpg` nei log, `pg_isready` fallisce.

```powershell
docker compose logs --tail 100 postgres
docker compose restart postgres
```

- Disco pieno → `docker system df`, libera spazio, restart.
- Corruzione → restore da backup: vedi [BACKUP_STRATEGY.md](BACKUP_STRATEGY.md) §Restore.
- **RLS gotcha**: query che tornano 0 righe inspiegabilmente = sessione senza
  `SET LOCAL app.current_org_id` (fail-closed corretto). Bug applicativo, non dati persi.

## 6. Redis down

Sintomi: alert `RedisCircuitOpen`, cache miss al 100%, lockout login non attivo.

Comportamento by design (non panicare):
- **Token blacklist: fail-closed in produzione** → token revocati restano negati,
  ma `is_blacklisted` può negare anche token validi → utenti sloggati. Atteso.
- **Brute-force lockout: fail-open** → nessun lockout durante l'outage (trade-off documentato SEC-03).
- Cache: degrado di latenza, nessun errore funzionale.

```powershell
docker compose restart redis   # recovery cache: immediato; nessun dato critico in Redis
```

## 7. Deliverability email (Resend)

- Le email transazionali (consegna del Codex ai lead) passano da Resend.
- Bounce/spam rate su → controlla la dashboard Resend e la configurazione
  DKIM/SPF del dominio mittente.
- Ogni email DEVE avere footer privacy + List-Unsubscribe (iniettati da
  `email_client` - se mancano nei log, indaga prima di inviare).

## 8. Incidente di sicurezza

1. **Contieni**: revoca il segreto compromesso (vedi [SECURITY.md](../SECURITY.md) § Key Rotation).
   Per JWT: ruota la coppia RSA → tutti gli access token muoiono in ≤15 min;
   per revoca immediata di un utente: blacklist via Redis.
2. **Valuta GDPR**: se dati personali coinvolti → valuta notifica Garante entro
   **72h** (Art. 33) e clienti entro **48h** (impegno DPA §7).
3. **Documenta**: timeline in `docs/incidents/YYYY-MM-DD-<slug>.md`.
4. **Post-mortem**: aggiungi la lezione in fondo a questo runbook.

## 9. Deploy / rollback

```powershell
# Deploy backend (Docker)
git pull
docker compose build app
docker compose up -d app
curl http://localhost:8000/readyz

# Rollback backend
git checkout <ultimo-tag-buono>
docker compose build app && docker compose up -d app

# Migrazioni
poetry run alembic upgrade head          # applica
poetry run alembic downgrade -1          # rollback ultima (ATTENZIONE: vedi nota)
```

- Le migrazioni 001-008 sono additive; il downgrade di 002 (RLS) **disabilita
  l'isolamento multi-tenant** - mai in produzione con più di 1 org.
- Frontend: Vercel → Deployments → "Promote to Production" sul deploy precedente (rollback 1-click).

## 10. Manutenzione ricorrente

| Cadenza | Azione |
|---|---|
| Giornaliera (auto) | Backup Postgres (`scripts/backup_postgres.ps1`, task scheduler) |
| Settimanale | Controlla Dependabot PR + alert CodeQL/Trivy in GitHub Security tab |
| Settimanale (auto) | Crawl EUR-Lex update (`python -m src.pipeline --action update --days-back 7`) |
| Mensile | Test di RESTORE del backup (un backup non testato non è un backup) |
| Trimestrale | Rotazione chiavi (SECURITY.md § Key Rotation) + review accessi |

## Post-mortem log

| Data | Incidente | Causa radice | Fix permanente |
|---|---|---|---|
| 2026-05-15 | Foundation deploy bloccato (domini ECONNREFUSED) | Custom domain mai puntato a Vercel | ADR-002; staging URL come fallback operativo |
| _(aggiungere qui)_ | | | |
