# Deploy backend su Hetzner (G10) — guida operativa

> Obiettivo: `api.normaai.org` live con TLS, in ~1 ora. Prerequisiti: account
> Hetzner Cloud, dominio `normaai.org` su Cloudflare, repo su GitHub.
> Tutto il materiale è già nel repo: `docker-compose.prod.yml`, `infra/Caddyfile`,
> `scripts/backup_postgres.sh`. In caso di problemi: [RUNBOOK.md](RUNBOOK.md).

## 1. Server (5 min)

Hetzner Cloud → Create Server:
- **CX22** (2 vCPU / 4 GB — basta per il pilot; l'app ha limit 4G ma i servizi
  insieme stanno in ~3 GB con swap), immagine **Ubuntu 24.04**, location **Falkenstein/Norimberga** (data residency DE).
- SSH key: aggiungi la tua chiave pubblica (mai password).
- Firewall Hetzner (o `ufw`): in ingresso solo **22, 80, 443**.

## 2. DNS (2 min)

Su Cloudflare, record **A**: `api.normaai.org` → IP del server, **proxy OFF
(grigio/DNS-only)** — Caddy fa Let's Encrypt da solo; il proxy arancione
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
git clone https://github.com/danielculotta/normaai.git normaai
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
| `DATABASE_URL` | `postgresql+asyncpg://normaai:<password>@postgres:5432/normaai` |
| `QDRANT_HOST` / `REDIS_URL` | `qdrant` / `redis://redis:6379/0` (nomi servizio docker) |
| `GOOGLE_API_KEY` (o `ANTHROPIC_API_KEY`) | chiave di produzione |
| `CORS_ORIGINS` | `https://normaai-psi.vercel.app,https://normaai.org,https://www.normaai.org` |
| `NORMAAI_PUBLIC_URL` | `https://normaai-psi.vercel.app` (poi `https://normaai.org` quando il dominio è live) |
| `RESEND_API_KEY`, `IMAP_*`, `TELEGRAM_*` | valori reali (come nel `.env` locale) |
| `GRAFANA_PASSWORD`, `PROMETHEUS_BEARER_TOKEN` | nuovi |
| `API_DOMAIN` | `api.normaai.org` |
| `ACME_EMAIL` | `info@normaai.org` |

**⚠️ Ruolo DB non-superuser (obbligatorio per il multi-tenant)**: PostgreSQL
**ignora le policy RLS** per i superuser e i proprietari di tabella. L'app NON deve
connettersi come `postgres`/owner. Crea un ruolo dedicato e forza la RLS:

```sql
CREATE ROLE normaai_app LOGIN PASSWORD '<password>';
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO normaai_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO normaai_app;
-- per ogni tabella tenant: forza RLS anche per l'owner
ALTER TABLE conversations FORCE ROW LEVEL SECURITY;  -- idem users, clients, assessments, alerts
```
Poi usa `normaai_app` (non `normaai`/superuser) nella `DATABASE_URL` dell'app.
Senza questo, l'isolamento multi-tenant collassa a livello DB.

Chiavi JWT di **produzione** (mai riusare quelle di sviluppo):

```bash
openssl genrsa -out jwt_private.pem 2048
openssl rsa -in jwt_private.pem -pubout -out jwt_public.pem
chmod 600 jwt_private.pem
```

## 5. Avvio (10 min)

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Migrazioni + seed knowledge base (il seed scarica da EUR-Lex: minuti)
docker compose exec app alembic upgrade head
docker compose exec app python -m src.pipeline seed
```

Verifica:

```bash
curl https://api.normaai.org/health     # 200 {"status":"ok",...}
curl https://api.normaai.org/readyz     # 200 ready (503 finché il seed non è completo)
```

## 6. Aggancia il frontend (5 min)

Su Vercel → Project → Settings → Environment Variables:
- `NEXT_PUBLIC_API_URL` = `https://api.normaai.org` → **Redeploy**.

Da quel momento il form lead usa il backend completo (HMAC, Postgres,
suppression list); la route serverless `/api/leads` resta come fallback.
Importa i lead raccolti nel frattempo dalle notifiche email con
`scripts/ingest_prospects.py`.

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
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build app
docker compose exec app alembic upgrade head
```

Rollback: `git checkout <tag-precedente>` + stesso comando di build.
