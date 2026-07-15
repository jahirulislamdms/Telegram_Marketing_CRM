#!/bin/sh
# ============================================================
#  Telegram Marketing CRM — PostgreSQL backup
#  Dumps the database with pg_dump, gzips it, and rotates old
#  backups. Designed to run inside the `backup` compose service
#  (which shares the Postgres network) or on the host.
#
#  Env:
#    POSTGRES_HOST      (default: postgres)
#    POSTGRES_PORT      (default: 5432)
#    POSTGRES_USER      (default: crm)
#    POSTGRES_DB        (default: telegram_crm)
#    PGPASSWORD         Postgres password (required)
#    BACKUP_DIR         (default: /backups)
#    BACKUP_RETENTION_DAYS  delete dumps older than this (default: 14)
# ============================================================
set -eu

POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-crm}"
POSTGRES_DB="${POSTGRES_DB:-telegram_crm}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

mkdir -p "$BACKUP_DIR"
timestamp="$(date -u +%Y%m%d-%H%M%S)"
outfile="$BACKUP_DIR/${POSTGRES_DB}-${timestamp}.sql.gz"

echo "[backup] dumping ${POSTGRES_DB} @ ${POSTGRES_HOST}:${POSTGRES_PORT} -> ${outfile}"
pg_dump -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  | gzip -9 > "$outfile"

# Fail loudly if the dump produced an empty/near-empty file.
if [ ! -s "$outfile" ]; then
  echo "[backup] ERROR: backup file is empty" >&2
  rm -f "$outfile"
  exit 1
fi

echo "[backup] wrote $(du -h "$outfile" | cut -f1) ${outfile}"

# Rotate: delete dumps older than the retention window.
find "$BACKUP_DIR" -name "${POSTGRES_DB}-*.sql.gz" -type f -mtime "+${BACKUP_RETENTION_DAYS}" -print -delete \
  | sed 's/^/[backup] pruned /' || true

echo "[backup] done"
