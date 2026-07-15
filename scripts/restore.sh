#!/bin/sh
# ============================================================
#  Telegram Marketing CRM — PostgreSQL restore
#  Restores a gzipped pg_dump produced by backup.sh.
#
#  Usage:
#    ./restore.sh /backups/telegram_crm-20260715-030000.sql.gz
#
#  Env: same POSTGRES_* / PGPASSWORD as backup.sh.
#  WARNING: this restores INTO the existing database. Stop the app first.
# ============================================================
set -eu

if [ "${1:-}" = "" ]; then
  echo "usage: $0 <backup-file.sql.gz>" >&2
  exit 2
fi
infile="$1"
if [ ! -f "$infile" ]; then
  echo "[restore] ERROR: file not found: $infile" >&2
  exit 1
fi

POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-crm}"
POSTGRES_DB="${POSTGRES_DB:-telegram_crm}"

echo "[restore] restoring ${infile} -> ${POSTGRES_DB} @ ${POSTGRES_HOST}:${POSTGRES_PORT}"
gunzip -c "$infile" \
  | psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1

echo "[restore] done"
