#!/usr/bin/env bash
# AI Assist single-host deployment entry point. See deployment.md §9.
# Usage: ./deploy/scripts/deploy.sh {up|fast-up|restart|down|ps|logs|create-admin EMAIL}
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

SECRETS_DIR="deploy/secrets"
REQUIRED_SECRETS=(postgres_password jwt_signing_key rabbitmq_password radio_service_password)
RUNTIME_UID=10001
RELEASE_HISTORY_FILE="frontend/public/release-history.json"
RELEASE_PUSH_REMOTE="${DEPLOY_PUSH_REMOTE:-origin}"
APP_SERVICES=(frontend backend outbox-publisher worker-fast worker-heavy celery-beat nginx)
REDEPLOY_SERVICES=(frontend backend outbox-publisher worker-fast worker-heavy celery-beat)

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
  for s in smtp_password llm_provider_key s3_access_key s3_secret_key mcp_connections.json; do
    [ -f "$SECRETS_DIR/$s" ] || : > "$SECRETS_DIR/$s"
  done
  local secret_path
  for secret_path in "$SECRETS_DIR"/*_password "$SECRETS_DIR"/jwt_signing_key \
    "$SECRETS_DIR"/*_key "$SECRETS_DIR"/mcp_connections.json; do
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
  # Keep AI Assist file logs on the dedicated observability disk rather than
  # the host root volume. Containers need a shared, writable log root.
  # them world-writable so containers (uid 10001 backend, root nginx) can write
  # without requiring a matching host user.
  local log_root="/mnt/docker-ext4/observability/aiassist/logs"
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
  commit_message="${DEPLOY_COMMIT_MESSAGE:-🐳 chore: 更新部署版本 ${release_version}}"

  git diff --check
  if [ -n "$(git status --porcelain)" ]; then
    git add --all
    git commit -m "$commit_message [skip ci]"
  else
    git commit --allow-empty -m "$commit_message [skip ci]"
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
history_path.chmod(0o644)
PY

  git add "$RELEASE_HISTORY_FILE"
  git commit -m "🐳 chore: 更新发布记录 ${release_version}"
  log "Pushing release history..."
  push_current_branch
}

prepare_fast_deploy_commit() {
  local commit_message
  commit_message="${DEPLOY_COMMIT_MESSAGE:-🐳 chore: 快速部署最新代码}"

  git diff --check
  if [ -n "$(git status --porcelain)" ]; then
    git add --all
    git commit -m "$commit_message"
  else
    log "Working tree is clean; reusing commit $(git rev-parse --short HEAD)."
  fi
  log "Pushing source commit $(git rev-parse --short HEAD); CI will run asynchronously..."
  push_current_branch
}

wait_for_ci_gate() {
  if [ "${DEPLOY_SKIP_CI_GATE:-0}" = "1" ]; then
    log "CI gate explicitly skipped by DEPLOY_SKIP_CI_GATE=1."
    return
  fi
  if ! command -v gh >/dev/null 2>&1; then
    err "GitHub CLI is required to verify CI before deployment."
    exit 1
  fi
  if ! gh auth status >/dev/null 2>&1; then
    err "GitHub CLI is not authenticated; refusing to deploy without a CI result."
    exit 1
  fi

  local workflow head_sha run_id started_at now timeout_seconds
  workflow="${DEPLOY_CI_WORKFLOW:-CI}"
  timeout_seconds="${DEPLOY_CI_TIMEOUT_SECONDS:-1800}"
  head_sha="$(git rev-parse HEAD)"
  started_at="$(date +%s)"
  run_id=""
  log "Waiting for CI workflow '$workflow' on commit ${head_sha:0:7}..."
  while [ -z "$run_id" ]; do
    run_id="$(gh run list \
      --workflow "$workflow" \
      --commit "$head_sha" \
      --event push \
      --limit 1 \
      --json databaseId \
      --jq '.[0].databaseId // empty')"
    if [ -n "$run_id" ]; then
      break
    fi
    now="$(date +%s)"
    if [ $((now - started_at)) -ge "$timeout_seconds" ]; then
      err "Timed out waiting for CI to start for commit ${head_sha:0:7}."
      exit 1
    fi
    sleep 5
  done
  if ! gh run watch "$run_id" --exit-status; then
    err "CI failed for commit ${head_sha:0:7}; image build and deployment stopped."
    exit 1
  fi
  log "CI passed for commit ${head_sha:0:7}."
}

check_backend_health() {
  docker compose exec -T backend \
    python -m app.cli.main healthcheck --url http://localhost:8000/health/ready
}

check_frontend_health() {
  docker compose exec -T frontend wget -qO- http://127.0.0.1/
}

check_gateway_health() {
  docker compose exec -T backend \
    python -m app.cli.main healthcheck --url http://nginx/health/ready
}

check_worker_health() {
  local service="$1"
  local node_name="$2"
  local container_hostname
  container_hostname="$(docker compose exec -T "$service" hostname)" || return 1
  docker compose exec -T "$service" \
    celery -A app.workers.celery_app.celery inspect ping \
    --destination "${node_name}@${container_hostname}"
}

check_fast_worker_health() {
  check_worker_health worker-fast fast
}

check_heavy_worker_health() {
  check_worker_health worker-heavy heavy
}

wait_for_check() {
  local label="$1"
  shift
  local timeout_seconds="${DEPLOY_HEALTH_TIMEOUT_SECONDS:-180}"
  local deadline=$(( $(date +%s) + timeout_seconds ))

  until "$@" >/dev/null 2>&1; do
    if [ "$(date +%s)" -ge "$deadline" ]; then
      err "Timed out after ${timeout_seconds}s waiting for ${label}."
      "$@" || true
      return 1
    fi
    sleep 2
  done
  log "${label} is healthy."
}

verify_application_health() {
  log "Verifying application health..."
  wait_for_check "backend" check_backend_health
  wait_for_check "frontend" check_frontend_health
  wait_for_check "worker-fast" check_fast_worker_health
  wait_for_check "worker-heavy" check_heavy_worker_health
  wait_for_check "nginx gateway" check_gateway_health
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
  wait_for_ci_gate
  log "Pulling pinned middleware images..."
  docker compose pull postgres redis rabbitmq nginx
  log "Building application images..."
  docker compose build backend frontend
  log "Starting infrastructure..."
  docker compose up -d --wait --wait-timeout 180 postgres redis rabbitmq
  log "Running database migrations..."
  docker compose run --rm migrate
  log "Starting application processes..."
  docker compose up -d "${APP_SERVICES[@]}"
  # Nginx resolves Compose service names when it starts. Restart it after any
  # backend/frontend recreation so it never retains a stale container IP.
  docker compose restart nginx
  docker compose up -d --wait --wait-timeout 180 "${APP_SERVICES[@]}"
  verify_application_health
  docker compose ps
  log "Done. Gateway on http://127.0.0.1:18080 (front the host Nginx per deployment.md)."
}

cmd_fast_up() {
  require_compose_v2
  check_capacity
  check_env_and_secrets
  export_rabbitmq_pass
  ensure_log_dirs
  log "Validating compose configuration..."
  docker compose config --quiet

  local service
  for service in postgres redis rabbitmq "${APP_SERVICES[@]}"; do
    if [ -z "$(docker compose ps --all --quiet "$service")" ]; then
      err "Service '$service' has no existing container; run '$0 up' first."
      exit 1
    fi
  done

  prepare_fast_deploy_commit
  log "Fast deploy: building application images with Docker cache..."
  docker compose build backend frontend
  log "Fast deploy: applying database migrations without restarting infrastructure..."
  docker compose run --rm --no-deps migrate
  log "Fast deploy: recreating application containers only..."
  docker compose up -d --no-deps --force-recreate "${REDEPLOY_SERVICES[@]}"
  # Re-resolve backend/frontend container IPs after their recreation.
  docker compose restart nginx
  verify_application_health
  docker compose ps
  log "Fast deploy complete. CI continues asynchronously on GitHub."
}

cmd_restart() {
  require_compose_v2
  check_env_and_secrets
  export_rabbitmq_pass
  ensure_log_dirs
  log "Validating compose configuration..."
  docker compose config --quiet

  local service
  for service in "${APP_SERVICES[@]}"; do
    if [ -z "$(docker compose ps --all --quiet "$service")" ]; then
      err "Service '$service' has no existing container; run '$0 up' first."
      exit 1
    fi
  done

  log "Restarting existing application containers (no Git, CI, pull, build, or migration)..."
  docker compose restart "${APP_SERVICES[@]}"
  verify_application_health
  docker compose ps
  log "Restart complete. Existing images and configuration were preserved."
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

cmd_issue_blog_mcp_token() {
  local email="${1:-}"
  local days="${2:-30}"
  [ -n "$email" ] || {
    err "Usage: $0 issue-blog-mcp-token EMAIL [DAYS]"
    exit 2
  }
  require_compose_v2
  check_env_and_secrets
  export_rabbitmq_pass
  docker compose exec -T backend \
    python -m app.cli.main issue-blog-mcp-token --email "$email" --days "$days"
}

case "${1:-}" in
  up)      cmd_up ;;
  fast-up) cmd_fast_up ;;
  restart) cmd_restart ;;
  down)    cmd_down ;;
  ps)      export_rabbitmq_pass 2>/dev/null || true; docker compose ps ;;
  logs)    export_rabbitmq_pass 2>/dev/null || true; shift || true; docker compose logs -f "$@" ;;
  create-admin) shift; cmd_create_admin "$@" ;;
  issue-blog-mcp-token) shift; cmd_issue_blog_mcp_token "$@" ;;
  *) err "Usage: $0 {up|fast-up|restart|down|ps|logs|create-admin EMAIL|issue-blog-mcp-token EMAIL [DAYS]}"; exit 2 ;;
esac
