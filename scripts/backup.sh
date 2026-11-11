#!/usr/bin/env bash
# ============================================================================
# NormaAI - nightly backup of the server.
# What it covers and what it does not: docs/BACKUP_STRATEGY.md.
#
#   bash scripts/backup.sh                  one backup run
#   bash scripts/backup.sh --install-cron   install or replace the nightly cron line
#
# One run:
#   1. dumps Postgres into backups/normaai_<stamp>.dump and checks that the
#      archive is readable;
#   2. only when restic is configured: takes a snapshot of every Qdrant
#      collection, copies .env and the JWT keys, sends all of it, encrypted, to
#      RESTIC_REPOSITORY, then drops the off-site copies past the retention;
#   3. deletes the local dumps past the retention.
# Without restic it does 1 and 3 and says what is missing: the dump then stays
# on this disk, unencrypted, and the index and .env are not backed up at all.
#
# Configuration: environment variables, read from BACKUP_ENV_FILE when the file
# exists (default /etc/normaai/backup.env, root only; the bootstrap writes it).
# It is kept out of .env on purpose: .env is handed to the app container.
#   RESTIC_REPOSITORY      s3:https://<endpoint>/<bucket>/normaai, sftp:<host>:normaai, ...
#   RESTIC_PASSWORD_FILE   file with the repository password. Keep the password
#                          OFF this server too: without it no backup can be read.
#   AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY   for S3-compatible storage
#   BACKUP_RETENTION_DAYS  default 30: no copy older than this survives a run
#   BACKUP_HEARTBEAT_URL   optional: fetched after a complete off-site run, for
#                          a service that warns when the fetch stops coming
#   QDRANT_URL             default http://127.0.0.1:6333 (docker-compose.yml
#                          publishes Qdrant on the loopback interface only)
#
# Exit status: 0 only when every step succeeded.
# ============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_ENV_FILE="${BACKUP_ENV_FILE:-/etc/normaai/backup.env}"
if [ -f "$BACKUP_ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$BACKUP_ENV_FILE"
  set +a
fi

BACKUP_DIR="${BACKUP_DIR:-$REPO_ROOT/backups}"
# A fixed path: restic groups the snapshots of one host by the path they saved.
STAGE_DIR="$BACKUP_DIR/offsite"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-normaai-postgres}"
DB_USER="${DB_USER:-normaai}"
DB_NAME="${DB_NAME:-normaai}"
QDRANT_URL="${QDRANT_URL:-http://127.0.0.1:6333}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
BACKUP_HOST="${BACKUP_HOST:-normaai}"
BACKUP_TAG="normaai"
CRON_LOG="/var/log/normaai-backup.log"

log() { printf '[backup] %s\n' "$*"; }
warn() { printf '[backup] WARNING: %s\n' "$*" >&2; }
die() {
  printf '[backup] FAIL: %s\n' "$*" >&2
  exit 1
}

# Reads JSON on stdin as `d` and runs the given Python expression statement.
json() { python3 -c 'import json, sys
d = json.load(sys.stdin)
'"$1"; }

# ── Cron ─────────────────────────────────────────────────────────────────────
install_cron() {
  local line current
  # Through `bash`, not by path: the script is not executable in git, and every
  # deploy (`git reset --hard`) would take the execute bit away again.
  line="0 2 * * * bash $REPO_ROOT/scripts/backup.sh >> $CRON_LOG 2>&1"
  current="$(crontab -l 2>/dev/null || true)"
  {
    if [ -n "$current" ]; then
      # Keep every other job; drop the previous backup lines, old name included.
      printf '%s\n' "$current" | grep -v -E 'scripts/backup(_postgres)?\.sh' || true
    fi
    printf '%s\n' "$line"
  } | crontab -
  log "cron line installed: $line"
}

# ── Postgres ─────────────────────────────────────────────────────────────────
dump_postgres() {
  local stamp partial size_kb
  [ "$(docker inspect -f '{{.State.Running}}' "$POSTGRES_CONTAINER" 2>/dev/null || true)" = "true" ] ||
    die "the container $POSTGRES_CONTAINER is not running"
  stamp="$(date +%Y%m%d_%H%M%S)"
  DUMP_FILE="$BACKUP_DIR/normaai_${stamp}.dump"
  partial="$DUMP_FILE.partial"
  log "dumping $DB_NAME from $POSTGRES_CONTAINER"
  docker exec "$POSTGRES_CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc --no-owner > "$partial" ||
    die "pg_dump failed"
  size_kb=$(($(wc -c < "$partial") / 1024))
  [ "$size_kb" -ge 5 ] || die "the dump is suspiciously small (${size_kb} KB)"
  # Integrity: pg_restore must be able to read the table of contents.
  docker exec -i "$POSTGRES_CONTAINER" pg_restore --list < "$partial" > /dev/null ||
    die "pg_restore cannot read the dump"
  mv "$partial" "$DUMP_FILE"
  log "Postgres dump: $DUMP_FILE (${size_kb} KB, archive readable)"
}

# ── Qdrant ───────────────────────────────────────────────────────────────────
# One snapshot per collection into $STAGE_DIR/qdrant/<collection>.snapshot, the
# name scripts/bootstrap_hetzner.sh restores from. Returns 1 when any
# collection could not be saved.
snapshot_qdrant() {
  local names name created snapshot expected target actual failed=0
  command -v python3 > /dev/null 2>&1 || {
    warn "python3 is needed to read Qdrant's answers"
    return 1
  }
  names="$(curl -fsS --max-time 30 "$QDRANT_URL/collections" |
    json 'print("\n".join(c["name"] for c in d["result"]["collections"]))')" || {
    warn "Qdrant does not answer at $QDRANT_URL"
    return 1
  }
  [ -n "$names" ] || {
    warn "Qdrant has no collection"
    return 1
  }
  mkdir -p "$STAGE_DIR/qdrant"
  while IFS= read -r name; do
    case "$name" in
      '' | *[!A-Za-z0-9_-]*)
        warn "collection skipped, its name cannot be a file name"
        failed=1
        continue
        ;;
    esac
    created="$(curl -fsS --max-time 900 -X POST "$QDRANT_URL/collections/$name/snapshots?wait=true" |
      json 'print(d["result"]["name"], d["result"].get("size") or "")')" || {
      warn "Qdrant could not snapshot the collection $name"
      failed=1
      continue
    }
    snapshot="${created%% *}"
    expected="${created#* }"
    case "$snapshot" in
      '' | *[!A-Za-z0-9._-]*)
        warn "unexpected snapshot name for the collection $name"
        failed=1
        continue
        ;;
    esac
    target="$STAGE_DIR/qdrant/$name.snapshot"
    if curl -fsS --max-time 3600 -o "$target" "$QDRANT_URL/collections/$name/snapshots/$snapshot"; then
      actual="$(wc -c < "$target" | tr -d '[:space:]')"
      if [ -n "$expected" ] && [ "$expected" != "$actual" ]; then
        warn "snapshot of $name: downloaded $actual bytes, Qdrant announced $expected"
        rm -f "$target"
        failed=1
      else
        log "Qdrant snapshot: $name ($actual bytes)"
      fi
    else
      warn "could not download the snapshot of the collection $name"
      rm -f "$target"
      failed=1
    fi
    # Qdrant keeps its own copy inside the container, outside the data volume:
    # left there, one more copy of every collection would pile up each night.
    curl -fsS --max-time 60 -X DELETE "$QDRANT_URL/collections/$name/snapshots/$snapshot?wait=true" > /dev/null ||
      warn "could not delete the snapshot $snapshot inside Qdrant: delete it by hand"
  done <<< "$names"
  return "$failed"
}

# ── Secrets and a note of what the copy holds ────────────────────────────────
stage_config() {
  local key missing=0
  mkdir -p "$STAGE_DIR/config"
  if [ -f "$REPO_ROOT/.env" ] && cp "$REPO_ROOT/.env" "$STAGE_DIR/config/env"; then
    log "configuration: .env"
  else
    warn "$REPO_ROOT/.env could not be copied: this run holds no server configuration"
    missing=1
  fi
  for key in jwt_private.pem jwt_public.pem; do
    if [ -f "$REPO_ROOT/data/$key" ]; then
      cp "$REPO_ROOT/data/$key" "$STAGE_DIR/config/$key" || missing=1
    fi
  done
  return "$missing"
}

write_manifest() {
  local file
  {
    printf 'NormaAI backup of %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'code: %s\n' "$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
    printf 'alembic: %s\n' "$(docker exec "$POSTGRES_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc \
      'SELECT version_num FROM alembic_version' 2>/dev/null || echo unknown)"
    # A Qdrant snapshot restores on the same minor version or on the next one.
    printf 'qdrant: %s\n' "$(curl -fsS --max-time 10 "$QDRANT_URL/" 2>/dev/null |
      json 'print(d.get("version", "unknown"))' 2>/dev/null || echo unknown)"
    printf 'files (bytes):\n'
    (cd "$STAGE_DIR" && find . -type f ! -name MANIFEST.txt | sort) | while IFS= read -r file; do
      printf '%12s  %s\n' "$(wc -c < "$STAGE_DIR/$file" | tr -d '[:space:]')" "$file"
    done
  } > "$STAGE_DIR/MANIFEST.txt"
}

# ── Off the server, encrypted ────────────────────────────────────────────────
send_offsite() {
  command -v restic > /dev/null 2>&1 ||
    die "restic is configured but not installed (apt-get install restic)"
  if [ ! -r "$RESTIC_PASSWORD_FILE" ] || [ ! -s "$RESTIC_PASSWORD_FILE" ]; then
    die "RESTIC_PASSWORD_FILE ($RESTIC_PASSWORD_FILE) is missing or empty"
  fi
  export RESTIC_REPOSITORY RESTIC_PASSWORD_FILE
  if ! restic cat config > /dev/null 2>&1; then
    # Either the repository is new or it cannot be opened: init succeeds only
    # in the first case, and never overwrites an existing repository.
    log "no restic repository opens at RESTIC_REPOSITORY: creating it"
    restic init || die "cannot open or create the restic repository (address, credentials, password)"
  fi
  restic backup --host "$BACKUP_HOST" --tag "$BACKUP_TAG" "$STAGE_DIR" ||
    die "restic backup failed: nothing was sent off the server"
  log "sent to the restic repository, encrypted"
  # --keep-within counts from the newest snapshot: if the nightly job stops,
  # nothing more is deleted.
  if ! restic forget --host "$BACKUP_HOST" --tag "$BACKUP_TAG" --group-by host \
    --keep-within "${KEEP_DAYS}d" --prune; then
    warn "restic forget failed: the off-site copies past the retention were not removed"
    return 1
  fi
}

prune_local() {
  find "$BACKUP_DIR" -maxdepth 1 -type f -name 'normaai_*.dump' \
    -mmin "+$((KEEP_DAYS * 1440))" -print -delete | sed 's/^/[backup] pruned /'
}

cleanup() {
  # The staging directory holds a plain copy of the secrets: never leave it.
  rm -rf "$STAGE_DIR"
  rm -f "$BACKUP_DIR"/normaai_*.dump.partial
}

main() {
  local status=0 mode
  umask 077
  mkdir -p "$BACKUP_DIR"
  if command -v flock > /dev/null 2>&1; then
    exec 9> "$BACKUP_DIR/.lock"
    flock -n 9 || die "another backup run holds the lock"
  fi
  trap cleanup EXIT

  dump_postgres

  if [ -n "${RESTIC_REPOSITORY:-}" ] && [ -n "${RESTIC_PASSWORD_FILE:-}" ]; then
    mode="off-site"
    rm -rf "$STAGE_DIR"
    mkdir -p "$STAGE_DIR/postgres"
    cp "$DUMP_FILE" "$STAGE_DIR/postgres/normaai.dump"
    # A Qdrant problem must not keep the database from leaving the server.
    snapshot_qdrant || {
      warn "the off-site copy of this run holds no complete Qdrant index"
      status=1
    }
    stage_config || status=1
    write_manifest
    send_offsite || status=1
  elif [ -n "${RESTIC_REPOSITORY:-}" ] || [ -n "${RESTIC_PASSWORD_FILE:-}" ]; then
    die "set both RESTIC_REPOSITORY and RESTIC_PASSWORD_FILE (in $BACKUP_ENV_FILE), or neither"
  else
    mode="local only"
    warn "off-site backup is NOT configured (RESTIC_REPOSITORY, RESTIC_PASSWORD_FILE)."
    warn "This run only wrote an unencrypted Postgres dump on this server's own disk."
    warn "The Qdrant index and .env are NOT backed up; if the server is lost or"
    warn "cancelled, so is every copy. See docs/BACKUP_STRATEGY.md."
  fi

  prune_local
  [ "$status" -eq 0 ] || die "finished with errors: see the warnings above"

  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$mode" > "$BACKUP_DIR/last_success"
  if [ "$mode" = "off-site" ] && [ -n "${BACKUP_HEARTBEAT_URL:-}" ]; then
    curl -fsS --max-time 15 --retry 3 -o /dev/null "$BACKUP_HEARTBEAT_URL" ||
      warn "the heartbeat was not delivered"
  fi
  log "done ($mode)"
}

case "$RETENTION_DAYS" in
  '' | *[!0-9]*) die "BACKUP_RETENTION_DAYS must be a whole number of days" ;;
esac
[ "$RETENTION_DAYS" -ge 2 ] || die "BACKUP_RETENTION_DAYS must be at least 2"
# The job runs once a day, so a copy is deleted by the first run that finds it
# older than RETENTION_DAYS - 1 days: no copy reaches RETENTION_DAYS + a run.
KEEP_DAYS=$((RETENTION_DAYS - 1))

case "${1:-}" in
  '') main ;;
  --install-cron) install_cron ;;
  -h | --help) sed -n '3,32p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' ;;
  *) die "unknown argument: $1 (see --help)" ;;
esac
