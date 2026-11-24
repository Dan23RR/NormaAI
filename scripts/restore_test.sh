#!/usr/bin/env bash
# ============================================================================
# NormaAI - restore test: proves that the latest backup can be read back.
# A backup nobody has restored is a hope, not a backup. The cron line that
# `bash scripts/backup.sh --install-cron` writes runs it on the 1st of every
# month at 05:00; run it by hand after the first backup (docs/BACKUP_STRATEGY.md).
# scripts/restore_drill.sh runs it away from the server, with the keys of the
# password manager.
#
#   bash scripts/restore_test.sh
#
# What it does, without touching the running database or index:
#   1. takes the latest off-site snapshot from the restic repository (or, when
#      restic is not configured, the newest local dump, and says so);
#   2. fails when that copy is older than RESTORE_TEST_MAX_AGE_HOURS (36): the
#      nightly job has stopped;
#   3. checks the repository (restic check) and that the snapshot holds the
#      Postgres dump, one snapshot per Qdrant collection and the copy of .env,
#      and that the copy of .env names the settings a rebuild needs (names
#      only: no value is printed);
#   4. loads the dump into a throwaway Postgres container (same image as the
#      running one, no network, removed at the end), checks that the core
#      tables exist and prints the row count of every table;
#   5. loads every Qdrant snapshot into a throwaway Qdrant container (the
#      running one's image, published on 127.0.0.1 only, removed at the end)
#      and checks that each collection has its points again: the count
#      MANIFEST.txt recorded at backup time, when it did;
#   6. prints how long each phase took: the measured part of a rebuild.
# A failed test tells the operator (Sentry and/or email, through the app
# container: python -m src.ops_alerts), like a failed backup.
#
# Configuration: the same BACKUP_ENV_FILE as scripts/backup.sh.
#   APP_CONTAINER          default normaai-app: where the failure alert is sent from
#   BACKUP_ALERTS          default 1; 0 sends no alert
#   RESTORE_TEST_QDRANT    default 1; 0 lists the Qdrant snapshots without loading them
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
QDRANT_CONTAINER="${QDRANT_CONTAINER:-normaai-qdrant}"
APP_CONTAINER="${APP_CONTAINER:-normaai-app}"
BACKUP_HOST="${BACKUP_HOST:-normaai}"
BACKUP_TAG="normaai"
MAX_AGE_HOURS="${RESTORE_TEST_MAX_AGE_HOURS:-36}"
TEST_CONTAINER="normaai-restore-test-$$"
QDRANT_TEST_CONTAINER="normaai-restore-test-qdrant-$$"
QDRANT_FALLBACK_IMAGE="qdrant/qdrant:v1.20.0"
TEST_USER="normaai"
TEST_DB="normaai"
# Present since the first migrations: without them the dump is not the database.
REQUIRED_TABLES=(alembic_version organizations users)
# A rebuild cannot start without these in the copy of .env (docs/BACKUP_STRATEGY.md 6.3).
REQUIRED_SETTINGS=(APP_SECRET_KEY POSTGRES_PASSWORD APP_DB_PASSWORD LLM_PROVIDER)
WORK=""
PROBLEMS=0
REPORT=""
FAILURE=""
ALERT_ON_FAILURE=0
QDRANT_FILES=()
TIMINGS=""

log() { printf '[restore-test] %s\n' "$*"; }
warn() { printf '[restore-test] WARNING: %s\n' "$*" >&2; }
problem() {
  printf '[restore-test] PROBLEM: %s\n' "$*" >&2
  PROBLEMS=$((PROBLEMS + 1))
  REPORT="${REPORT}PROBLEM: $*"$'\n'
}
die() {
  printf '[restore-test] FAIL: %s\n' "$*" >&2
  FAILURE="$*"
  exit 1
}

# Tells the operator through the app container (src/ops_alerts.py), which holds
# the Resend key and the Sentry DSN. Away from the server there is none: the
# run then only says so.
alert_operator() {
  local summary="${FAILURE:-the restore test failed}" runner=()
  [ "${BACKUP_ALERTS:-1}" = "1" ] || return 0
  command -v docker > /dev/null 2>&1 || return 0
  if command -v timeout > /dev/null 2>&1; then runner=(timeout 120); fi
  if ! printf '%s' "${REPORT}FAIL: $summary" |
    "${runner[@]}" docker exec -i "$APP_CONTAINER" python -m src.ops_alerts restore-test "$summary" > /dev/null; then
    warn "the operator was not told of this failure (is $APP_CONTAINER running here?)"
  fi
}

cleanup() {
  docker rm -f -v "$QDRANT_TEST_CONTAINER" > /dev/null 2>&1 || true
  docker rm -f -v "$TEST_CONTAINER" > /dev/null 2>&1 || true
  # The work directory holds a copy of the database, the index and .env: never leave it.
  if [ -n "$WORK" ]; then
    rm -rf "$WORK"
  fi
}

on_exit() {
  local code=$?
  if [ "$code" -ne 0 ] && [ "$ALERT_ON_FAILURE" = "1" ]; then
    alert_operator
  fi
  cleanup
}

# Seconds since the start of a phase; adds "<phase> <seconds>s" to the timings.
PHASE_START=0
phase_start() { PHASE_START=$SECONDS; }
phase_end() { TIMINGS="${TIMINGS}${TIMINGS:+, }$1 $((SECONDS - PHASE_START))s"; }

# Reads JSON on stdin as `d` and runs the given Python expression statement.
json() { python3 -c 'import json, sys
d = json.load(sys.stdin)
'"$1"; }

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

# Prints the names among REQUIRED_SETTINGS (and the key of LLM_PROVIDER) that the
# env file on stdin lacks or leaves empty. Reads it as data: nothing in it runs.
missing_settings() { python3 -c 'import sys
values = {}
for raw in sys.stdin.read().splitlines():
    line = raw.strip()
    if line and not line.startswith("#") and "=" in line:
        name, _, value = line.partition("=")
        values[name.strip()] = value.strip().strip(chr(39) + chr(34))
keys = {"gemini": "GOOGLE_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
        "mistral": "MISTRAL_API_KEY", "openrouter": "OPENROUTER_API_KEY"}
wanted = list(sys.argv[1:])
if values.get("LLM_PROVIDER") in keys:
    wanted.append(keys[values["LLM_PROVIDER"]])
print(" ".join(name for name in wanted if not values.get(name)))
' "${REQUIRED_SETTINGS[@]}"; }

# ── 1. The latest copy ───────────────────────────────────────────────────────
restic_dump() { # <path in the snapshot> <file>
  restic dump --host "$BACKUP_HOST" --tag "$BACKUP_TAG" latest "$1" > "$2"
}

fetch_from_restic() {
  local snapshots newest listing dump_path index_files env_path manifest_path missing file name
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
    log "Qdrant snapshots in the copy:"
    printf '%s\n' "$index_files" | sed 's/^/[restore-test]   /'
  else
    problem "the latest snapshot holds no Qdrant snapshot: the index is not backed up"
  fi
  # Not grep -q: it stops at the first match, and under pipefail the writer it
  # cuts off could make a successful search look failed.
  env_path="$(printf '%s\n' "$listing" | grep -E '/config/env$' | head -n 1 || true)"
  if [ -n "$env_path" ]; then
    log "server configuration (.env) is in the copy"
    restic_dump "$env_path" "$WORK/env" || die "cannot extract the copy of .env from the snapshot"
    missing="$(missing_settings < "$WORK/env")" || die "cannot read the copy of .env"
    rm -f "$WORK/env"
    if [ -n "$missing" ]; then
      problem "the copy of .env lacks settings a rebuild needs: $missing"
    else
      log "the copy of .env names every setting a rebuild needs"
    fi
  else
    problem "the latest snapshot holds no copy of .env"
  fi
  manifest_path="$(printf '%s\n' "$listing" | grep -E '/MANIFEST\.txt$' | head -n 1 || true)"
  if [ -n "$manifest_path" ]; then
    restic_dump "$manifest_path" "$WORK/MANIFEST.txt" || warn "cannot extract MANIFEST.txt"
  fi
  restic_dump "$dump_path" "$WORK/normaai.dump" ||
    die "cannot extract the Postgres dump from the snapshot"
  if [ -n "$index_files" ] && [ "${RESTORE_TEST_QDRANT:-1}" = "1" ]; then
    mkdir -p "$WORK/qdrant"
    while IFS= read -r file; do
      name="$(basename "$file" .snapshot)"
      case "$name" in
        '' | *[!A-Za-z0-9_-]*) problem "unexpected snapshot name: $file"; continue ;;
      esac
      restic_dump "$file" "$WORK/qdrant/$name.snapshot" ||
        die "cannot extract the Qdrant snapshot of $name"
      QDRANT_FILES+=("$WORK/qdrant/$name.snapshot")
    done <<< "$index_files"
  fi
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

# ── 4. A throwaway Qdrant, and the index in it ───────────────────────────────
start_qdrant() {
  local image attempt
  image="$(docker inspect -f '{{.Config.Image}}' "$QDRANT_CONTAINER" 2>/dev/null || true)"
  image="${image:-$QDRANT_FALLBACK_IMAGE}"
  log "starting a throwaway $image ($QDRANT_TEST_CONTAINER, on 127.0.0.1 only)"
  # The upload needs the HTTP API: the image has no curl to call it from inside.
  docker run -d --name "$QDRANT_TEST_CONTAINER" -p 127.0.0.1::6333 \
    -e QDRANT__TELEMETRY_DISABLED=true "$image" > /dev/null ||
    die "cannot start the throwaway Qdrant"
  QDRANT_TEST_URL="http://$(docker port "$QDRANT_TEST_CONTAINER" 6333/tcp | head -n 1)"
  case "$QDRANT_TEST_URL" in
    http://127.0.0.1:[0-9]*) ;;
    *) die "cannot read the port of the throwaway Qdrant" ;;
  esac
  for attempt in $(seq 1 60); do
    if curl -fsS --max-time 5 "$QDRANT_TEST_URL/readyz" > /dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  die "the throwaway Qdrant was not ready after $attempt seconds"
}

# The number MANIFEST.txt recorded for a collection at backup time, or nothing.
expected_points() {
  [ -f "$WORK/MANIFEST.txt" ] || return 0
  sed -n "s/^collection $1: \([0-9][0-9]*\) points\$/\1/p" "$WORK/MANIFEST.txt" | head -n 1
}

restore_index() {
  local file name points expected
  for file in "${QDRANT_FILES[@]}"; do
    name="$(basename "$file" .snapshot)"
    log "loading the Qdrant snapshot of $name ($(($(wc -c < "$file") / 1048576)) MB)"
    if ! curl -fsS --max-time 1800 -X POST \
      "$QDRANT_TEST_URL/collections/$name/snapshots/upload?priority=snapshot&wait=true" \
      -F "snapshot=@$file" > /dev/null; then
      problem "the Qdrant snapshot of $name does not load"
      continue
    fi
    points="$(curl -fsS --max-time 30 "$QDRANT_TEST_URL/collections/$name" |
      json 'print(int(d["result"].get("points_count") or 0))')" || {
      problem "the restored collection $name does not answer"
      continue
    }
    expected="$(expected_points "$name")"
    if [ "$points" -eq 0 ]; then
      problem "the restored collection $name is empty"
    elif [ -n "$expected" ] && [ "$points" != "$expected" ]; then
      problem "the restored collection $name has $points points, the backup recorded $expected"
    else
      log "collection $name: $points points${expected:+, as recorded at backup time}"
    fi
  done
}

main() {
  case "$MAX_AGE_HOURS" in
    '' | *[!0-9]*) die "RESTORE_TEST_MAX_AGE_HOURS must be a whole number of hours" ;;
  esac
  umask 077
  WORK="$(mktemp -d)"
  local started=$SECONDS

  phase_start
  if [ -n "${RESTIC_REPOSITORY:-}" ] && [ -n "${RESTIC_PASSWORD_FILE:-}" ]; then
    fetch_from_restic
  elif [ -n "${RESTIC_REPOSITORY:-}" ] || [ -n "${RESTIC_PASSWORD_FILE:-}" ]; then
    die "set both RESTIC_REPOSITORY and RESTIC_PASSWORD_FILE (in $BACKUP_ENV_FILE), or neither"
  else
    fetch_local
  fi
  phase_end "copy"

  phase_start
  start_postgres
  restore_dump
  check_database
  phase_end "postgres"

  if [ "${#QDRANT_FILES[@]}" -gt 0 ]; then
    phase_start
    start_qdrant
    restore_index
    phase_end "qdrant"
  elif [ -n "${RESTIC_REPOSITORY:-}" ] && [ "${RESTORE_TEST_QDRANT:-1}" != "1" ]; then
    warn "RESTORE_TEST_QDRANT=0: the Qdrant snapshots were listed, not loaded"
  fi
  log "time: ${TIMINGS}; total $((SECONDS - started))s"

  if [ "$PROBLEMS" -gt 0 ]; then
    die "$PROBLEMS problem(s): the backup is not what a restore needs (see above)"
  fi
  if [ "${#QDRANT_FILES[@]}" -gt 0 ]; then
    log "PASSED: the latest backup loads into Postgres and Qdrant and holds what a restore needs"
  else
    log "PASSED: the latest backup loads into Postgres and holds what a restore needs"
  fi
}

case "${1:-}" in
  '')
    ALERT_ON_FAILURE=1
    trap on_exit EXIT
    main
    ;;
  -h | --help) sed -n '3,36p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' ;;
  *) die "unknown argument: $1 (see --help)" ;;
esac
