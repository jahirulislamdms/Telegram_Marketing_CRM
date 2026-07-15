#!/bin/sh
# ============================================================
#  Backup scheduler for the `backup` compose service.
#  Runs backup.sh immediately, then every BACKUP_INTERVAL_SECONDS
#  (default 86400 = daily). Uses a plain sleep loop so it needs no
#  cron daemon inside the container.
# ============================================================
set -eu

BACKUP_INTERVAL_SECONDS="${BACKUP_INTERVAL_SECONDS:-86400}"
SCRIPT_DIR="$(dirname "$0")"

echo "[backup-loop] starting; interval=${BACKUP_INTERVAL_SECONDS}s"
while true; do
  if sh "$SCRIPT_DIR/backup.sh"; then
    echo "[backup-loop] backup ok; sleeping ${BACKUP_INTERVAL_SECONDS}s"
  else
    echo "[backup-loop] backup FAILED; will retry after ${BACKUP_INTERVAL_SECONDS}s" >&2
  fi
  sleep "$BACKUP_INTERVAL_SECONDS"
done
