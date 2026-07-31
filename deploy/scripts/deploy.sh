#!/usr/bin/env bash
# AI Assist single-host deployment entry point. See deployment.md §9.
# Usage: ./deploy/scripts/deploy.sh {up|down|ps|logs|create-admin EMAIL}
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

SECRETS_DIR="deploy/secrets"
REQUIRED_SECRETS=(postgres_password jwt_signing_key rabbitmq_password radio_service_password)
RUNTIME_UID=10001
RELEASE_HISTORY_FILE="frontend/public/release-history.json"
RELEASE_PUSH_REMOTE="${DEPLOY_PUSH_REMOTE:-origin}"

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

ensure_log_dirs() {
  # Create per-service log directories under /www/wwwlogs/aiassist/ and make
  # them world-writable so containers (uid 10001 backend, root nginx) can write
  # without requiring a matching host user.
  local log_root="/www/wwwlogs/aiassist"
  for svc in backend outbox-publisher worker-fast worker-heavy celery-beat nginx; do
    mkdir -p "$log_root/$svc"
  done
  # nginx writes directly into log_root/nginx
  mkdir -p "$log_root/nginx"
  chmod -R 777 "$log_root"
  log "Log directories ready under $log_root"
}

push_current_branch() {
  if git rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then
    git push "$RELEASE_PUSH_REMOTE" HEAD
  else
    git push --set-upstream "$RELEASE_PUSH_REMOTE" HEAD
  fi
}

prepare_release_commit() {
  local release_version release_id deployed_at commit_message source_commit source_short changed_files
  release_version="$(date -u +%Y.%m.%d.%H%M%S)"
  release_id="${release_version}-pending"
  deployed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  commit_message="${DEPLOY_COMMIT_MESSAGE:-deploy: update ${release_version}}"

  git diff --check
  if [ -n "$(git status --porcelain)" ]; then
    git add --all
    git commit -m "$commit_message"
  else
    git commit --allow-empty -m "$commit_message"
  fi
  source_commit="$(git rev-parse HEAD)"
  source_short="$(git rev-parse --short HEAD)"
  release_id="${release_version}-${source_short}"
  changed_files="$(git show --format= --name-only HEAD | sed '/^$/d')"
  log "Pushing source commit $source_short..."
  push_current_branch

  python3 - "$RELEASE_HISTORY_FILE" "$release_id" "$release_version" \
    "$source_commit" "$source_short" "$commit_message" "$deployed_at" "$changed_files" <<'PY'
import json
import sys
from pathlib import Path

history_path = Path(sys.argv[1])
release_id, version, commit, commit_short, message, deployed_at, changed_files_arg = sys.argv[2:]
changed_files = [line.strip() for line in changed_files_arg.splitlines() if line.strip()]

categories = []
if any(path.startswith("frontend/") for path in changed_files):
    categories.append("前端界面与交互更新")
if any(path.startswith("backend/") for path in changed_files):
    categories.append("后端接口与业务逻辑更新")
if any(path.startswith(("specs/", "docs/")) for path in changed_files):
    categories.append("规格与文档更新")
if any(path.startswith(("deploy/", "compose.yaml")) for path in changed_files):
    categories.append("部署与运行配置更新")
if not categories:
    categories.append("部署版本与运行状态更新")

entry = {
    "id": release_id,
    "version": version,
    "commit": commit,
    "commit_short": commit_short,
    "message": message,
    "changes": [message, *categories],
    "changed_files": changed_files[:100],
    "deployed_at": deployed_at,
    "environment": "production",
    "git_pushed": True,
    "deployment_status": "verified",
    "migration_head": None,
}

try:
    current = json.loads(history_path.read_text(encoding="utf-8"))
except (FileNotFoundError, json.JSONDecodeError):
    current = {"releases": []}
releases = [item for item in current.get("releases", []) if item.get("id") != release_id]
history_path.parent.mkdir(parents=True, exist_ok=True)
history_path.write_text(
    json.dumps({"releases": [entry, *releases[:49]]}, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY

  git add "$RELEASE_HISTORY_FILE"
  git commit -m "release: ${release_version}"
  log "Pushing release history..."
  push_current_branch
}

cmd_up() {
  require_compose_v2
  check_capacity
  check_env_and_secrets
  export_rabbitmq_pass
  ensure_log_dirs
  log "Validating compose configuration..."
  docker compose config --quiet
  prepare_release_commit
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
