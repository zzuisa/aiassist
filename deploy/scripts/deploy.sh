#!/usr/bin/env bash
# AI Assist single-host deployment entry point. See deployment.md §9.
# Usage: ./deploy/scripts/deploy.sh {up|down|ps|logs|create-admin EMAIL}
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

SECRETS_DIR="deploy/secrets"
REQUIRED_SECRETS=(postgres_password jwt_signing_key rabbitmq_password)
RUNTIME_UID=10001

log() { printf '\033[1;34m[deploy]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[deploy]\033[0m %s\n' "$*" >&2; }

require_compose_v2() {
  if ! docker compose version >/dev/null 2>&1; then
    err "Docker Compose V2 is required (the 'docker compose' plugin)."
    exit 1
  fi
}

check_capacity() {
  local available_kb
  available_kb="$(df -Pk "$ROOT" | awk 'NR == 2 {print $4}')"
  if [ "${available_kb:-0}" -lt 5242880 ]; then
    err "At least 5 GiB of free disk space is required to build and deploy."
    exit 1
  fi
}

check_env_and_secrets() {
  [ -f .env ] || { err ".env is missing. Copy .env.example and edit it."; exit 1; }
  for s in "${REQUIRED_SECRETS[@]}"; do
    if [ ! -s "$SECRETS_DIR/$s" ]; then
      err "Required secret $SECRETS_DIR/$s is missing or empty."
      exit 1
    fi
  done
  # Optional secret files must exist for compose 'file:' sources; create empty
  # placeholders so absent features degrade instead of failing to configure.
  for s in smtp_password llm_provider_key s3_access_key s3_secret_key; do
    [ -f "$SECRETS_DIR/$s" ] || : > "$SECRETS_DIR/$s"
  done
  local secret_path
  for secret_path in "$SECRETS_DIR"/*_password "$SECRETS_DIR"/jwt_signing_key \
    "$SECRETS_DIR"/*_key; do
    [ -f "$secret_path" ] || continue
    chmod 600 "$secret_path"
    if [ "$(stat -c %u "$secret_path")" != "$RUNTIME_UID" ]; then
      if [ "$(id -u)" -eq 0 ]; then
        chown "$RUNTIME_UID" "$secret_path"
      else
        err "$secret_path must be owned by container UID $RUNTIME_UID and mode 0600."
        err "Run: sudo chown $RUNTIME_UID '$secret_path'"
        exit 1
      fi
    fi
  done
}

export_rabbitmq_pass() {
  # RabbitMQ's image needs the password as an env var; read it from the secret
  # file at runtime so it never lives in Git or compose.yaml.
  RABBITMQ_DEFAULT_PASS="$(tr -d '\n' < "$SECRETS_DIR/rabbitmq_password")"
  export RABBITMQ_DEFAULT_PASS
}

cmd_up() {
  require_compose_v2
  check_capacity
  check_env_and_secrets
  export_rabbitmq_pass
  log "Validating compose configuration..."
  docker compose config --quiet
  log "Pulling pinned middleware images..."
  docker compose pull postgres redis rabbitmq nginx
  log "Building application images..."
  docker compose build backend frontend
  log "Starting infrastructure..."
  docker compose up -d --wait --wait-timeout 180 postgres redis rabbitmq
  log "Running database migrations..."
  docker compose run --rm migrate
  log "Starting application processes..."
  docker compose up -d \
    frontend backend outbox-publisher worker-fast worker-heavy celery-beat nginx
  # Nginx resolves Compose service names when it starts. Restart it after any
  # backend/frontend recreation so it never retains a stale container IP.
  docker compose restart nginx
  docker compose up -d --wait --wait-timeout 180 \
    frontend backend outbox-publisher worker-fast worker-heavy celery-beat nginx
  log "Verifying gateway health..."
  docker compose exec -T backend \
    python -m app.cli.main healthcheck --url http://localhost:8000/health/ready
  docker compose exec -T worker-fast \
    celery -A app.workers.celery_app.celery inspect ping --destination "fast@$(docker compose exec -T worker-fast hostname)"
  docker compose exec -T worker-heavy \
    celery -A app.workers.celery_app.celery inspect ping --destination "heavy@$(docker compose exec -T worker-heavy hostname)"
  docker compose ps
  log "Done. Gateway on http://127.0.0.1:18080 (front the host Nginx per deployment.md)."
}

cmd_down() {
  require_compose_v2
  export_rabbitmq_pass 2>/dev/null || true
  # Never pass -v here: volumes (data) must survive an application stop.
  docker compose down
  log "Application stopped. Data volumes preserved."
}

cmd_create_admin() {
  local email="${1:-}"
  [ -n "$email" ] || { err "Usage: $0 create-admin EMAIL"; exit 2; }
  require_compose_v2
  check_env_and_secrets
  export_rabbitmq_pass
  docker compose run --rm backend python -m app.cli.main create-admin --email "$email"
}

case "${1:-}" in
  up)   cmd_up ;;
  down) cmd_down ;;
  ps)   export_rabbitmq_pass 2>/dev/null || true; docker compose ps ;;
  logs) export_rabbitmq_pass 2>/dev/null || true; shift || true; docker compose logs -f "$@" ;;
  create-admin) shift; cmd_create_admin "$@" ;;
  *)    err "Usage: $0 {up|down|ps|logs|create-admin EMAIL}"; exit 2 ;;
esac
