#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this repair with sudo." >&2
  exit 1
fi

DB=/var/lib/cryptogotchi/cryptogotchi.db
SERVICE=cryptogotchi.service

if [[ ! -f "$DB" ]]; then
  echo "Database not found: $DB" >&2
  exit 1
fi

systemctl stop "$SERVICE" 2>/dev/null || true
STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP="$DB.backup-before-v0.6.1-$STAMP"
cp -a "$DB" "$BACKUP"
echo "Backup created: $BACKUP"

has_column() {
  local column=$1
  sqlite3 "$DB" "PRAGMA table_info(price_samples);" | awk -F'|' -v c="$column" '$2==c {found=1} END {exit found?0:1}'
}

if ! has_column quote_currency; then
  sqlite3 "$DB" "ALTER TABLE price_samples ADD COLUMN quote_currency TEXT NOT NULL DEFAULT '';"
  echo "Added price_samples.quote_currency"
fi

if ! has_column source; then
  sqlite3 "$DB" "ALTER TABLE price_samples ADD COLUMN source TEXT NOT NULL DEFAULT 'coingecko';"
  echo "Added price_samples.source"
fi

sqlite3 "$DB" \
  "CREATE INDEX IF NOT EXISTS idx_price_coin_quote_source_ts ON price_samples(coin_id, quote_currency, source, ts);"
chown cryptogotchi:cryptogotchi "$DB" "$DB-wal" "$DB-shm" 2>/dev/null || true

systemctl daemon-reload
systemctl reset-failed "$SERVICE" || true
systemctl restart "$SERVICE"
sleep 5
systemctl --no-pager --full status "$SERVICE"
