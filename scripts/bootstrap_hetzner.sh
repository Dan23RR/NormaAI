#!/usr/bin/env bash
# ============================================================================
# NormaAI - one-shot production bootstrap for a FRESH Ubuntu 24.04 server
# (8 GB RAM recommended, docs/DEPLOY_CHECKLIST.md).
# Run as root. Idempotent: re-running resumes where it stopped and never
# overwrites an existing .env or JWT keys.
#
#   curl -fsSL https://raw.githubusercontent.com/Dan23RR/NormaAI/main/scripts/bootstrap_hetzner.sh -o bootstrap.sh
#   bash bootstrap.sh
#
# What it does (each step prints [n/9]):
#   1. Docker + compose, 2 GB swap, unattended security upgrades, ufw 22/80/443
#   2. Clones (or updates) the repo into /opt/normaai
#   3. Generates every secret and writes .env (asks only for the LLM key;
#      Resend is optional)
#   4. Builds the image (bakes the embedding model) and the RS256 JWT key pair
#   5. Starts postgres / qdrant / redis and runs the alembic migrations
#   6. Creates the NON-superuser DB role (RLS is inert for superusers)
#   7. Restores the Qdrant collections from the snapshots in $SNAPSHOT_DIR
#      (minutes); without snapshots it seeds the corpus from EUR-Lex, which
#      with multilingual-e5-large takes hours of CPU
#   8. Starts the app behind Caddy with the RLS overlay (TLS via Let's Encrypt)
#   9. Nightly backup (scripts/backup.sh): cron line, a first run, and final
#      health checks
#
# Backups leave the server, encrypted, only when both of these are in the
# environment at the first run (docs/BACKUP_STRATEGY.md, docs/DEPLOY_CHECKLIST.md):
#   RESTIC_REPOSITORY     where restic stores them: s3:https://<endpoint>/<bucket> or
#                         sftp:<user>@<host>:/<path>
#   RESTIC_PASSWORD_FILE  a file you created with the repository password, which
#                         you also keep OFF the server (the bootstrap never
#                         generates it: a password that exists only here is
#                         lost with the server, and the backups with it)
# plus AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY for S3-compatible storage and,
# optionally, BACKUP_HEARTBEAT_URL. Step 9 then installs restic and writes them
# to /etc/normaai/backup.env (root only), which later runs read. Without them
# the nightly job only keeps a Postgres dump on this disk, and says so.
# SKIP_FIRST_BACKUP=1 skips the backup step 9 runs at once: use it when
# rebuilding a lost server, before its database is restored.
#
# The dense model is chosen at the first run (EMBEDDING_CHOICE=e5|mpnet in the
# environment skips the question): e5, multilingual-e5-large, recommended
# (golden v2 89/101 against 81, docs/MODELS.md 2.2), 2.1 GB of model in the image
# against 1.1; or mpnet, the default of the code. It sets EMBEDDING_MODEL,
# EMBEDDING_DIMENSION and QDRANT_COLLECTION in .env; WEB_CONCURRENCY and
# APP_MEMORY_LIMIT can also be set in the environment before the first run.
# Afterwards .env is the source.
#
# DNS must already point api.normaai.org (A record, Cloudflare proxy OFF) to
# this server's IPv4, otherwise Caddy cannot obtain the certificate in step 8.
# ============================================================================
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Dan23RR/NormaAI.git}"
APP_DIR="${APP_DIR:-/opt/normaai}"
API_DOMAIN="${API_DOMAIN:-api.normaai.org}"
ACME_EMAIL="${ACME_EMAIL:-info@normaai.org}"
PUBLIC_URL="${PUBLIC_URL:-https://normaai.org}"
CORS_ORIGINS="${CORS_ORIGINS:-https://normaai.org,https://www.normaai.org,https://normaai-psi.vercel.app}"
# Qdrant snapshots to restore in step 7, one file per collection named
# <collection>.snapshot. Outside APP_DIR: git clone needs an empty directory.
SNAPSHOT_DIR="${SNAPSHOT_DIR:-/opt/normaai-snapshots}"
E5_MODEL="intfloat/multilingual-e5-large"
COMPOSE_BASE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
COMPOSE_RLS="$COMPOSE_BASE -f docker-compose.rls.yml"

log()  { printf '\n\033[1;34m[%s]\033[0m %s\n' "$1" "$2"; }
die()  { printf '\n\033[1;31mERRORE:\033[0m %s\n' "$1" >&2; exit 1; }
gen()  { python3 -c "import secrets; print(secrets.token_urlsafe($1))"; }

[ "$(id -u)" -eq 0 ] || die "esegui come root (sudo -i)"
command -v python3 >/dev/null || apt-get install -y python3 >/dev/null

# ── 1. Base system ───────────────────────────────────────────────────────────
log "1/9" "Docker, swap, aggiornamenti automatici, firewall"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates cron curl git ufw unattended-upgrades openssl >/dev/null
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
docker compose version >/dev/null 2>&1 || die "docker compose plugin mancante"
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
dpkg-reconfigure -f noninteractive unattended-upgrades >/dev/null 2>&1 || true
ufw allow 22/tcp >/dev/null; ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null

# ── 2. Code ──────────────────────────────────────────────────────────────────
log "2/9" "Repository in $APP_DIR"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch -q origin && git -C "$APP_DIR" reset -q --hard origin/main
else
  git clone -q "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"
mkdir -p data backups
# Baked into the image (Dockerfile ARG GIT_SHA via docker-compose.prod.yml) and
# reported by GET /health as "version", so a deploy can be verified end to end.
export GIT_SHA="$(git rev-parse --short=7 HEAD)"

# ── 3. Secrets and .env ──────────────────────────────────────────────────────
log "3/9" "Configurazione .env"
if [ -f .env ]; then
  echo "   .env esistente: non lo tocco (cancellalo per rigenerarlo)."
else
  echo "   Serve la chiave API del modello. Provider: gemini (default), anthropic oppure mistral."
  echo "   Le domande degli utenti vengono elaborate dal provider scelto: gemini e anthropic sono"
  echo "   societa' statunitensi; mistral elabora in data center di paesi UE ed EFTA, ma non e'"
  echo "   ancora misurato sul golden set (docs/DEPLOY_CHECKLIST.md, docs/MODELS.md sezione 5.1)."
  read -r -p "   LLM_PROVIDER [gemini]: " LLM_PROVIDER; LLM_PROVIDER="${LLM_PROVIDER:-gemini}"
  read -r -s -p "   Chiave API del provider: " LLM_KEY; echo
  [ -n "$LLM_KEY" ] || die "chiave API vuota"
  read -r -s -p "   RESEND_API_KEY (invio email; invio vuoto per saltare): " RESEND_KEY; echo
  read -r -p "   Email del primo amministratore [info@normaai.org]: " ADMIN_EMAIL
  ADMIN_EMAIL="${ADMIN_EMAIL:-info@normaai.org}"
  echo "   Modello di ricerca (docs/DEPLOY_CHECKLIST.md): e5 = multilingual-e5-large, consigliato"
  echo "   (golden set 89/101, modello di 2,1 GB nell'immagine); mpnet = predefinito del codice (81/101, 1,1 GB)."
  EMBEDDING_CHOICE="${EMBEDDING_CHOICE:-}"
  until [ "$EMBEDDING_CHOICE" = e5 ] || [ "$EMBEDDING_CHOICE" = mpnet ]; do
    read -r -p "   Modello (e5 o mpnet): " EMBEDDING_CHOICE
  done
  # Each collection was built with its model: the snapshots carry both.
  case "$EMBEDDING_CHOICE" in
    e5) EMBEDDING_MODEL="$E5_MODEL"; EMBEDDING_DIMENSION=1024; QDRANT_COLLECTION=eu_regulations_e5 ;;
    mpnet) EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-mpnet-base-v2
           EMBEDDING_DIMENSION=768; QDRANT_COLLECTION=eu_regulations ;;
  esac
  WEB_CONCURRENCY="${WEB_CONCURRENCY:-1}"
  APP_MEMORY_LIMIT="${APP_MEMORY_LIMIT:-4G}"
  POSTGRES_PASSWORD="$(gen 24)"; APP_DB_PASSWORD="$(gen 24)"
  GOOGLE_API_KEY=""; ANTHROPIC_API_KEY=""; MISTRAL_API_KEY=""
  case "$LLM_PROVIDER" in
    gemini) GOOGLE_API_KEY="$LLM_KEY" ;;
    anthropic) ANTHROPIC_API_KEY="$LLM_KEY" ;;
    mistral) MISTRAL_API_KEY="$LLM_KEY" ;;
    *) die "LLM_PROVIDER deve essere gemini, anthropic o mistral" ;;
  esac
  cat > .env <<EOF
# Generated by scripts/bootstrap_hetzner.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ)
# A plain "docker compose" here uses the production files (docs/RUNBOOK.md).
# Without it, "docker compose up -d app" would recreate the app from the base
# file and the dev override: as the superuser, which production refuses.
# Migrations name the base files explicitly (normaai_app cannot ALTER tables).
COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml:docker-compose.rls.yml
APP_ENV=production
APP_SECRET_KEY=$(gen 64)
CORS_ORIGINS=$CORS_ORIGINS
NORMAAI_PUBLIC_URL=$PUBLIC_URL
# Registrazione solo su invito; lo staff (crawl, inviti per nuove organizzazioni)
REGISTRATION_MODE=invite
STAFF_EMAILS=$ADMIN_EMAIL
API_DOMAIN=$API_DOMAIN
ACME_EMAIL=$ACME_EMAIL

LLM_PROVIDER=$LLM_PROVIDER
GOOGLE_API_KEY=$GOOGLE_API_KEY
ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY
# Mistral answers from its EU regional endpoint unless MISTRAL_BASE_URL says otherwise.
MISTRAL_API_KEY=$MISTRAL_API_KEY

POSTGRES_PASSWORD=$POSTGRES_PASSWORD
DATABASE_URL=postgresql+asyncpg://normaai:$POSTGRES_PASSWORD@postgres:5432/normaai
DATABASE_URL_SYNC=postgresql://normaai:$POSTGRES_PASSWORD@postgres:5432/normaai
APP_DB_PASSWORD=$APP_DB_PASSWORD
QDRANT_HOST=qdrant
QDRANT_PORT=6333
REDIS_URL=redis://redis:6379/0

# Collection and dense model: docker compose also bakes EMBEDDING_MODEL into the image.
QDRANT_COLLECTION=$QDRANT_COLLECTION
EMBEDDING_MODEL=$EMBEDDING_MODEL
EMBEDDING_DIMENSION=$EMBEDDING_DIMENSION
# Uvicorn workers and app container memory: 2.8 GB per worker with e5 (docs/MODELS.md, section 6).
WEB_CONCURRENCY=$WEB_CONCURRENCY
APP_MEMORY_LIMIT=$APP_MEMORY_LIMIT
# Cross-encoder reranker off (docs/MODELS.md, section 4).
RERANKER_MODEL_DIR=

JWT_PRIVATE_KEY_PATH=/app/data/jwt_private.pem
JWT_PUBLIC_KEY_PATH=/app/data/jwt_public.pem

DATA_SOURCE=both
# Step 7 writes the corpus date of the collection here (its metadata point).
CORPUS_AS_OF=
ACQUISITION_SCHEDULER_ENABLED=false

RESEND_API_KEY=$RESEND_KEY
RESEND_FROM_EMAIL=info@normaai.org
RESEND_FROM_NAME=NormaAI
RESEND_REPLY_TO=info@normaai.org

GRAFANA_PASSWORD=$(gen 18)
PROMETHEUS_BEARER_TOKEN=$(gen 32)
EOF
  chmod 600 .env
  echo "   .env scritto (permessi 600). Copialo in un posto sicuro: contiene le password."
fi
# shellcheck disable=SC1091
set -a; . ./.env; set +a
# An .env written before the model choice existed: what the app falls back to.
: "${EMBEDDING_MODEL:=sentence-transformers/paraphrase-multilingual-mpnet-base-v2}"
: "${QDRANT_COLLECTION:=eu_regulations}"
# 8 GB recommended (an 8 GB server reports about 7.6 GiB). With 4 GB one worker
# fits, 1.6 GiB with e5 and 1.8 GiB with mpnet in the dress rehearsal, but with
# little room for requests, the deploys' image builds and a second worker.
MEM_KB="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
if [ "$MEM_KB" -lt 7340032 ] && [ "${ALLOW_LOW_MEMORY:-0}" != "1" ]; then
  die "consigliati 8 GB di RAM (trovati $((MEM_KB / 1024)) MB): con 4 GB un solo worker e poco margine; ALLOW_LOW_MEMORY=1 per procedere"
fi

# ── 4. Image build + JWT keys ────────────────────────────────────────────────
log "4/9" "Build dell'immagine (scarica $EMBEDDING_MODEL, circa 2,2 GB con e5) e chiavi JWT RS256"
$COMPOSE_BASE build app
if [ ! -f data/jwt_private.pem ]; then
  openssl genrsa -out data/jwt_private.pem 2048 2>/dev/null
  openssl rsa -in data/jwt_private.pem -pubout -out data/jwt_public.pem 2>/dev/null
fi
# data/ is bind-mounted read-write into the container, which runs as the
# unprivileged "normaai" user of the image: give that uid the files.
APP_UID="$($COMPOSE_BASE run --rm --no-deps --entrypoint id app -u normaai 2>/dev/null | tr -d '[:space:]')"
[ -n "$APP_UID" ] || die "impossibile leggere l'uid dell'utente normaai nell'immagine"
chown -R "$APP_UID:$APP_UID" data
chmod 600 data/jwt_private.pem; chmod 644 data/jwt_public.pem

# ── 5. Infra + migrations ────────────────────────────────────────────────────
log "5/9" "Postgres, Qdrant, Redis e migrazioni"
$COMPOSE_BASE up -d postgres qdrant redis
# Alembic is the only source of the schema (scripts/init_db.sql creates just the
# extensions). Run as the `normaai` owner (base compose, NOT the RLS overlay:
# normaai_app cannot ALTER tables). No `|| alembic stamp head` fallback: that
# used to hide the init_db.sql drift and left tables missing - migration 007
# reconciles any pre-existing database instead.
$COMPOSE_BASE run --rm app alembic upgrade head

# ── 6. Non-superuser role (real RLS) ────────────────────────────────────────
log "6/9" "Ruolo applicativo normaai_app (isolamento multi-tenant reale)"
$COMPOSE_BASE exec -T postgres psql -U normaai -d normaai -v app_pw="$APP_DB_PASSWORD" < scripts/setup_app_role.sql >/dev/null
# Two columns, which psql -tA joins with "|" as t/f. Concatenated in SQL the
# booleans become 'false|false' and the check below would always fail.
ROLE_CHECK="$($COMPOSE_BASE exec -T postgres psql -U normaai -d normaai -tA -c "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname='normaai_app';")"
[ "$ROLE_CHECK" = "f|f" ] || die "il ruolo normaai_app non e' non-privilegiato (atteso f|f, trovato '$ROLE_CHECK')"

# ── 7. Corpus: snapshots, or a seed ─────────────────────────────────────────
log "7/9" "Corpus in Qdrant: snapshot da $SNAPSHOT_DIR, altrimenti seed"
QDRANT_URL="http://127.0.0.1:6333"
# Points of one collection, 0 when it does not exist yet.
points() {
  curl -fsS "$QDRANT_URL/collections/$1" 2>/dev/null \
    | python3 -c 'import json,sys; print(int(json.load(sys.stdin)["result"].get("points_count") or 0))' 2>/dev/null \
    || echo 0
}
for _ in $(seq 1 30); do curl -fsS "$QDRANT_URL/readyz" >/dev/null 2>&1 && break; sleep 2; done
for f in "$SNAPSHOT_DIR"/*.snapshot; do
  [ -f "$f" ] || continue
  name="$(basename "$f" .snapshot)"
  if [ "$(points "$name")" != "0" ] && [ "${RESTORE:-0}" != "1" ]; then
    echo "   $name contiene gia' $(points "$name") punti: non la ripristino (RESTORE=1 per sovrascriverla)."
    continue
  fi
  echo "   ripristino $name da $f"
  curl -fsS -X POST "$QDRANT_URL/collections/$name/snapshots/upload?priority=snapshot&wait=true" \
    -F "snapshot=@$f" >/dev/null || die "ripristino di $name non riuscito"
  echo "   $name: $(points "$name") punti"
done
POINTS="$(points "$QDRANT_COLLECTION")"
if [ "${SKIP_SEED:-0}" = "1" ]; then
  echo "   SKIP_SEED=1: salto il seed."
elif [ "$POINTS" != "0" ] && [ "${RESEED:-0}" != "1" ]; then
  echo "   $QDRANT_COLLECTION contiene $POINTS punti: salto il seed (RESEED=1 per rifarlo)."
else
  echo "   Seed di $QDRANT_COLLECTION con $EMBEDDING_MODEL: con e5 su CPU dura ore, non chiudere la sessione."
  $COMPOSE_BASE run --rm app python -m src.pipeline --action seed ${RESEED:+--recreate}
fi
# Corpus date of answers and reports: the one recorded in the collection (its
# corpus_meta point, written by the seed and carried by the snapshot), not today.
AS_OF="$(curl -fsS -X POST "$QDRANT_URL/collections/$QDRANT_COLLECTION/points/scroll" \
  -H 'Content-Type: application/json' \
  -d '{"filter":{"must":[{"key":"kind","match":{"value":"corpus_meta"}}]},"limit":1,"with_payload":["corpus_as_of"]}' 2>/dev/null \
  | python3 -c 'import json,sys; p=json.load(sys.stdin)["result"]["points"]; print(p[0]["payload"].get("corpus_as_of","") if p else "")' 2>/dev/null \
  || true)"
if [ -n "$AS_OF" ] && [ "$AS_OF" != "${CORPUS_AS_OF:-}" ]; then
  if grep -q '^CORPUS_AS_OF=' .env; then
    sed -i "s/^CORPUS_AS_OF=.*/CORPUS_AS_OF=$AS_OF/" .env
  else
    echo "CORPUS_AS_OF=$AS_OF" >> .env
  fi
  export CORPUS_AS_OF="$AS_OF"
  echo "   CORPUS_AS_OF=$AS_OF in .env (punto dei metadati di $QDRANT_COLLECTION)"
fi

# ── 8. App + Caddy with RLS overlay ─────────────────────────────────────────
log "8/9" "Avvio applicazione dietro Caddy (TLS automatico per $API_DOMAIN)"
$COMPOSE_RLS up -d --build app caddy
echo -n "   attendo che l'app sia healthy"
for _ in $(seq 1 40); do
  if [ "$(docker inspect -f '{{.State.Health.Status}}' normaai-app 2>/dev/null)" = healthy ]; then echo " ok"; break; fi
  echo -n "."; sleep 5
done
[ "$(docker inspect -f '{{.State.Health.Status}}' normaai-app)" = healthy ] || {
  docker logs --tail 60 normaai-app; die "l'app non e' diventata healthy (log sopra)"; }

# ── 9. Backups + verification ───────────────────────────────────────────────
log "9/9" "Backup notturno e verifica finale"
# Off the server and encrypted only with a restic repository and a password
# file the owner created (see the header). The settings go to a root-only file
# of their own, not to .env, which is handed to the app container. An existing
# file is never rewritten.
BACKUP_ENV_FILE="${BACKUP_ENV_FILE:-/etc/normaai/backup.env}"
export BACKUP_ENV_FILE
if [ -f "$BACKUP_ENV_FILE" ]; then
  echo "   $BACKUP_ENV_FILE esistente: non lo tocco."
elif [ -z "${RESTIC_REPOSITORY:-}" ] || [ -z "${RESTIC_PASSWORD_FILE:-}" ]; then
  :
elif [ ! -s "$RESTIC_PASSWORD_FILE" ]; then
  echo "   ATTENZIONE: RESTIC_PASSWORD_FILE ($RESTIC_PASSWORD_FILE) non esiste o e' vuoto. Crealo con la"
  echo "   password che hai salvato nel password manager, poi rilancia questo script."
else
  chmod 600 "$RESTIC_PASSWORD_FILE"
  ( umask 077
    mkdir -p "$(dirname "$BACKUP_ENV_FILE")"
    { echo "# Written by scripts/bootstrap_hetzner.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ)."
      echo "# Read by scripts/backup.sh and scripts/restore_test.sh (docs/BACKUP_STRATEGY.md)."
      for name in RESTIC_REPOSITORY RESTIC_PASSWORD_FILE AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY \
                  AWS_DEFAULT_REGION BACKUP_RETENTION_DAYS BACKUP_HEARTBEAT_URL; do
        if [ -n "${!name:-}" ]; then printf '%s=%q\n' "$name" "${!name}"; fi
      done
    } > "$BACKUP_ENV_FILE" )
  echo "   $BACKUP_ENV_FILE scritto (solo root)."
fi
if [ -f "$BACKUP_ENV_FILE" ]; then
  command -v restic >/dev/null 2>&1 || apt-get install -y -qq restic >/dev/null
  echo "   Backup cifrati fuori dal server: restic $(restic version 2>/dev/null | awk '{print $2}'), impostazioni in $BACKUP_ENV_FILE."
else
  echo "   ATTENZIONE: nessun backup fuori dal server. Il job notturno salva solo un dump di"
  echo "   Postgres su questo disco: se il server viene perso o cancellato, lo sono anche i backup."
  echo "   Per attivarli: docs/DEPLOY_CHECKLIST.md (RESTIC_REPOSITORY e RESTIC_PASSWORD_FILE), poi rilancia."
fi
# The cron line calls the script through bash: the deploys' `git reset --hard`
# would take an execute bit away again. It also replaces the old
# backup_postgres.sh line. Then one run now, which proves the whole chain
# (and creates the restic repository the first time) instead of waiting for 02:00.
bash scripts/backup.sh --install-cron \
  || echo "   ATTENZIONE: riga di cron del backup NON installata (messaggi qui sopra): nessun backup notturno finche' non la installi con: bash $APP_DIR/scripts/backup.sh --install-cron"
if [ "${SKIP_FIRST_BACKUP:-0}" = "1" ]; then
  # Rebuilding a lost server: the database is still empty here, and its backup
  # would become the newest copy (docs/BACKUP_STRATEGY.md, section 6.3).
  echo "   SKIP_FIRST_BACKUP=1: salto il primo backup. Dopo il ripristino lancia: bash $APP_DIR/scripts/backup.sh"
else
  bash scripts/backup.sh \
    || echo "   ATTENZIONE: il primo backup non e' riuscito (messaggi qui sopra). Correggi e lancia: bash $APP_DIR/scripts/backup.sh"
fi
echo "   health (interno):  $(docker exec normaai-app curl -fsS http://localhost:8000/health)"
echo "   readyz (interno):  $(docker exec normaai-app curl -sS http://localhost:8000/readyz)"
echo -n "   https://$API_DOMAIN/health: "
curl -fsS --max-time 20 "https://$API_DOMAIN/health" || echo "(non ancora raggiungibile: controlla il record DNS A -> $(curl -fsS https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}'); Caddy riprova da solo)"
echo

# First administrator: in invite mode nobody can register without a code, so
# the very first one is minted here, once (only while the users table is empty).
ADMIN_EMAIL="${ADMIN_EMAIL:-${STAFF_EMAILS%%,*}}"
USERS="$(docker exec normaai-postgres psql -U normaai -d normaai -tAc 'SELECT count(*) FROM users' 2>/dev/null | tr -d '[:space:]')"
if [ "$USERS" = "0" ] && [ -n "$ADMIN_EMAIL" ]; then
  echo "   Primo invito amministratore per $ADMIN_EMAIL (il codice si vede solo ora):"
  docker exec normaai-app python scripts/create_invite.py --email "$ADMIN_EMAIL" \
    || echo "   (invito non creato: lancia a mano 'docker exec normaai-app python scripts/create_invite.py --email $ADMIN_EMAIL')"
fi

cat <<EOF

Fatto. Prossimi passi (docs/DEPLOY_CHECKLIST.md):
  - Vercel -> Settings -> Environment Variables: NEXT_PUBLIC_API_BASE_URL=https://$API_DOMAIN, poi Redeploy.
  - Registrati su $PUBLIC_URL/login con il codice di invito qui sopra.
  - Dal portatile: pwsh scripts/verify_live_site.ps1 -BaseUrl $PUBLIC_URL
  - Salva una copia di $APP_DIR/.env e di $APP_DIR/data/jwt_private.pem fuori dal server.
  - Backup: ogni notte alle 02:00 (bash $APP_DIR/scripts/backup.sh, log in /var/log/normaai-backup.log).
    Prova subito il ripristino: bash $APP_DIR/scripts/restore_test.sh (docs/BACKUP_STRATEGY.md).
  - Gli snapshot in $SNAPSHOT_DIR sono la copia di partenza di Qdrant: tienili finche' il primo
    backup fuori dal server non e' riuscito.
  - Sorveglianza: variabili API_BASE_URL e API_EXPECTED_IP del repository GitHub, per il
    controllo .github/workflows/uptime.yml (docs/DEPLOY_CHECKLIST.md).
  - Aggiornamenti: un push su main esegue .github/workflows/deploy.yml (build, migrazioni
    come owner, riavvio, verifica di /health). A mano, nello stesso ordine:
      cd $APP_DIR && git pull && export GIT_SHA=\$(git rev-parse --short=7 HEAD)
      $COMPOSE_BASE build app && $COMPOSE_BASE run --rm app alembic upgrade head
      $COMPOSE_RLS up -d app caddy
EOF
