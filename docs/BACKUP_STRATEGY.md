# NormaAI — Backup & Disaster Recovery

> Obiettivi: **RPO 24h** (max 1 giorno di dati persi) · **RTO 1h** (ripristino entro 1 ora).
> Adeguati alla fase pilot; rivedere a RPO 15min/RTO 30min con i primi contratti enterprise
> (i questionari vendor lo chiedono sempre).

## Cosa va salvato (e cosa no)

| Dato | Dove | Criticità | Strategia |
|---|---|---|---|
| PostgreSQL (org, utenti, leads, assessments, conversations, audit) | volume `postgres_data` | **CRITICA — unica fonte non ricostruibile** | `pg_dump` giornaliero + retention 30gg |
| Qdrant (vettori normativi) | volume `qdrant_data` | Bassa — ricostruibile con `python -m src.pipeline seed` (~min/ore) | snapshot settimanale opzionale, oppure nulla |
| Redis (cache, blacklist, lockout) | volume `redis_data` | Nessuna — effimero by design | nessun backup |
| Chiavi JWT + `.env` | filesystem | Alta (segreti) | copia manuale cifrata offline (password manager / disco cifrato), MAI nel repo |
| Codice | GitHub remoto | — | già versionato |

## Backup giornaliero Postgres

Script: [`scripts/backup_postgres.ps1`](../scripts/backup_postgres.ps1)
(compresso `.dump` formato custom, retention 30 giorni, verifica integrità).

Pianificazione (Windows Task Scheduler, ore 02:00):

```powershell
$action = New-ScheduledTaskAction -Execute 'pwsh.exe' `
  -Argument '-NoProfile -File "C:\path\to\normaai\scripts\backup_postgres.ps1"'
$trigger = New-ScheduledTaskTrigger -Daily -At 02:00
Register-ScheduledTask -TaskName "NormaAI Postgres Backup" -Action $action -Trigger $trigger
```

Su server Linux (Hetzner, G10): cron `0 2 * * *` con l'equivalente bash in coda allo script.

**Off-site**: la directory `backups/` è locale. Copiare almeno settimanalmente su
storage esterno (Hetzner Storage Box / S3 / Backblaze B2). Un backup sulla stessa
macchina del DB protegge dai bug, non dai disastri.

## Restore

```powershell
# 1. Ferma l'app (evita scritture durante il restore)
docker compose stop app

# 2. Restore (sovrascrive il DB!)
docker exec -i normaai-postgres pg_restore -U normaai -d normaai --clean --if-exists < backups\normaai_YYYYMMDD_HHmmss.dump

# 3. Riallinea le migrazioni e riparti
poetry run alembic upgrade head
docker compose up -d app
curl http://localhost:8000/readyz
```

Qdrant dopo un disastro totale: `python -m src.pipeline seed` (ricostruisce dai crawler).

## Test di restore (mensile — obbligatorio)

Un backup non testato non è un backup:

```powershell
# Ripristina in un DB temporaneo e conta le righe chiave
docker exec normaai-postgres createdb -U normaai normaai_restore_test
docker exec -i normaai-postgres pg_restore -U normaai -d normaai_restore_test < backups\<ultimo>.dump
docker exec normaai-postgres psql -U normaai -d normaai_restore_test -c "SELECT count(*) FROM organizations; SELECT count(*) FROM leads;"
docker exec normaai-postgres dropdb -U normaai normaai_restore_test
```

Annotare l'esito nel post-mortem log del [RUNBOOK](RUNBOOK.md).
