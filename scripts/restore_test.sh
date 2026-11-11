#!/usr/bin/env bash
# ============================================================================
# NormaAI - restore test: proves that the latest backup can be read back.
# A backup nobody has restored is a hope, not a backup. Run it after the first
# backup and then every month (docs/BACKUP_STRATEGY.md).
#
#   bash scripts/restore_test.sh
#
# What it does, without touching the running database:
#   1. takes the latest off-site snapshot from the restic repository (or, when
#      restic is not configured, the newest local dump, and says so);
#   2. fails when that copy is older than RESTORE_TEST_MAX_AGE_HOURS (36): the
#      nightly job has stopped;
#   3. checks the repository (restic check) and that the snapshot holds the
#      Postgres dump, one snapshot per Qdrant collection and the copy of .env;
#   4. loads the dump into a throwaway Postgres container (same image as the
#      running one, no network, removed at the end);
#   5. checks that the core tables exist and prints the row count of every
#      table.
# The Qdrant snapshots are listed, not loaded: restoring one is the upload of
# docs/RUNBOOK.md section 3, which scripts/bootstrap_hetzner.sh also uses.
#
# Configuration: the same BACKUP_ENV_FILE as scripts/backup.sh.
# Exit status: 0 when every check passed, 1 otherwise.
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
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-normaai-postgres}"
BACKUP_HOST="${BACKUP_HOST:-normaai}"
BACKUP_TAG="normaai"
MAX_AGE_HOURS="${RESTORE_TEST_MAX_AGE_HOURS:-36}"
TEST_CONTAINER="normaai-restore-test-$$"
TEST_USER="normaai"
TEST_DB="normaai"
# Present since the first migrations: without them the dump is not the database.
REQUIRED_TABLES=(alembic_version organizations users)
WORK=""
PROBLEMS=0

log() { printf '[restore-test] %s\n' "$*"; }
warn() { printf '[restore-test] WARNING: %s\n' "$*" >&2; }
problem() {
  printf '[restore-test] PROBLEM: %s\n' "$*" >&2
  PROBLEMS=$((PROBLEMS + 1))
}
die() {
  printf '[restore-test] FAIL: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  docker rm -f -v "$TEST_CONTAINER" > /dev/null 2>&1 || true
  # The work directory holds a copy of the database: never leave it.
  if [ -n "$WORK" ]; then
    rm -rf "$WORK"
  fi
}

# No -i: psql must not read this script's standard input (the loops below do).
psql_test() { docker exec "$TEST_CONTAINER" psql -U "$TEST_USER" -d "$TEST_DB" -v ON_ERROR_STOP=1 -tA "$@"; }

# Reads `restic snapshots --json` on stdin; prints the time of the newest
# snapshot and its age in whole hours ("<time> <hours>"), or nothing when the
# list is empty.
newest_snapshot() { python3 -c 'import json, re, sys
from datetime import datetime, timezone

def moment(text):
    # restic prints nanoseconds: keep the six digits every Python version reads.
    text = re.sub(r"(\.\d{6})\d+", r"\1", text.strip()).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.astimezone()

times = [moment(item["time"]) for item in json.load(sys.stdin) or []]
if times:
    newest = max(times)
    age = int((datetime.now(timezone.utc) - newest).total_seconds() // 3600)
    print(newest.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), age)
'; }

check_age() { # <hours> <what>
  local hours="$1"
  case "$hours" in
    '' | *[!0-9-]*) die "cannot read the age of $2" ;;
  esac
  if [ "$hours" -gt "$MAX_AGE_HOURS" ]; then
    problem "$2 is $hours hours old, more than $MAX_AGE_HOURS: the nightly backup has stopped"
  else
    log "$2 is $hours hours old"
  fi
}

# ── 1. The latest copy ───────────────────────────────────────────────────────
fetch_from_restic() {
  local snapshots newest listing dump_path index_files
  command -v restic > /dev/null 2>&1 || die "restic is configured but not installed"
  export RESTIC_REPOSITORY RESTIC_PASSWORD_FILE
  snapshots="$(restic snapshots --host "$BACKUP_HOST" --tag "$BACKUP_TAG" --json)" ||
    die "cannot read the restic repository (address, credentials, password)"
  newest="$(printf '%s' "$snapshots" | newest_snapshot)" || die "cannot read restic's list of snapshots"
  [ -n "$newest" ] || die "the restic repository holds no snapshot of this server yet"
  log "latest off-site snapshot: ${newest%% *}"
  check_age "${newest#* }" "the latest off-site snapshot"

  log "checking the repository (restic check)"
  restic check > /dev/null || problem "restic check reports errors in the repository"

  listing="$(restic ls --host "$BACKUP_HOST" --tag "$BACKUP_TAG" latest)" ||
    die "cannot list the latest snapshot"
  dump_path="$(printf '%s\n' "$listing" | grep -E '/postgres/normaai\.dump$' | head -n 1 || true)"
  [ -n "$dump_path" ] || die "the latest snapshot holds no Postgres dump"
  index_files="$(printf '%s\n' "$listing" | grep -E '/qdrant/[^/]+\.snapshot$' || true)"
  if [ -n "$index_files" ]; then
    log "Qdrant snapshots in the copy (listed, not loaded):"
    printf '%s\n' "$index_files" | sed 's/^/[restore-test]   /'
  else
    problem "the latest snapshot holds no Qdrant snapshot: the index is not backed up"
  fi
  # Not grep -q: it stops at the first match, and under pipefail the writer it
  # cuts off could make a successful search look failed.
  if printf '%s\n' "$listing" | grep -E '/config/env$' > /dev/null; then
    log "server configuration (.env) is in the copy"
  else
    problem "the latest snapshot holds no copy of .env"
  fi
  restic dump --host "$BACKUP_HOST" --tag "$BACKUP_TAG" latest "$dump_path" > "$WORK/normaai.dump" ||
    die "cannot extract the Postgres dump from the snapshot"
}

fetch_local() {
  local newest
  warn "restic is not configured: testing the newest LOCAL dump."
  warn "It sits unencrypted on this server's disk; the index and .env are not backed up."
  # `|| true`: without a backups directory find fails, and under pipefail the
  # script would stop here, before the message below.
  newest="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'normaai_*.dump' -printf '%T@ %p\n' 2>/dev/null |
    sort -n | tail -n 1 | cut -d' ' -f2- || true)"
  [ -n "$newest" ] || die "no dump in $BACKUP_DIR: run scripts/backup.sh first"
  log "newest local dump: $newest"
  check_age "$((($(date +%s) - $(date -r "$newest" +%s)) / 3600))" "the newest local dump"
  cp "$newest" "$WORK/normaai.dump"
}

# ── 2. A throwaway Postgres ──────────────────────────────────────────────────
start_postgres() {
  local image password attempt
  image="$(docker inspect -f '{{.Config.Image}}' "$POSTGRES_CONTAINER" 2>/dev/null || true)"
  image="${image:-postgres:16-alpine}"
  password="$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')"
  log "starting a throwaway $image ($TEST_CONTAINER, no network)"
  docker run -d --name "$TEST_CONTAINER" --network none \
    -e POSTGRES_USER="$TEST_USER" -e POSTGRES_DB="$TEST_DB" -e POSTGRES_PASSWORD="$password" \
    "$image" > /dev/null || die "cannot start the throwaway container"
  # Over TCP on purpose: while the image initialises the data directory its
  # temporary server listens on the socket only, and is restarted afterwards.
  for attempt in $(seq 1 60); do
    if docker exec "$TEST_CONTAINER" pg_isready -h 127.0.0.1 -U "$TEST_USER" -d "$TEST_DB" > /dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  die "the throwaway Postgres was not ready after $attempt seconds"
}

restore_dump() {
  local size_kb
  size_kb=$(($(wc -c < "$WORK/normaai.dump") / 1024))
  # The dump grants privileges to the application role: it must exist first,
  # as on a real server, where scripts/setup_app_role.sql creates it.
  psql_test -q -c 'CREATE ROLE normaai_app NOLOGIN' || die "cannot prepare the throwaway database"
  log "loading the dump (${size_kb} KB)"
  docker exec -i "$TEST_CONTAINER" pg_restore -U "$TEST_USER" -d "$TEST_DB" --no-owner --exit-on-error \
    < "$WORK/normaai.dump" || die "pg_restore failed: the dump does not load"
}

# ── 3. Is it the database? ───────────────────────────────────────────────────
check_database() {
  local table tables count revision
  for table in "${REQUIRED_TABLES[@]}"; do
    if [ "$(psql_test -c "SELECT to_regclass('public.$table') IS NOT NULL")" != "t" ]; then
      problem "the table $table is missing from the restored database"
    fi
  done
  revision="$(psql_test -c 'SELECT version_num FROM alembic_version' 2>/dev/null || true)"
  if [ -n "$revision" ]; then
    log "schema revision (alembic): $revision"
  else
    problem "alembic_version is empty: the schema revision is unknown"
  fi
  # format('%I') quotes each name, so it can go back into a query as it is.
  tables="$(psql_test -c "SELECT format('%I', table_name) FROM information_schema.tables
    WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY 1")" ||
    die "cannot list the restored tables"
  [ -n "$tables" ] || die "the restored database has no table"
  log "rows per table in the restored copy:"
  while IFS= read -r table; do
    count="$(psql_test -c "SELECT count(*) FROM public.$table" < /dev/null)" ||
      die "cannot count the rows of $table"
    printf '[restore-test]   %-28s %s\n' "$table" "$count"
  done <<< "$tables"
}

main() {
  case "$MAX_AGE_HOURS" in
    '' | *[!0-9]*) die "RESTORE_TEST_MAX_AGE_HOURS must be a whole number of hours" ;;
  esac
  umask 077
  WORK="$(mktemp -d)"
  trap cleanup EXIT

  if [ -n "${RESTIC_REPOSITORY:-}" ] && [ -n "${RESTIC_PASSWORD_FILE:-}" ]; then
    fetch_from_restic
  elif [ -n "${RESTIC_REPOSITORY:-}" ] || [ -n "${RESTIC_PASSWORD_FILE:-}" ]; then
    die "set both RESTIC_REPOSITORY and RESTIC_PASSWORD_FILE (in $BACKUP_ENV_FILE), or neither"
  else
    fetch_local
  fi
  start_postgres
  restore_dump
  check_database

  if [ "$PROBLEMS" -gt 0 ]; then
    die "$PROBLEMS problem(s): the backup is not what a restore needs (see above)"
  fi
  log "PASSED: the latest backup loads into Postgres and holds what a restore needs"
}

case "${1:-}" in
  '') main ;;
  -h | --help) sed -n '3,24p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' ;;
  *) die "unknown argument: $1 (see --help)" ;;
esac
