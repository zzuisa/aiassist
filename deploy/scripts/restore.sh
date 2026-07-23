#!/usr/bin/env bash
# AI Assist restore: verify manifest/checksums, then pg_restore + assets.
# Usage: restore.sh <backup-dir>
set -euo pipefail

DIR="${1:?usage: restore.sh <backup-dir>}"
ASSET_ROOT="${ASSET_ROOT:-/data/assets}"
PGHOST="${POSTGRES_HOST:-postgres}"
PGUSER="${POSTGRES_USER:-aiassist}"
PGDB="${POSTGRES_DB:-aiassist}"
export PGPASSWORD="$(cat /run/secrets/postgres_password 2>/dev/null || echo "${POSTGRES_PASSWORD:-}")"

[ -f "${DIR}/manifest.json" ] || { echo "manifest.json missing" >&2; exit 1; }

echo "[restore] verifying checksums..."
EXPECT_DB="$(grep -o '"database_sha256": *"[^"]*"' "${DIR}/manifest.json" | cut -d'"' -f4)"
ACTUAL_DB="$(sha256sum "${DIR}/database.dump" | awk '{print $1}')"
[ "$EXPECT_DB" = "$ACTUAL_DB" ] || { echo "database checksum mismatch" >&2; exit 1; }

if [ -f "${DIR}/assets.tar.gz" ]; then
  EXPECT_A="$(grep -o '"assets_sha256": *"[^"]*"' "${DIR}/manifest.json" | cut -d'"' -f4)"
  ACTUAL_A="$(sha256sum "${DIR}/assets.tar.gz" | awk '{print $1}')"
  [ "$EXPECT_A" = "$ACTUAL_A" ] || { echo "assets checksum mismatch" >&2; exit 1; }
fi

echo "[restore] restoring database (clean)..."
pg_restore --clean --if-exists -h "$PGHOST" -U "$PGUSER" -d "$PGDB" "${DIR}/database.dump"

if [ -f "${DIR}/assets.tar.gz" ]; then
  echo "[restore] restoring assets..."
  mkdir -p "$ASSET_ROOT"
  tar -xzf "${DIR}/assets.tar.gz" -C "$ASSET_ROOT"
fi

echo "[restore] applying current migrations..."
cd /app && python -m app.cli.main migrate

echo "[restore] done. Run smoke tests (login, task save, asset read, SSE)."
