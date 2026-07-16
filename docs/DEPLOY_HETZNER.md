# Deploy backend su Hetzner (G10) - guida operativa

> Obiettivo: `api.normaai.org` live con TLS, in ~1 ora. Prerequisiti: account
> Hetzner Cloud, dominio `normaai.org` su Cloudflare, repo su GitHub.
> Tutto il materiale è già nel repo: `docker-compose.prod.yml`, `infra/Caddyfile`,
> `scripts/backup_postgres.sh`. In caso di problemi: [RUNBOOK.md](RUNBOOK.md).

## 1. Server (5 min)

Hetzner Cloud → Create Server:
- **CX22** (2 vCPU / 4 GB - basta per il pilot; l'app ha limit 4G ma i servizi
  insieme stanno in ~3 GB con swap), immagine **Ubuntu 24.04**, location **Falkenstein/Norimberga** (data residency DE).
- SSH key: aggiungi la tua chiave pubblica (mai password).
- Firewall Hetzner (o `ufw`): in ingresso solo **22, 80, 443**.

## 2. DNS (2 min)

Su Cloudflare, record **A**: `api.normaai.org` → IP del server, **proxy OFF
(grigio/DNS-only)** - Caddy fa Let's Encrypt da solo; il proxy arancione
interferirebbe con la challenge. (Il sito su Vercel resta com'è.)

## 3. Bootstrap server (10 min)

```bash
ssh root@<IP>

# Docker + compose plugin
curl -fsSL https://get.docker.com | sh

# Swap 2G (cuscino per i picchi di embedding)
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# Aggiornamenti di sicurezza automatici
apt-get update && apt-get install -y unattended-upgrades
dpkg-reconfigure -f noninteractive unattended-upgrades

# Codice
mkdir -p /opt && cd /opt
git clone https://github.com/Dan23RR/NormaAI.git normaai
cd normaai
```

## 4. Configurazione produzione (15 min)

```bash
cp .env.example .env
nano .env
```

Valori da impostare (gli altri default vanno bene):

| Variabile | Valore |
|---|---|
| `APP_ENV` | `production` |
| `APP_SECRET_KEY` | nuovo: `python3 -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `POSTGRES_PASSWORD` | nuovo, robusto (entra anche in `DATABASE_URL`) |
| `DATABASE_URL` | `postgresql+asyncpg://normaai:<password>@postgres:5432/normaai` (ruolo owner: lo usano solo migrazioni + seed, che richiedono i privilegi DDL) |
| `APP_DB_PASSWORD` | password del ruolo applicativo **non-superuser** `normaai_app` (l'overlay RLS la usa per la `DATABASE_URL` dell'app a runtime) |
| `QDRANT_HOST` / `REDIS_URL` | `qdrant` / `redis://redis:6379/0` (nomi servizio docker) |
| `GOOGLE_API_KEY` (o `ANTHROPIC_API_KEY`) | chiave di produzione |
| `CORS_ORIGINS` | `https://normaai-psi.vercel.app,https://normaai.org,https://www.normaai.org` |
| `NORMAAI_PUBLIC_URL` | `https://normaai-psi.vercel.app` (poi `https://normaai.org` quando il dominio è live) |
| `RESEND_API_KEY` | chiave Resend (email transazionali: consegna del Codex) |
| `GRAFANA_PASSWORD`, `PROMETHEUS_BEARER_TOKEN` | nuovi |
| `API_DOMAIN` | `api.normaai.org` |
| `ACME_EMAIL` | `info@normaai.org` |

**⚠️ Ruolo DB non-superuser (OBBLIGATORIO per il multi-tenant)**: PostgreSQL
**ignora le policy RLS** per i superuser e i proprietari di tabella, anche sotto
`FORCE ROW LEVEL SECURITY`. Se l'app si connette come `normaai` (owner),
l'isolamento multi-tenant è **inerte** (un tenant può leggere i dati di un altro).
L'app DEVE girare come ruolo non-superuser `normaai_app`, che si attiva con
l'**overlay RLS** (`docker-compose.rls.yml`, vedi §5).

Procedura completa, creazione del ruolo (`scripts/setup_app_role.sql`) e gate di
validazione: **[DEPLOY_READINESS.md §2](DEPLOY_READINESS.md)**. In sintesi: crea
`normaai_app`, imposta `APP_DB_PASSWORD`, e prima di mettere un **secondo tenant
reale** esegui `python scripts/validate_rls_two_tenant.py` (deve dare PASSED) con
`rolsuper | rolbypassrls = f | f`. **In produzione l'app si rifiuta di avviarsi**
se il ruolo connesso è superuser/bypassrls (fail-fast in `lifespan`), quindi
l'overlay non è opzionale.

Chiavi JWT di **produzione** (mai riusare quelle di sviluppo):

```bash
openssl genrsa -out jwt_private.pem 2048
openssl rsa -in jwt_private.pem -pubout -out jwt_public.pem
chmod 600 jwt_private.pem
```

## 5. Avvio (10 min)

```bash
# 1) Migrazioni + seed come ruolo OWNER. Sono comandi CLI one-shot (run --rm):
#    NON avviano il server, quindi il fail-fast del lifespan non scatta. Il seed
#    scarica da EUR-Lex: minuti.
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d postgres qdrant redis
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm app alembic upgrade head
# crea il ruolo non-superuser normaai_app (+ policy mancanti). Passa la STESSA
# password che hai messo in APP_DB_PASSWORD nel .env (:'app_pw' la quota da solo):
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
  psql -U normaai -d normaai -v app_pw="<APP_DB_PASSWORD>" < scripts/setup_app_role.sql
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm app python -m src.pipeline --action seed

# 2) Avvia l'app CON l'overlay RLS: gira come normaai_app (RLS attiva e applicata).
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.rls.yml up -d --build
```

Verifica:

```bash
curl https://api.normaai.org/health     # 200 {"status":"ok",...}
curl https://api.normaai.org/readyz     # 200 ready (503 finché qdrant/llm/corpus non sono pronti)
curl https://api.normaai.org/api/v1/stats   # qdrant.points_count > 0 = corpus seedato davvero
# Gate RLS (PRIMA di un secondo tenant): il ruolo app deve essere f | f
docker compose exec -T postgres psql -U normaai -d normaai -c \
  "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname='normaai_app';"
python scripts/validate_rls_two_tenant.py   # deve dare PASSED
```

## 6. Aggancia il frontend (5 min)

Su Vercel → Project → Settings → Environment Variables:
- `NEXT_PUBLIC_API_URL` = `https://api.normaai.org` → **Redeploy**.

Da quel momento il form lead usa il backend completo (HMAC, Postgres,
suppression list); la route serverless `/api/leads` resta come fallback.

## 7. Backup + cron (5 min)

```bash
chmod +x scripts/backup_postgres.sh
crontab -e
# aggiungi:
0 2 * * * /opt/normaai/scripts/backup_postgres.sh >> /var/log/normaai-backup.log 2>&1
```

Copia off-site settimanale: vedi [BACKUP_STRATEGY.md](BACKUP_STRATEGY.md)
(Hetzner Storage Box, `rclone` o `scp` dei file in `backups/`).

## 8. Smoke finale

```powershell
# dal laptop
pwsh scripts/verify_live_site.ps1                     # sito Vercel
curl https://api.normaai.org/api/v1/stats              # backend
```

Registra l'esito nel post-mortem log del [RUNBOOK](RUNBOOK.md). Fine G10.

## Aggiornamenti successivi

```bash
cd /opt/normaai && git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.rls.yml up -d --build app
docker compose exec app alembic upgrade head
```

Rollback: `git checkout <tag-precedente>` + stesso comando di build.
