# NormaAI - Runbook operativo

> Procedure per incidenti e operazioni ricorrenti. Pubblico: Daniel (founder-operator)
> e qualsiasi agente LLM in co-work. Aggiornare a ogni incidente reale (post-mortem in fondo).

## 0. Vista d'insieme

```
Vercel (frontend, fra1) ──browser, CORS──▶ api.normaai.org (Caddy → FastAPI, Docker)
                                              ├── PostgreSQL 16 (RLS multi-tenant)
                                              ├── Qdrant v1.20 (hybrid search, collection eu_regulations_e5)
                                              ├── Redis 7 (cache + blacklist + lockout)
                                              └── Ollama Qwen (opzionale, local LLM)
Observability: Prometheus :9090 · Grafana :3001 · Jaeger :16686
```

Il browser chiama l'API all'indirizzo di `NEXT_PUBLIC_API_BASE_URL` (variabile del progetto
Vercel), senza rewrite. Server nuovo e messa in produzione: [DEPLOY_CHECKLIST.md](DEPLOY_CHECKLIST.md).

Sul server il `.env` contiene `COMPOSE_FILE` (file base, prod e RLS): `docker compose` senza `-f`
usa i file di produzione. L'app si collega come `normaai_app` e nel suo container la password
del proprietario dello schema (`POSTGRES_PASSWORD`, che il `.env` tiene per i servizi `postgres`
e `migrate`) è vuota: `docker-compose.prod.yml` la azzera. Le migrazioni girano come
proprietario nel servizio usa e getta `migrate`: `docker compose run --rm migrate`. L'immagine
dell'app è `NORMAAI_IMAGE` del `.env` (quella costruita dalla CI e scaricata da GHCR per
digest, che `scripts/deploy.sh` scrive a ogni deploy), oppure `normaai-app:local` se il `.env`
non la indica. In locale `docker compose` usa il file base e l'override di sviluppo.

Comandi base:

```powershell
docker compose ps                      # stato servizi
docker compose logs -f app             # log applicazione
docker compose restart app             # riavvio app (ultima risorsa, vedi §2)
curl http://localhost:8000/health      # liveness (in locale; sul server vedi sotto)
curl http://localhost:8000/readyz      # readiness (503 = dipendenze giù)
```

Sul server l'app non pubblica la porta 8000: `docker exec normaai-app curl -fsS http://localhost:8000/readyz`
oppure, da fuori, `curl https://api.normaai.org/readyz`. Prometheus, Grafana e Jaeger non partono
con il deploy: `docker compose up -d prometheus grafana jaeger`, poi tunnel SSH
(`ssh -L 3001:localhost:3001 -L 9090:localhost:9090 <utente>@<server>`). Prometheus legge il
token per `/api/v1/metrics/prometheus` dal secret di compose `prometheus_bearer_token`, che
compose crea da `PROMETHEUS_BEARER_TOKEN` del `.env` (`infra/prometheus.yml`, `credentials_file`).

## 1. Diagnosi rapida (primi 5 minuti)

Chi avvisa:

- il controllo esterno `.github/workflows/uptime.yml`, ogni 30 minuti dai runner di GitHub (sito,
  certificati e, con la variabile `API_BASE_URL` del repository, `/readyz`, CORS del login e DNS
  dell'API). Un controllo fallito fa fallire il run e apre o aggiorna una issue «Uptime: <host>»,
  che il primo run riuscito chiude. `/readyz` chiede al provider del modello se accetta la
  chiave e il modello configurati (§4): una chiave revocata o un modello inesistente lo fanno
  diventare rosso, senza riavviare l'app. GitHub sospende lo schedule dopo 60 giorni senza
  attività nel repository (con una email prima): riattivalo dalla scheda Actions;
- Sentry, con `SENTRY_DSN` nel `.env` (l'immagine ha l'SDK): le eccezioni e ogni riga di log
  ERROR dell'API e dei job di cron, compreso il rifiuto della chiave alla partenza. Gli eventi
  non portano il corpo delle richieste né le variabili locali. Sentry manda una email per ogni
  nuovo problema, secondo le regole di avviso del progetto;
- una email a `OPS_ALERT_EMAIL` (con `RESEND_API_KEY`) quando falliscono un job di cron
  (`check-freshness`, `recheck-documents`), il backup notturno o il test di ripristino mensile
  (`src/ops_alerts.py`). Gli script di backup girano sull'host e mandano l'avviso attraverso il
  container dell'app: se l'app è spenta l'avviso non parte (lo dice il log), ma allora il
  controllo esterno vede l'API giù. Un backup che smette del tutto di partire (cron rotto) lo
  vede solo `BACKUP_HEARTBEAT_URL` (BACKUP_STRATEGY.md §4).

Grafana e Prometheus servono a capire il guasto, non ad avvisare: nessun Alertmanager è
collegato, quindi le regole di `infra/prometheus.rules.yml` si vedono solo aprendo Prometheus, e
non girano affatto se lo stack di osservabilità non è avviato. Le metriche che leggono sono
registrate dall'app: richieste per rotta e stato, latenze, stato ed esiti dei circuit breaker.

1. `curl /health` → se non risponde: processo/container morto → §2.
2. `curl /readyz` → 503: guarda `checks` nel body (qdrant/llm/corpus down) e, per il modello, il
   motivo in `llm` → §3/§4.
3. Grafana → dashboard "NormaAI - Health": 5xx rate, circuit breakers, p95.
4. Prometheus → http://localhost:9090/alerts per le regole in stato di allarme (nessuno le
   riceve per email: vedi sopra).
5. `docker compose logs --tail 100 app` → cerca `circuit_open`, `*_failed`, tracebacks.

## 2. App down (health check rosso)

```powershell
docker compose ps                       # exited? unhealthy?
docker compose logs --tail 200 app
docker compose up -d app                # restart pulito
```

- Crash loop all'avvio → quasi sempre config: `validate_settings_or_exit` stampa
  il motivo (APP_SECRET_KEY corta, chiavi JWT mancanti in production, `LLM_PROVIDER` sconosciuto,
  con `LLM_PROVIDER=mistral` chiave Mistral assente o URL non https). Per Gemini, Anthropic e
  OpenRouter la chiave assente non ferma l'avvio: `/readyz` risponde `llm: down` con
  `"llm": "missing_key"`.
  `FATAL: the app connects to PostgreSQL as a SUPERUSER` = app avviata senza l'overlay RLS
  (per esempio `docker compose -f docker-compose.yml up -d app`): rilancia `docker compose up -d app`
  con il `COMPOSE_FILE` del `.env`.
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
- Collection corrotta/persa → ripristina l'ultimo snapshot (sotto): con multilingual-e5-large il seed
  sulla CPU del server dura ore. Il re-seed resta possibile: `python -m src.pipeline --action seed`
  (sul server dentro `docker compose run --rm app`).
  Il seed è idempotente (id dei chunk deterministici, re-index per atto/lingua): rilanciarlo non duplica nulla.
  Un singolo atto o framework: `--acts 32022L2464` / `--acts DORA`; una sola lingua: `--lang IT`.
- **Snapshot delle collection** (backup e trasferimento su un server nuovo). Sul server Qdrant
  risponde su `127.0.0.1:6333`. Uno snapshot per collection:
  ```bash
  curl -fsS -X POST "http://127.0.0.1:6333/collections/eu_regulations_e5/snapshots?wait=true"   # "name" del file
  curl -fsS -o eu_regulations_e5.snapshot "http://127.0.0.1:6333/collections/eu_regulations_e5/snapshots/<name>"
  ```
  Ripristino, che sostituisce la collection se esiste già:
  ```bash
  curl -fsS -X POST "http://127.0.0.1:6333/collections/eu_regulations_e5/snapshots/upload?priority=snapshot&wait=true" \
    -F "snapshot=@eu_regulations_e5.snapshot"
  ```
  Su un server nuovo lo fa il passo 7 di `scripts/bootstrap_hetzner.sh` con i file
  `/opt/normaai-snapshots/<collection>.snapshot`. Lo snapshot porta con sé vettori, indici, IDF e
  il punto dei metadati (`corpus_as_of`). Si ripristina sulla stessa versione di Qdrant; tra
  minor diverse vale la regola delle minor consecutive di «Aggiornare Qdrant» qui sotto. Rifallo
  dopo ogni aggiornamento del corpus e tienine una copia fuori dal server.
- **Cambiare modello di ricerca** (e5 o mpnet, una collection per modello, tutte e due negli
  snapshot): `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION` e `QDRANT_COLLECTION` nel `.env`, poi build
  dell'immagine e riavvio come al §9. Valori e memoria in [DEPLOY_CHECKLIST.md](DEPLOY_CHECKLIST.md) §1.
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

## 4. LLM provider down (Gemini/Anthropic/Mistral)

Sintomi: `/readyz` con `llm: down`, alert `LLMCircuitOpen` o `LLMErrorRateHigh`, 503 sulle
risposte intelligence, problemi `llm_probe_failed` o `llm_*_error` in Sentry.

Il motivo è in `"llm"` di `/readyz` (`src/llm_probe.py`: una richiesta all'endpoint del modello
configurato, con la chiave in un'intestazione, risposta tenuta 5 minuti, 1 dopo un errore; con
`APP_ENV=testing` non parte nulla):

| `llm` | Vuol dire | Cosa fare |
|---|---|---|
| `missing_key` | nessuna chiave per `LLM_PROVIDER` | chiave nel `.env`, poi `docker compose up -d app` |
| `key_rejected` | il provider rifiuta la chiave (revocata, sbagliata) | nuova chiave nella console del provider, poi come sopra |
| `model_not_found` | il modello configurato non esiste per quella chiave | `ANTHROPIC_MODEL` (o `GEMINI_MODEL`, `MISTRAL_MODEL`) nel `.env` |
| `no_credit` | credito finito (solo OpenRouter lo dice qui) | ricarica o alza il limite |
| `rate_limited`, `provider_error`, `unreachable` | il provider risponde 429 o 5xx, o non risponde | status page del provider |
| `circuit_open` | cinque risposte fallite di fila | i log e Sentry dicono perché |

Anthropic, Google e Mistral non dicono il credito rimasto finché una generazione non viene
rifiutata: il credito finito si vede come risposte fallite (Sentry, poi `circuit_open`). Il
limite di spesa impostato nella console del provider manda il suo avviso prima.

1. Status page del provider (Google, Anthropic o Mistral, secondo `LLM_PROVIDER`).
2. Quota/billing: errore `429`/`RESOURCE_EXHAUSTED` nei log = quota esaurita, non outage.
3. Failover manuale di provider (richiede chiave dell'altro provider in `.env`):
   ```powershell
   # in .env:  LLM_PROVIDER=anthropic   (o gemini, o mistral)
   docker compose up -d app
   ```
   Anthropic con `claude-haiku-5-5` (predefinito anche nel codice) è l'unica configurazione
   misurata (docs/MODELS.md §2.3).
4. Il circuito si richiude da solo (recovery 60s) quando il provider torna.
5. Cambiare provider cambia dove vengono elaborate le domande degli utenti: Mistral, con
   `MISTRAL_BASE_URL` predefinito, sull'endpoint regionale UE; Google e Anthropic sono
   società statunitensi. Mistral non è ancora misurato sul golden set (docs/MODELS.md §5.1).
   In produzione con `LLM_PROVIDER=mistral` l'app non parte senza `MISTRAL_API_KEY` o con un
   `MISTRAL_BASE_URL` non https.

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
- **Limiti di frequenza**: contati nella memoria di ogni processo finché Redis non risponde
  (avviso `rate_limit_storage_unreachable` all'avvio, «falling back to in-memory» di slowapi
  durante l'esercizio); con più worker ognuno conta per conto suo. Tornano condivisi da soli.
- Cache: degrado di latenza, nessun errore funzionale.

```powershell
docker compose restart redis   # recovery cache: immediato; nessun dato critico in Redis
```

## 7. Deliverability email (Resend)

- Le email transazionali (consegna del Codex ai lead) passano da Resend.
- Bounce/spam rate su → controlla la dashboard Resend e la configurazione
  DKIM/SPF del dominio mittente.
- Le email di oggi (consegna del Codex, verifica dell'indirizzo) sono transazionali: non
  hanno un'intestazione List-Unsubscribe né un footer privacy, e `src/email_client.py` non ne
  aggiunge. Un'email periodica (per esempio un riepilogo degli avvisi) deve dare un modo di
  smettere di riceverla prima di partire.

## 8. Incidente di sicurezza

1. **Contieni**: revoca il segreto compromesso (vedi [SECURITY.md](../SECURITY.md) § Key Rotation).
   Per JWT: ruota la coppia RSA (`data/jwt_private.pem`, `data/jwt_public.pem`) e riavvia
   l'app → i token firmati con la vecchia chiave non sono più accettati;
   per chiudere subito tutte le sessioni di un utente: `python scripts/staff.py end-sessions
   <email>` (§11); per togliergli l'accesso, un amministratore della sua organizzazione lo
   rimuove (`DELETE /api/v1/auth/members/{id}`).
2. **Valuta GDPR**: se dati personali coinvolti → valuta notifica Garante entro
   **72h** (Art. 33) e clienti entro **48h** (impegno DPA §7).
3. **Documenta**: timeline in `docs/incidents/YYYY-MM-DD-<slug>.md`.
4. **Post-mortem**: aggiungi la lezione in fondo a questo runbook.

## 9. Deploy / rollback

- **Deploy backend**: `.github/workflows/deploy.yml` parte solo dopo che la CI («NormaAI CI») è
  riuscita su un push di `main`, e installa esattamente il commit che la CI ha provato, finché è
  ancora la testa di `main` (se `main` è andato avanti, lo installa la CI del commit nuovo):
  1. costruisce l'immagine di quel commit, con il modello di ricerca del server (variabile
     `DEPLOY_EMBEDDING_MODEL`, predefinito multilingual-e5-large), e la pubblica su GHCR come
     `ghcr.io/<owner>/<repo>:deploy-<sha>`;
  2. via SSH come utente `deploy` (non root), la cui chiave può lanciare solo
     `scripts/deploy.sh`: il commit deve stare su `origin/main`, l'immagine viene scaricata per
     digest mentre la vecchia app risponde, e rifiutata se le sue etichette non nominano il commit
     e l'`EMBEDDING_MODEL` del `.env`; migrazioni come proprietario (`docker compose run --rm
     migrate`); poi viene ricreata la sola app e si aspetta il suo healthcheck. Se la nuova app non
     diventa healthy torna l'immagine precedente, con il checkout precedente, e il job fallisce;
  3. aspetta che `https://api.normaai.org/health` riporti il commit.

  L'API resta giù solo per il riavvio dell'app, cioè il caricamento del modello (31-90 s con e5):
  sul server non si costruisce più nulla. Senza i segreti `DEPLOY_*`
  ([DEPLOY_CHECKLIST.md](DEPLOY_CHECKLIST.md) passo 6) il workflow salta con un avviso.
- **Rollback**: Actions → Deploy → Run workflow da `main`, con `sha` = un commit di `main` su cui
  la CI è riuscita (l'immagine viene ricostruita da quel commit). Oppure sul server, come `deploy`:

```bash
# un commit di main, con l'immagine costruita qui (fallback, scarica di nuovo il modello)
sudo -u deploy -H bash /opt/normaai/scripts/deploy.sh <sha-di-40-caratteri> build
# un'immagine già su GHCR, per digest (quella precedente è nel .env prima del deploy)
sudo -u deploy -H bash /opt/normaai/scripts/deploy.sh <sha> ghcr.io/<owner>/<repo>@sha256:<digest>
curl -fsS https://api.normaai.org/health          # "version" = i primi 7 caratteri dello SHA

# Migrazioni: rollback dell'ultima (ATTENZIONE: vedi nota)
docker compose run --rm migrate alembic downgrade -1
```

- Non lanciare `docker compose build app` quando `NORMAAI_IMAGE` nel `.env` è un digest di GHCR:
  compose proverebbe a dare quel nome alla build. La build sul server passa da
  `scripts/deploy.sh <sha> build`, che usa il nome `normaai-app:<sha>`.

- Le migrazioni 001-008 sono additive; il downgrade di 002 (RLS) **disabilita
  l'isolamento multi-tenant** - mai in produzione con più di 1 org.
- Frontend: Vercel → Deployments → "Promote to Production" sul deploy precedente (rollback 1-click).

## 10. Manutenzione ricorrente

| Cadenza | Azione |
|---|---|
| Giornaliera (auto) | Backup alle 02:00 (`bash scripts/backup.sh`, cron installato dal bootstrap, log in `/var/log/normaai-backup.log`): dump Postgres, snapshot di ogni collection Qdrant e `.env`, cifrati con restic e inviati a `RESTIC_REPOSITORY`; senza restic solo un dump in chiaro sul disco del server, con un avviso a ogni run ([BACKUP_STRATEGY.md](BACKUP_STRATEGY.md)). Un run fallito avvisa l'operatore (§1). In locale `scripts/backup_postgres.ps1` |
| Giornaliera (auto) | 03:30, `python -m src.pipeline --action check-freshness` dentro il container dell'app (cron del bootstrap, log in `/var/log/normaai-jobs.log`): confronta la versione consolidata indicizzata di ogni atto con l'ultima di CELLAR |
| Ogni 30 minuti (auto) | Controllo esterno `.github/workflows/uptime.yml` (§1) |
| Settimanale (auto) | Lunedì alle 04:00, `python -m src.pipeline --action recheck-documents` dentro il container dell'app (cron del bootstrap, log in `/var/log/normaai-jobs.log`): ricontrolla le disposizioni dei documenti sorvegliati, scrive gli avvisi e invia il riepilogo |
| Settimanale | Controlla Dependabot PR + alert CodeQL/Trivy in GitHub Security tab |
| Settimanale (a mano), o quando `check-freshness` segnala atti superati | Aggiornamento del corpus: `docker compose run --rm app python -m src.pipeline --action update` (lo scheduler interno è spento, `ACQUISITION_SCHEDULER_ENABLED=false`). Confronta il testo di ogni atto seguito (`TRACKED_ACTS`), in EN e IT, con quello indicizzato, re-indicizza solo i testi cambiati e scrive nella collection la data del corpus, quella che vedono gli utenti; non aggiunge atti fuori dall'elenco. Con e5 ogni testo cambiato richiede minuti di CPU. Poi un nuovo snapshot della collection (§3) |
| Mensile (auto) | Test di ripristino il 1° del mese alle 05:00 (`bash /opt/normaai/scripts/restore_test.sh`, riga di cron di `backup.sh --install-cron`, log in `/var/log/normaai-restore-test.log`): carica l'ultima copia in un Postgres e in un Qdrant usa e getta e controlla tabelle e punti; se fallisce avvisa l'operatore. Esito nel post-mortem log qui sotto |
| Trimestrale | Esercitazione di ripristino dal portatile, con le sole chiavi del password manager: `bash scripts/restore_drill.sh` ([BACKUP_STRATEGY.md](BACKUP_STRATEGY.md) §6.4); rotazione chiavi (SECURITY.md § Key Rotation) + review accessi |

## 11. Account e accessi

Tutti i comandi girano sul server dentro il container dell'app, per esempio
`docker exec normaai-app python scripts/staff.py list` (oppure con
`docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm app ...`). La tabella
`users` non ha RLS, quindi va bene anche il ruolo `normaai_app`. Ogni processo dell'API vede
una modifica entro `AUTH_ACCOUNT_CACHE_SECONDS` (30 s).

- **Staff** (crawl del corpus, inviti per nuove organizzazioni). È il flag `users.is_staff`,
  che solo questo script imposta, e vale solo con l'email verificata. `STAFF_EMAILS` non è più
  letto: se resta nel `.env`, all'avvio c'è un avviso.
  ```bash
  python scripts/staff.py list
  python scripts/staff.py grant ops@normaai.org     # account attivo con email verificata
  python scripts/staff.py revoke ops@normaai.org
  ```
  Dopo la migrazione 010 nessuno è staff: chi lo era per `STAFF_EMAILS` va nominato di nuovo
  con `grant`. Un'email non verificata si sistema con il link di verifica o con un reset
  della password, che la verifica. L'invito di un amministratore di un'organizzazione non
  verifica l'indirizzo (solo quelli di `scripts/create_invite.py` e dello staff): prima di
  `grant` controlla l'organizzazione che `list` e `grant` mostrano.
- **Password dimenticata.** L'utente usa «Password dimenticata?» nella pagina di accesso
  (`/reset-password`): arriva un link valido `PASSWORD_RESET_TOKEN_TTL_MINUTES` (30 minuti),
  una volta sola, e al cambio si chiudono tutte le sue sessioni. Serve `RESEND_API_KEY`. Se
  l'email non arriva (spam, Resend non configurato), lo staff crea lo stesso link:
  ```bash
  python scripts/staff.py reset-password anna@studio.it          # stampa il link, una volta
  python scripts/staff.py reset-password anna@studio.it --send   # e lo spedisce
  ```
  Il link va consegnato solo alla persona, su un canale che sia suo. Nel database resta solo
  l'hash; un nuovo link annulla il precedente.
- **Chiudere tutte le sessioni** di un account (dispositivo perso, persona che lascia lo
  studio): `python scripts/staff.py end-sessions anna@studio.it`. Ogni token emesso fino a
  quel momento è rifiutato; l'utente accede di nuovo.
- **Membri.** Li gestisce un amministratore dell'organizzazione via API:
  `GET /api/v1/auth/members`, `PATCH /api/v1/auth/members/{id}` con `{"role": "viewer"}`,
  `DELETE /api/v1/auth/members/{id}`. L'ultimo amministratore attivo non si può né declassare
  né rimuovere (409). La rimozione cancella l'account e le sue conversazioni; clienti,
  controlli, report e inviti restano all'organizzazione. Il logout dal sito revoca la
  sessione anche sul server.
- **Review trimestrale degli accessi** (§10): `python scripts/staff.py list` e, per ogni
  organizzazione, `GET /api/v1/auth/members`.

## Post-mortem log

| Data | Incidente | Causa radice | Fix permanente |
|---|---|---|---|
| 2026-05-15 | Foundation deploy bloccato (domini ECONNREFUSED) | Custom domain mai puntato a Vercel | ADR-002; staging URL come fallback operativo |
| 2026-09 | Server di produzione cancellato; per circa sette settimane nessuno se ne accorge, e i backup spariscono con il server | Nessun controllo dall'esterno del server; backup solo locali, in chiaro, senza l'indice Qdrant | Controllo esterno `uptime.yml` con issue automatica; backup cifrati fuori dal server con restic e test di ripristino mensile (BACKUP_STRATEGY.md) |
| _(aggiungere qui)_ | | | |
