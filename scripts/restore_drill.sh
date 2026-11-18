#!/usr/bin/env bash
# ============================================================================
# NormaAI - restore drill: read the backups back WITHOUT the server and its
# hosting account, with only what the password manager holds. In September 2026
# the whole hosting account was lost: a backup that only the server could open
# would have gone with it. Run it every three months, and after any change of
# the repository, its password or its storage key (docs/BACKUP_STRATEGY.md,
# section 6.4).
#
# On a machine that is NOT the server (a laptop with Docker, or a fresh VM at
# another provider), with bash, docker, restic, curl and python3, from a clone
# of the repository:
#
#   export RESTIC_REPOSITORY='s3:https://<endpoint>/<bucket>'          # password manager
#   export AWS_ACCESS_KEY_ID='<key id>' AWS_SECRET_ACCESS_KEY='<key>'   # S3 only
#   bash scripts/restore_drill.sh
#
# It asks for the repository password (not echoed), unless RESTIC_PASSWORD_FILE
# names a file you wrote from the password manager. Then it runs
# scripts/restore_test.sh without the server's settings (no BACKUP_ENV_FILE, no
# alert): the latest snapshot, restic check, the copy of .env and the settings
# it names, the Postgres dump in a throwaway Postgres, every Qdrant snapshot in
# a throwaway Qdrant, the time of each phase. The age limit is
# RESTORE_DRILL_MAX_AGE_HOURS (default 36, as on the server).
# It ends with the checklist of what a real rebuild adds, to time the rest.
# Nothing stays on this machine: the password and the copy are in a temporary
# folder that is removed at the end, and the throwaway containers too.
# Exit status: the restore test's (0 when every check passed).
# ============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Present on the production server only (the bootstrap writes it).
SERVER_MARK="${RESTORE_DRILL_SERVER_MARK:-/etc/normaai/backup.env}"
WORK=""

log() { printf '[restore-drill] %s\n' "$*"; }
die() {
  printf '[restore-drill] FAIL: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  if [ -n "$WORK" ]; then
    rm -rf "$WORK"
  fi
}

checklist() {
  cat << 'EOF'
[restore-drill] What a real rebuild adds (docs/BACKUP_STRATEGY.md, section 6.3).
[restore-drill] Time each step in the drill, or estimate it, and write it down:
[restore-drill]   [ ] a new server at the provider (DEPLOY_CHECKLIST.md, step 1)     ____ min
[restore-drill]   [ ] the DNS record of the API (step 2)                             ____ min
[restore-drill]   [ ] restic restore on the new server, .env and snapshots in place  ____ min
[restore-drill]   [ ] the bootstrap with SKIP_FIRST_BACKUP=1                         ____ min
[restore-drill]   [ ] the database load (section 6.2), a backup, the restore test    ____ min
[restore-drill]   [ ] the final test (DEPLOY_CHECKLIST.md, step 9)                   ____ min
[restore-drill] Then the date, the times and the outcome in the post-mortem log of docs/RUNBOOK.md.
EOF
}

main() {
  local tool password status=0
  if [ -f "$SERVER_MARK" ] && [ "${RESTORE_DRILL_ON_SERVER:-0}" != "1" ]; then
    die "this looks like the production server ($SERVER_MARK): the drill proves something only away from it (RESTORE_DRILL_ON_SERVER=1 to run it anyway)"
  fi
  for tool in docker restic curl python3; do
    command -v "$tool" > /dev/null 2>&1 || die "$tool is needed on this machine"
  done
  [ -n "${RESTIC_REPOSITORY:-}" ] ||
    die "export RESTIC_REPOSITORY, and the storage keys, from the password manager"

  umask 077
  WORK="$(mktemp -d)"
  trap cleanup EXIT
  if [ -z "${RESTIC_PASSWORD_FILE:-}" ]; then
    [ -t 0 ] || die "no terminal to ask for the repository password: set RESTIC_PASSWORD_FILE"
    read -r -s -p "[restore-drill] restic repository password (from the password manager): " password
    printf '\n'
    [ -n "$password" ] || die "empty password"
    printf '%s' "$password" > "$WORK/password"
    password=""
    RESTIC_PASSWORD_FILE="$WORK/password"
  fi
  [ -s "$RESTIC_PASSWORD_FILE" ] || die "RESTIC_PASSWORD_FILE ($RESTIC_PASSWORD_FILE) is missing or empty"
  export RESTIC_REPOSITORY RESTIC_PASSWORD_FILE

  log "repository from the environment, password from outside the server: running the restore test"
  BACKUP_ENV_FILE="$WORK/no-server-settings" BACKUP_ALERTS=0 \
    RESTORE_TEST_MAX_AGE_HOURS="${RESTORE_DRILL_MAX_AGE_HOURS:-36}" \
    bash "$REPO_ROOT/scripts/restore_test.sh" || status=$?
  if [ "$status" -eq 0 ]; then
    log "PASSED: the backups open and load with the keys kept off the server"
  else
    log "FAILED: see the restore test above; fix it before you need the backups"
  fi
  checklist
  return "$status"
}

case "${1:-}" in
  '') main ;;
  -h | --help) sed -n '3,28p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' ;;
  *) die "unknown argument: $1 (see --help)" ;;
esac
