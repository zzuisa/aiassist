#!/usr/bin/env bash
# AI Assist single-host deployment entry point. See deployment.md §9.
# Usage: ./deploy/scripts/deploy.sh {up|down|ps|logs}
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

SECRETS_DIR="deploy/secrets"
REQUIRED_SECRETS=(postgres_password jwt_signing_key rabbitmq_password)

log() { printf '\033[1;34m[deploy]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[deploy]\033[0m %s\n' "$*" >&2; }

require_compose_v2() {
  if ! docker compose version >/dev/null 2>&1; then
    err "Docker Compose V2 is required (the 'docker compose' plugin)."
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
}

export_rabbitmq_pass() {
  # RabbitMQ's image needs the password as an env var; read it from the secret
  # file at runtime so it never lives in Git or compose.yaml.
  RABBITMQ_DEFAULT_PASS="$(tr -d '\n' < "$SECRETS_DIR/rabbitmq_password")"
  export RABBITMQ_DEFAULT_PASS
}

cmd_up() {
  require_compose_v2
  check_env_and_secrets
  export_rabbitmq_pass
  log "Validating compose configuration..."
  docker compose config --quiet
  log "Pulling pinned middleware images..."
  docker compose pull postgres redis rabbitmq nginx
  log "Building application images..."
  docker compose build backend frontend
  log "Starting infrastructure..."
  docker compose up -d postgres redis rabbitmq
  log "Running database migrations..."
  docker compose run --rm migrate
  log "Starting application processes..."
  docker compose up -d frontend backend outbox-publisher worker-fast worker-heavy celery-beat nginx
  log "Waiting for readiness..."
  sleep 5
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

case "${1:-}" in
  up)   cmd_up ;;
  down) cmd_down ;;
  ps)   export_rabbitmq_pass 2>/dev/null || true; docker compose ps ;;
  logs) export_rabbitmq_pass 2>/dev/null || true; shift || true; docker compose logs -f "$@" ;;
  *)    err "Usage: $0 {up|down|ps|logs}"; exit 2 ;;
esac
