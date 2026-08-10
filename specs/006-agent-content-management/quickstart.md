# Quickstart: 博客 Agent 内容管理验收

## Prerequisites

- PostgreSQL、Redis、RabbitMQ、backend、frontend、worker-fast 和 worker-heavy 按现有 Compose 启动。
- 执行 Alembic upgrade 到 `0019_blog_agent_content_management`。
- 准备用户 A、用户 B；用户 A 至少有一篇私有文章与默认 Blog Skill。
- 测试环境使用 Fake LLM provider；能力注册准备 `visualize=available`、`answers-charts=disabled`、`imagegen=unknown` 三种状态。

## Contract Gate

1. 校验 `blog-agent-config.v1.json` 与 `blog-orchestration-snapshot.v1.json` 的正反样本。
2. 校验 OpenAPI/AsyncAPI 可解析且实现路由、DTO 和消息字段无漂移。
3. 校验 manifest 节点/边引用、DAG、stage order 和所有生产路径经过 quality-validator/candidate-save。
4. 验证能力公开响应不包含 endpoint、headers、token、token_file、Cookie、private key 字段。

## Scenario 1: 理解执行结构（US1）

1. 用户 A 打开 `/blog/agents`。
2. 验证顺序为输入/Skill 匹配、总控诊断、Editor/条件专业 Agent、能力、质量校验、候选保存。
3. 验证 Logic 连接 `visualize`，Data 连接 `answers-charts`，不可用能力仍占正确位置并解释状态。
4. 切换到 360px、键盘和屏幕阅读器语义树，确认不看连线也能读出上下游和条件。

**Pass**: 页面结构与 manifest 完全一致，无伪造节点，可从任一详情返回原位置。

## Scenario 2: 修改、校验与激活（US2）

1. 打开 Editor Agent，修改可编辑 instruction section，保存变更说明。
2. 确认新增 v2 草稿，v1/内置默认仍生效。
3. 分别提交未知占位符、空必填段、超长文本、模拟 API key/PEM，确认保存或激活被字段级错误阻止。
4. 对合法 v2 查看影响并显式激活，确认 activation version 增加。
5. 用旧 expected_version 并发激活，确认返回稳定 version conflict。
6. 恢复 v1，确认生成 v3 草稿；恢复系统默认，确认生成新版本而非删除历史。

**Pass**: 保存不等于上线，所有历史不可变，锁定规则不可编辑，冲突不丢失内容。

## Scenario 3: Skill/能力定位（US3）

1. 从 Logic 节点查看内容 Skill 与 `visualize` 能力的不同标签。
2. 进入已有 Skill 编辑/版本页面后返回，定位仍在 Logic。
3. 停用部署能力或模拟健康读取失败，刷新拓扑。

**Pass**: Skill 使用既有 ID/版本；能力只显示安全清单；状态真实表现为 disabled/unknown 和对应 skip/degrade/block。

## Scenario 4: 隔离预览与正式快照（US4）

1. 对未激活草稿 v2 输入临时样例并创建预览。
2. 在 broker 停止时验证 preview、job、outbox 与样例已保存，恢复 broker 后可继续。
3. 验证 broker message 只有 ID；结果只有 section name/hash/length、plan、selected/skipped、validation 和 usage。
4. 确认文章、revision 和 candidate 数量未变化。
5. 提交正式优化任务，在 Worker 开始前编辑/停用 Agent 与 Skill。
6. 查看任务详情，确认仍使用提交时 snapshot，并展示 selected/skipped reason。
7. 查看一个旧任务，确认 `legacy_incomplete` 而非套用当前配置。

**Pass**: 预览无正式内容副作用；正式任务配置不漂移；失败可重试且原输入存在。

## Scenario 5: 版本治理与升级（US5）

1. 比较两个 Agent 版本，确认字段级 diff、来源和激活标记。
2. 模拟 manifest 从 v1 升到 v2 且默认哈希/输出兼容性变化。
3. 确认用户覆盖仍存在并标记 needs_revalidation；未确认前不静默切换。
4. 查看 Activity 与结构化日志。

**Pass**: 版本可恢复，升级不覆盖用户内容；Activity/日志只含 ID、版本、字段集合、长度、哈希和错误码。

## Ownership and Security Matrix

- 用户 B 对用户 A 的 Agent version、activation、preview 和 orchestration snapshot 执行 list/get/write，统一得到不存在或拒绝。
- 所有写接口缺少 CSRF 时拒绝；未知 agent_key、字段或占位符拒绝。
- 搜索响应、通知和公开博客接口不包含 Agent Prompt、预览或快照。
- 用密码、Bearer token、Cookie、PEM、带凭据 URL 和 token_file 值跑保存、日志、Activity、异常响应测试，泄露数必须为 0。

## Regression and Performance

- 无用户覆盖时运行现有 Blog Orchestrator 单元/集成测试，输出与 manifest v1 默认兼容。
- 运行现有 Blog Skill、AI candidate、任务中心、SSE、发布兼容回归。
- 测量 topology 首屏与保存/激活 p95；验证任务 snapshot 事务增加时间不超过计划预算。
- 执行 migration upgrade/downgrade/upgrade，确认现有文章、Skill、PostAIRun、Candidate 无变化。

## Final Commands

```bash
cd backend && pytest tests/contract/test_blog_agent_contracts.py tests/unit/test_blog_agent_manifest.py tests/unit/test_blog_prompt_assembly.py tests/integration/test_blog_agent_management.py tests/integration/test_blog_agent_snapshot.py tests/security/test_blog_agent_security.py tests/reliability/test_blog_agent_preview.py
cd frontend && npm run typecheck && npm run test -- blog-agents blog-agent-editor && npm run test:e2e -- blog-agent-management.spec.ts
```

随后运行完整 backend/frontend 回归、Compose health checks 和一次真实内部文章端到端优化。不得在验收样例、日志或文档中写入真实密钥。
