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
#   2. Clones (or updates) the repo into /opt/normaai, owned by the non-root
#      user GitHub deploys as (DEPLOY_USER, default deploy, created here and
#      put in the docker group); with DEPLOY_SSH_PUBKEY in the environment it
#      installs that key for it, able to run scripts/deploy.sh only
#   3. Generates every secret and writes .env (asks for the LLM key; Resend and
#      Sentry are optional) with the measured configuration (docs/MODELS.md
#      2.3): anthropic with ANTHROPIC_MODEL=claude-haiku-5-5, the e5 search
#      model with RERANKER_SEARCH_DEPTH=45 and no reranker, one worker
#   4. The image: pulled when NORMAAI_IMAGE (environment or .env) names one
#      from GHCR, otherwise built here (bakes the embedding model); the RS256
#      JWT key pair
#   5. Starts postgres / qdrant / redis and runs the migrations as the owner,
#      in the one-shot migrate service of docker-compose.prod.yml
#   6. Creates the NON-superuser DB role (RLS is inert for superusers)
#   7. Restores the Qdrant collections from the snapshots in $SNAPSHOT_DIR
#      (minutes); without snapshots it seeds the corpus from EUR-Lex, which
#      with multilingual-e5-large takes hours of CPU
#   8. Starts the app behind Caddy with the RLS overlay (TLS via Let's Encrypt)
#   9. Cron: nightly backup (scripts/backup.sh) with a first run, the monthly
#      restore test, and the two application jobs (nightly check-freshness,
#      weekly recheck-documents, both `python -m src.pipeline` inside the app
#      container); final health checks
#
# The app container gets no password of the database owner: .env keeps
# POSTGRES_PASSWORD for the postgres and migrate services and
# docker-compose.prod.yml blanks it for the app, which connects as normaai_app.
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
# environment skips the question; Enter takes e5): e5, multilingual-e5-large,
# the measured one (golden v2 89/101 against 81, docs/MODELS.md 2.2), 2.1 GB of
# model in the image against 1.1; or mpnet, the default of the code. It sets
# EMBEDDING_MODEL, EMBEDDING_DIMENSION, QDRANT_COLLECTION and
# RERANKER_SEARCH_DEPTH in .env; WEB_CONCURRENCY and APP_MEMORY_LIMIT can also
# be set in the environment before the first run. Each worker holds its own
# copy of the model, 2.8 GB with e5 and 2.1 with mpnet (docs/MODELS.md 6): the
# script stops when WEB_CONCURRENCY workers do not fit in APP_MEMORY_LIMIT.
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
# The non-root user that owns the checkout and runs the deploys (scripts/deploy.sh).
DEPLOY_USER="${DEPLOY_USER:-deploy}"
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
# restic always: the restore test and a rebuild need it even before backups are configured.
apt-get install -y -qq ca-certificates cron curl git ufw unattended-upgrades openssl restic >/dev/null
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
log "2/9" "Repository in $APP_DIR, utente di deploy $DEPLOY_USER"
# The deploy user: no password, no sudo; in the docker group, which is as much
# as root on this machine. What limits GitHub's key is the forced command below.
if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$DEPLOY_USER"
fi
usermod -aG docker "$DEPLOY_USER"
# Root runs git here too (the backup records the commit): allowed for this path only.
git config --system --get-all safe.directory 2>/dev/null | grep -qxF "$APP_DIR" \
  || git config --system --add safe.directory "$APP_DIR"
if [ -d "$APP_DIR/.git" ]; then
  # A checkout of an older bootstrap belongs to root: hand it over first.
  chown "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR"
  find "$APP_DIR" -mindepth 1 -maxdepth 1 ! -name data ! -name backups -exec chown -R "$DEPLOY_USER:$DEPLOY_USER" {} +
  runuser -u "$DEPLOY_USER" -- git -C "$APP_DIR" fetch -q origin
  runuser -u "$DEPLOY_USER" -- git -C "$APP_DIR" reset -q --hard origin/main
else
  install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$APP_DIR"
  runuser -u "$DEPLOY_USER" -- git clone -q "$REPO_URL" "$APP_DIR"
fi
# GitHub's deploy key (docs/DEPLOY_CHECKLIST.md step 6): it may run
# scripts/deploy.sh and nothing else, with no terminal and no forwarding.
if [ -n "${DEPLOY_SSH_PUBKEY:-}" ]; then
  [[ "$DEPLOY_SSH_PUBKEY" =~ ^(ssh-ed25519|ecdsa-sha2-nistp256|ssh-rsa)\ [A-Za-z0-9+/=]+(\ [^\"]*)?$ ]] \
    || die "DEPLOY_SSH_PUBKEY non e' una chiave pubblica OpenSSH su una riga"
  DEPLOY_HOME="$(getent passwd "$DEPLOY_USER" | cut -d: -f6)"
  install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$DEPLOY_HOME/.ssh"
  KEY_LINE="restrict,command=\"bash $APP_DIR/scripts/deploy.sh --ssh\" $DEPLOY_SSH_PUBKEY"
  touch "$DEPLOY_HOME/.ssh/authorized_keys"
  grep -qxF "$KEY_LINE" "$DEPLOY_HOME/.ssh/authorized_keys" \
    || printf '%s\n' "$KEY_LINE" >> "$DEPLOY_HOME/.ssh/authorized_keys"
  chown "$DEPLOY_USER:$DEPLOY_USER" "$DEPLOY_HOME/.ssh/authorized_keys"
  chmod 600 "$DEPLOY_HOME/.ssh/authorized_keys"
  echo "   chiave di deploy installata per $DEPLOY_USER (solo scripts/deploy.sh)"
fi
cd "$APP_DIR"
# data/ is the app container's only writable mount (read-only root file system):
# data/texts holds the official texts the document check downloads
# (NORMAAI_TEXT_CACHE=/app/data/texts in docker-compose.yml). backups/ is root's.
mkdir -p data/texts backups
chown root:root backups && chmod 700 backups
# Baked into the image (Dockerfile ARG GIT_SHA via docker-compose.prod.yml) and
# reported by GET /health as "version", so a deploy can be verified end to end.
export GIT_SHA="$(git rev-parse --short=7 HEAD)"

# ── 3. Secrets and .env ──────────────────────────────────────────────────────
log "3/9" "Configurazione .env"
if [ -f .env ]; then
  echo "   .env esistente: non lo tocco (cancellalo per rigenerarlo)."
else
  echo "   Serve la chiave API del modello. Provider: anthropic (default, l'unico misurato:"
  echo "   Claude Haiku 5.5, docs/MODELS.md 2.3), gemini oppure mistral, non misurati."
  echo "   Le domande degli utenti vengono elaborate dal provider scelto: anthropic e gemini sono"
  echo "   societa' statunitensi; mistral elabora in data center di paesi UE ed EFTA"
  echo "   (docs/DEPLOY_CHECKLIST.md, docs/MODELS.md sezione 5.1). Imposta un limite di spesa"
  echo "   nella console del provider prima di aprire il servizio (docs/DEPLOY_CHECKLIST.md, passo 1)."
  read -r -p "   LLM_PROVIDER [anthropic]: " LLM_PROVIDER; LLM_PROVIDER="${LLM_PROVIDER:-anthropic}"
  read -r -s -p "   Chiave API del provider: " LLM_KEY; echo
  [ -n "$LLM_KEY" ] || die "chiave API vuota"
  read -r -s -p "   RESEND_API_KEY (invio email; invio vuoto per saltare): " RESEND_KEY; echo
  read -r -s -p "   SENTRY_DSN (errori a Sentry; invio vuoto per saltare): " SENTRY_DSN_VALUE; echo
  read -r -p "   Email del primo amministratore [info@normaai.org]: " ADMIN_EMAIL
  ADMIN_EMAIL="${ADMIN_EMAIL:-info@normaai.org}"
  echo "   Modello di ricerca (docs/DEPLOY_CHECKLIST.md): e5 = multilingual-e5-large, quello misurato"
  echo "   (golden set 89/101, modello di 2,1 GB nell'immagine); mpnet = predefinito del codice (81/101, 1,1 GB)."
  EMBEDDING_CHOICE="${EMBEDDING_CHOICE:-}"
  until [ "$EMBEDDING_CHOICE" = e5 ] || [ "$EMBEDDING_CHOICE" = mpnet ]; do
    read -r -p "   Modello (e5 o mpnet) [e5]: " EMBEDDING_CHOICE; EMBEDDING_CHOICE="${EMBEDDING_CHOICE:-e5}"
  done
  # Each collection was built with its model: the snapshots carry both. The
  # search depth is the one measured with that model (docs/MODELS.md 4.1).
  case "$EMBEDDING_CHOICE" in
    e5) EMBEDDING_MODEL="$E5_MODEL"; EMBEDDING_DIMENSION=1024; QDRANT_COLLECTION=eu_regulations_e5
        RERANKER_SEARCH_DEPTH=45 ;;
    mpnet) EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-mpnet-base-v2
           EMBEDDING_DIMENSION=768; QDRANT_COLLECTION=eu_regulations; RERANKER_SEARCH_DEPTH=90 ;;
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
# Migrations run as the owner in the one-shot service: docker compose run --rm migrate.
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
# The measured model (docs/MODELS.md 2.3), also the default of src/config.py.
# Set a spending limit for this key in the Anthropic console.
ANTHROPIC_MODEL=claude-haiku-5-5
# Mistral answers from its EU regional endpoint unless MISTRAL_BASE_URL says otherwise.
MISTRAL_API_KEY=$MISTRAL_API_KEY

# Owner of the schema: for the postgres and migrate services only.
# docker-compose.prod.yml blanks it in the app container, which connects as
# normaai_app with APP_DB_PASSWORD (docker-compose.rls.yml).
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
APP_DB_PASSWORD=$APP_DB_PASSWORD
QDRANT_HOST=qdrant
QDRANT_PORT=6333
REDIS_URL=redis://redis:6379/0

# Collection and dense model: docker compose also bakes EMBEDDING_MODEL into the image.
QDRANT_COLLECTION=$QDRANT_COLLECTION
EMBEDDING_MODEL=$EMBEDDING_MODEL
EMBEDDING_DIMENSION=$EMBEDDING_DIMENSION
# Uvicorn workers and app container memory: each worker loads its own model,
# 2.8 GB with e5 and 2.1 with mpnet (docs/MODELS.md, section 6). 1 worker in 4G;
# 2 workers with e5 need APP_MEMORY_LIMIT=7G, and a 16 GB server.
WEB_CONCURRENCY=$WEB_CONCURRENCY
APP_MEMORY_LIMIT=$APP_MEMORY_LIMIT
# Cross-encoder reranker off (docs/MODELS.md, section 4); fusion depth of the model.
RERANKER_MODEL_DIR=
RERANKER_SEARCH_DEPTH=$RERANKER_SEARCH_DEPTH

# The image the app runs: scripts/deploy.sh writes the GHCR digest after each
# deploy. Empty: the image built on this server (normaai-app:local).
NORMAAI_IMAGE=${NORMAAI_IMAGE:-}

JWT_PRIVATE_KEY_PATH=/app/data/jwt_private.pem
JWT_PUBLIC_KEY_PATH=/app/data/jwt_public.pem

DATA_SOURCE=eurlex
# Fallback only: the API reads the corpus date from the collection's metadata
# point, written by the seed and by --action update; step 7 copies it here.
CORPUS_AS_OF=
ACQUISITION_SCHEDULER_ENABLED=false

RESEND_API_KEY=$RESEND_KEY
RESEND_FROM_EMAIL=info@normaai.org
RESEND_FROM_NAME=NormaAI
RESEND_REPLY_TO=info@normaai.org

# Alarms (docs/RUNBOOK.md section 1): errors to Sentry; failed cron jobs,
# backups and restore tests also by email (through Resend) to OPS_ALERT_EMAIL.
SENTRY_DSN=$SENTRY_DSN_VALUE
OPS_ALERT_EMAIL=$ADMIN_EMAIL

GRAFANA_PASSWORD=$(gen 18)
PROMETHEUS_BEARER_TOKEN=$(gen 32)
EOF
  chmod 600 .env
  echo "   .env scritto (permessi 600). Copialo in un posto sicuro: contiene le password."
fi
# Read by docker compose as the deploy user; root reads it anyway.
chown "$DEPLOY_USER:$DEPLOY_USER" .env && chmod 600 .env
# shellcheck disable=SC1091
set -a; . ./.env; set +a
# An .env written before the model choice existed: what the app falls back to.
: "${EMBEDDING_MODEL:=sentence-transformers/paraphrase-multilingual-mpnet-base-v2}"
: "${QDRANT_COLLECTION:=eu_regulations}"
: "${WEB_CONCURRENCY:=1}"
: "${APP_MEMORY_LIMIT:=4G}"
# The arithmetic of docs/MODELS.md section 6: each worker loads its own model.
case "$EMBEDDING_MODEL" in
  "$E5_MODEL") PER_WORKER_MB=2800 ;;
  *) PER_WORKER_MB=2100 ;;
esac
MEM_NUMBER="${APP_MEMORY_LIMIT%[gGmM]}"
[[ "$MEM_NUMBER" =~ ^[1-9][0-9]*$ ]] || die "APP_MEMORY_LIMIT deve essere un numero intero di G o M (per esempio 4G), trovato '$APP_MEMORY_LIMIT'"
case "$APP_MEMORY_LIMIT" in
  *[gG]) LIMIT_MB=$((MEM_NUMBER * 1024)) ;;
  *[mM]) LIMIT_MB=$MEM_NUMBER ;;
  *) die "APP_MEMORY_LIMIT deve finire con G o M (per esempio 4G), trovato '$APP_MEMORY_LIMIT'" ;;
esac
[[ "$WEB_CONCURRENCY" =~ ^[1-9][0-9]*$ ]] || die "WEB_CONCURRENCY deve essere un numero intero, trovato '$WEB_CONCURRENCY'"
if [ $((WEB_CONCURRENCY * PER_WORKER_MB)) -gt "$LIMIT_MB" ]; then
  die "$WEB_CONCURRENCY worker x $PER_WORKER_MB MB = $((WEB_CONCURRENCY * PER_WORKER_MB)) MB non stanno in APP_MEMORY_LIMIT=$APP_MEMORY_LIMIT: WEB_CONCURRENCY=1, oppure APP_MEMORY_LIMIT piu' alto nel .env (docs/MODELS.md sezione 6)"
fi
# 8 GB recommended (an 8 GB server reports about 7.6 GiB). With 4 GB one worker
# fits: 2.8 GB with e5 after the 101 golden questions (1.6 GiB right after the
# warm-up in the dress rehearsal), with little room for requests, a build on the
# server and the monitoring stack.
MEM_KB="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
if [ "$MEM_KB" -lt 7340032 ] && [ "${ALLOW_LOW_MEMORY:-0}" != "1" ]; then
  die "consigliati 8 GB di RAM (trovati $((MEM_KB / 1024)) MB): con 4 GB un solo worker e poco margine; ALLOW_LOW_MEMORY=1 per procedere"
fi

# ── 4. Image + JWT keys ──────────────────────────────────────────────────────
# NORMAAI_IMAGE names the image CI built (ghcr.io/...@sha256:...): pulled, not
# built. Without it, the image is built here, as the deploys did before GHCR.
NORMAAI_IMAGE="${NORMAAI_IMAGE:-}"
if [ -n "$NORMAAI_IMAGE" ] && docker image inspect "$NORMAAI_IMAGE" >/dev/null 2>&1; then
  log "4/9" "Immagine $NORMAAI_IMAGE (gia' presente) e chiavi JWT RS256"
  BUILD_FLAG="--no-build"
elif [[ "$NORMAAI_IMAGE" == *@sha256:* ]]; then
  log "4/9" "Immagine $NORMAAI_IMAGE (da GHCR) e chiavi JWT RS256"
  docker pull -q "$NORMAAI_IMAGE" >/dev/null \
    || die "impossibile scaricare $NORMAAI_IMAGE (pacchetto privato? docker login ghcr.io, oppure NORMAAI_IMAGE= vuoto nel .env per costruirla qui)"
  BUILD_FLAG="--no-build"
else
  # Empty: normaai-app:local; a local tag that is gone (scripts/deploy.sh ... build): rebuilt.
  log "4/9" "Build dell'immagine (scarica $EMBEDDING_MODEL, circa 2,2 GB con e5) e chiavi JWT RS256"
  $COMPOSE_BASE build app
  BUILD_FLAG="--build"
fi
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
# extensions). Run as the `normaai` owner, in the one-shot migrate service of
# docker-compose.prod.yml: normaai_app cannot ALTER tables, and the app
# container does not get the owner's password. No `|| alembic stamp head`
# fallback: that used to hide the init_db.sql drift and left tables missing -
# migration 007 reconciles any pre-existing database instead.
$COMPOSE_BASE run --rm migrate

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
$COMPOSE_RLS up -d $BUILD_FLAG app caddy
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
# The application's scheduled jobs (the in-process scheduler stays off): run
# inside the app container, logged to $JOBS_LOG. Re-running replaces the two
# lines and keeps every other cron line.
JOBS_LOG="/var/log/normaai-jobs.log"
APP_CRON_LINES="30 3 * * * docker exec normaai-app python -m src.pipeline --action check-freshness >> $JOBS_LOG 2>&1
0 4 * * 1 docker exec normaai-app python -m src.pipeline --action recheck-documents >> $JOBS_LOG 2>&1"
if { { crontab -l 2>/dev/null || true; } | { grep -v -E 'src\.pipeline --action (check-freshness|recheck-documents)' || true; }
     printf '%s\n' "$APP_CRON_LINES"; } | crontab -; then
  echo "   Cron dell'app: check-freshness ogni notte alle 03:30, recheck-documents il lunedi' alle 04:00 (log in $JOBS_LOG)."
else
  echo "   ATTENZIONE: righe di cron dell'app NON installate: niente controllo di aggiornamento del corpus ne' ricontrollo dei documenti."
fi
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
  - Salva una copia di $APP_DIR/.env fuori dal server, nel password manager, con la password
    del repository restic. Le chiavi JWT no: un server ricostruito ne crea una coppia nuova.
  - Backup: ogni notte alle 02:00 (bash $APP_DIR/scripts/backup.sh, log in /var/log/normaai-backup.log).
    Prova subito il ripristino: bash $APP_DIR/scripts/restore_test.sh (docs/BACKUP_STRATEGY.md).
  - Gli snapshot in $SNAPSHOT_DIR sono la copia di partenza di Qdrant: tienili finche' il primo
    backup fuori dal server non e' riuscito.
  - Sorveglianza: variabili API_BASE_URL e API_EXPECTED_IP del repository GitHub, per il
    controllo .github/workflows/uptime.yml (docs/DEPLOY_CHECKLIST.md).
  - Allarmi: SENTRY_DSN e OPS_ALERT_EMAIL nel .env (docs/RUNBOOK.md sezione 1); un limite di
    spesa nella console del provider del modello.
  - Aggiornamenti: dopo la CI riuscita su main, .github/workflows/deploy.yml costruisce
    l'immagine, la pubblica su GHCR e la installa come $DEPLOY_USER (docs/DEPLOY_CHECKLIST.md
    passo 6: chiave di deploy e segreti). A mano, come $DEPLOY_USER, lo stesso script:
      sudo -u $DEPLOY_USER -H bash $APP_DIR/scripts/deploy.sh <commit di main> build
EOF
