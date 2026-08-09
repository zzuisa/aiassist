#!/usr/bin/env bash
set -euo pipefail

validation_mode="${1:-run}"
validation_base_url="${BASE_URL:-https://llm.roguelife.de}"

if [ -z "${E2E_EMAIL:-}" ]; then
  read -r -p "验证账号邮箱: " E2E_EMAIL
  export E2E_EMAIL
fi

if [ -z "${E2E_PASSWORD:-}" ]; then
  read -r -s -p "验证账号密码: " E2E_PASSWORD
  printf '\n'
  export E2E_PASSWORD
fi

if [ -z "$E2E_EMAIL" ] || [ -z "$E2E_PASSWORD" ]; then
  printf '验证账号邮箱和密码不能为空。\n' >&2
  exit 2
fi

export BASE_URL="$validation_base_url"

printf '验证目标: %s\n' "$BASE_URL"
printf '流程: 健康检查 -> 鉴权 -> 只读 Agent 任务 -> SSE -> 终态报告\n'

case "$validation_mode" in
  run)
    npx playwright test --config=playwright.agent-validation.config.ts
    printf '报告已生成。运行 npm run verify:agent:report 查看。\n'
    ;;
  ui)
    npx playwright test --config=playwright.agent-validation.config.ts --ui
    ;;
  *)
    printf '用法: %s {run|ui}\n' "$0" >&2
    exit 2
    ;;
esac
