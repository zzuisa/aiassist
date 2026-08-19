# Implementation Plan: 集中 Prompt 与 Skill 管理

**Branch**: `010-prompt-skill-management` | **Date**: 2026-08-14 | **Spec**: [spec.md](./spec.md)

## Summary

建立统一、用户所有且版本不可变的 AI 配置中心：每个 LLM 场景获得一个模块定义和可回退的 Prompt 基线；模块 Skill 保存业务指令、允许工具与参数默认值。每次调用在执行前绑定生效版本。对话 Agent 改为让模型在 schema 约束下产生工具调用参数，现有确定性 intent 仅作为模型不可用时的安全回退，不再要求“最近文章”指定数量。

## Technical Context

**Language/Version**: Python 3.12；TypeScript 5.7；Node 24  
**Primary Dependencies**: FastAPI、SQLAlchemy/Alembic、Vue 3、Pinia、Vue Router、Pydantic、Vitest、Playwright  
**Storage**: PostgreSQL；新增 AI 模块配置、Prompt 版本、Skill 版本、运行绑定记录，迁移既有博客 Skill 引用  
**Testing**: 后端单元/契约/集成测试、前端组件测试与 Agent E2E  
**Target Platform**: 现有 Docker Compose 单机部署  
**Performance Goals**: 配置解析不新增网络往返；正常 Agent 首次路由维持一次模型调用；配置读取在单次运行内固定  
**Constraints**: 所有权、schema、工具权限、限额、写入确认及凭据隔离不可配置；历史运行可追溯  

## Constitution Check

| Gate | Result | Notes |
|---|---|---|
| Durable Capture Before Intelligence | PASS | 配置和任务均在调用前持久化、运行绑定不可变。 |
| Human Authority | PASS | 只读调用可自动执行，写入仍走确认。 |
| Operational Simplicity | PASS | 使用一个通用配置域模型，不为每个场景复制表或 UI。 |
| Validated AI | PASS | 每个模型输出继续经过 Pydantic schema 与工具 schema 校验。 |
| Reliable Async Work | PASS | 复用 Job/Run，配置版本在入队前绑定。 |
| Privacy and Least Privilege | PASS | 配置按用户隔离，Prompt 不含凭据；安全前缀不可编辑。 |
| Contract/Test First | PASS | 先覆盖 Agent 默认参数、版本绑定、权限拒绝与试运行。 |
| Observability | PASS | 记录模块/版本/错误类别，不记录原始提示或推理。 |

## Design

1. 建立 `AIConfigModule` 静态目录（模块 key、标题、输入/输出 schema、强制安全前缀、支持工具），并由 `AIConfigProfile`、不可变 `AIPromptVersion`、不可变 `AISkillVersion` 存储每位用户的版本化覆盖；不存在覆盖时按相同模型读取基线版本。
2. 配置服务解析优先级为：运行显式绑定 → 用户已启用模块 Skill/Prompt → 受版本管理的基线。保存时验证模块兼容性、长度、schema、注册工具及默认参数；强制安全前缀由服务拼接，不能由编辑器传入或覆盖。
3. 为每次调用创建 `AIConfigBinding`（模块、Prompt/Skill 版本、模型、运行关联）；Blog 的既有 `BlogSkillVersion` 保持历史可读，并适配/迁移到统一 Skill 引用，不破坏现有默认作用域。
4. 新增 AI 配置中心 API 与前端：模块列表、版本详情、草稿保存/启用/回退、只读 dry-run 和运行绑定查询。复用现有 Blog Skill 页面组件和版本交互模式。
5. 对话路由的结构化 schema 扩展为 `tool_calls`（至多一个首期调用），模型读取适用文章查询 Skill；调用 `posts.list_recent` 时 `limit` 可选，Skill 默认值为 10。工具注册表保持最终参数 schema、上限和权限校验。
6. 把现有静态 Prompt 迁入模块基线：conversation_route、agent_content_analysis、quick_plan、voice_task_parse、capture_analysis、blog_generate、blog_optimize、blog_skill_test。网关继续注入输出 JSON Schema。

## Project Structure

```text
backend/
├── alembic/versions/
├── app/models/ai_config.py
├── app/modules/ai_config/{catalog.py,schemas.py,service.py,router.py}
├── app/modules/agent/{conversation_router.py,conversation_schemas.py,registry.py,intents.py}
└── app/{workers/tasks/blog.py,workers/tasks/capture_ai.py,modules/tasks/plan_service.py,modules/voice/service.py}
frontend/
├── src/api/aiConfig.ts
├── src/modules/settings/AIConfigPage.vue
└── src/router/index.ts
```

## Post-design Constitution Check

PASS. Prompt editing is deliberately constrained by deterministic platform policy and all write authority remains unchanged.
