#!/usr/bin/env bash
# AI Assist backup: PostgreSQL custom-format dump + assets + manifest/checksums.
# Redis/RabbitMQ/Celery state is NOT authoritative and is not backed up.
set -euo pipefail

TS="$(date +%Y%m%d-%H%M%S)"
BACKUP_ROOT="${BACKUP_ROOT:-/data/backups}"
ASSET_ROOT="${ASSET_ROOT:-/data/assets}"
OUT="${BACKUP_ROOT}/${TS}"
mkdir -p "$OUT"

PGHOST="${POSTGRES_HOST:-postgres}"
PGUSER="${POSTGRES_USER:-aiassist}"
PGDB="${POSTGRES_DB:-aiassist}"
export PGPASSWORD="$(cat /run/secrets/postgres_password 2>/dev/null || echo "${POSTGRES_PASSWORD:-}")"

echo "[backup] dumping database ${PGDB}..."
pg_dump -Fc -h "$PGHOST" -U "$PGUSER" "$PGDB" -f "${OUT}/database.dump"

echo "[backup] copying assets..."
if [ -d "$ASSET_ROOT" ]; then
  tar -czf "${OUT}/assets.tar.gz" -C "$ASSET_ROOT" .
fi

echo "[backup] writing manifest + checksums..."
DB_SHA="$(sha256sum "${OUT}/database.dump" | awk '{print $1}')"
ASSET_SHA="$( [ -f "${OUT}/assets.tar.gz" ] && sha256sum "${OUT}/assets.tar.gz" | awk '{print $1}' || echo "none")"
ASSET_COUNT="$( [ -d "$ASSET_ROOT" ] && find "$ASSET_ROOT" -type f | wc -l || echo 0)"
MIGRATION_HEAD="$(
  psql -At -h "$PGHOST" -U "$PGUSER" -d "$PGDB" \
    -c "SELECT version_num FROM alembic_version LIMIT 1" 2>/dev/null || echo unknown
)"

cat > "${OUT}/manifest.json" <<EOF
{
  "created_at": "${TS}",
  "app": "aiassist",
  "database_dump": "database.dump",
  "database_sha256": "${DB_SHA}",
  "assets_archive": "assets.tar.gz",
  "assets_sha256": "${ASSET_SHA}",
  "asset_count": ${ASSET_COUNT},
  "migration_head": "${MIGRATION_HEAD}"
}
EOF

echo "[backup] done: ${OUT}"
echo "[backup] IMPORTANT: copy ${OUT} to an off-host, encrypted destination."
