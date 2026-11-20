#!/usr/bin/env bash
# Old name of the nightly backup, kept so that a crontab or a guide that still
# calls it keeps working. The backup itself is scripts/backup.sh: Postgres as
# before and, when restic is configured, the Qdrant index and .env, encrypted
# and off the server (docs/BACKUP_STRATEGY.md).
set -euo pipefail
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/backup.sh" "$@"
