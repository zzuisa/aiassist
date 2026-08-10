---
name: speckit-git-commit
description: Commit changes before or after a Spec Kit command while enforcing emoji-prefixed commit types with concise Chinese descriptions. Use for Spec Kit Git hooks and whenever a Spec Kit workflow asks to generate or execute a commit.
---

# Commit Spec Kit Changes

## Workflow

1. Determine the hook event, such as `after_specify`, `before_plan`, or `after_implement`.
2. Read `.specify/extensions/git/git-config.yml` and honor the event-specific `enabled` value, falling back to `auto_commit.default` only when the event has no override.
3. Inspect the worktree and exclude unrelated user changes, credentials, generated artifacts, and accidental files.
4. Ensure the configured commit message follows the required format below. Correct a nonconforming generated message before committing.
5. When enabled and every worktree change belongs to the hook, run the platform script:
   - Bash: `.specify/extensions/git/scripts/bash/auto-commit.sh <event_name>`
   - PowerShell: `.specify/extensions/git/scripts/powershell/auto-commit.ps1 <event_name>`
   If unrelated changes exist, do not use the all-files script; stage only the intended paths and commit them directly.
6. Report the commit hash and subject.
7. After a successful commit, ask: “是否需要我 Review 一下这些修改，看看是不是补丁叠补丁式的修改；如果是，我可以将它重构成最优解？”

## Commit Message Format

Use `emoji + type: 简短中文描述`:

- `✨ feat: 新增 XXX 功能`
- `🐞 fix: 修复 XXX bug`
- `📃 docs: 增加/更新 XXX 文档`
- `🌈 style: 代码格式调整`
- `🦄 refactor: 重构 XXX`
- `🎈 perf: 优化 XXX 性能`
- `🧪 test: 增加 XXX 测试`
- `🔧 build: 更新依赖或构建配置`
- `🐎 ci: 更新 CI 配置`
- `🐳 chore: 更新其他杂项`
- `↩️ revert: 回滚 XXX`

Choose the primary outcome for a cohesive change. Split materially different outcomes into separate commits.

## Graceful Degradation

- Skip with a warning when Git, the repository, or the configuration is unavailable.
- Skip when the event is disabled or there are no in-scope changes.
- Never commit merely because this skill was loaded; require an enabled hook or an explicit user request.
