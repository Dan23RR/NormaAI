#!/usr/bin/env bash
# NormaAI - daily Postgres backup (Linux server variant of backup_postgres.ps1).
# Install on the Hetzner box:
#   chmod +x scripts/backup_postgres.sh
#   crontab -e   ->   0 2 * * * /opt/normaai/scripts/backup_postgres.sh >> /var/log/normaai-backup.log 2>&1
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${REPO_ROOT}/backups"
CONTAINER="normaai-postgres"
DB_USER="normaai"
DB_NAME="normaai"
RETENTION_DAYS=30

mkdir -p "${BACKUP_DIR}"
STAMP="$(date +%Y%m%d_%H%M%S)"
FILE="${BACKUP_DIR}/normaai_${STAMP}.dump"

echo "[backup] dumping ${DB_NAME} from ${CONTAINER} -> ${FILE}"
docker exec "${CONTAINER}" pg_dump -U "${DB_USER}" -d "${DB_NAME}" -Fc --no-owner > "${FILE}"

SIZE_KB=$(( $(stat -c%s "${FILE}") / 1024 ))
if [ "${SIZE_KB}" -lt 5 ]; then
    echo "[backup] FAIL: dump suspiciously small (${SIZE_KB} KB)" >&2
    exit 2
fi

# Integrity: pg_restore must be able to read the archive TOC.
docker exec -i "${CONTAINER}" pg_restore --list > /dev/null < "${FILE}"
echo "[backup] OK (${SIZE_KB} KB, verified)"

find "${BACKUP_DIR}" -name 'normaai_*.dump' -mtime "+${RETENTION_DAYS}" -print -delete |
    sed 's/^/[backup] pruned /'
