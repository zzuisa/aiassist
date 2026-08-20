# Quickstart: 通用 MCP 任务编排与报告验收

## 1. 准备环境

```bash
docker compose run --rm migrate
docker compose up -d --build backend worker-fast worker-heavy beat frontend
docker compose ps
```

确认迁移到最新 head，backend、worker、broker、数据库和前端健康。MCP secrets 只通过部署 secrets 文件提供，不复制到规格、日志或测试输出。

首次部署还必须执行锁定版本的 LangGraph PostgreSQL Checkpointer 初始化/迁移。该 schema 由 LangGraph 运行时管理；AI Assist Alembic 只管理业务投影表和 `graph_thread_id/graph_run_id` 引用。

## 2. 准备参考数据

为测试用户创建三个启用分类，并准备以下私有文章：

- 情感相关且已有分类
- 情感相关且没有分类
- 不属于情感主题
- 无法高可信分类的短文
- 准备用于制造版本冲突的未分类文章

另准备最多 1,000 篇混合文章做容量测试。记录安全测试 ID 和初始 `category_id/version`，不要记录正文或令牌。

## 3. 验证能力快照与计划

在自助 Agent 提交：

```text
检查所有博客中有关情感的文章是否都有分类；为没有分类的文章推荐现有分类，确认后添加分类，并给我完整报告。
```

验收：

- 业务工具执行前已持久化 plan 和 capability snapshot。
- 模型可见工具名仅含字母、数字、下划线、连字符且不超过 64 字符。
- 快照不含端点、令牌、连接字符串和 MCP server instructions。
- 计划包含搜索、筛选、分类读取/分析、预览写入、验证和报告责任，且 DAG 无环、步骤不超过 12。
- 运行时只有一个 LangGraph `orchestrate_task` Graph Run；不存在并行的 Agent scheduler、Celery DAG 或第二个 checkpoint 状态源。

## 4. 验证批量预览和确认边界

等待冻结预览出现：

- 预览数量与符合条件的未分类文章一致。
- 每项包含文章、existing category、expected version、可信度和依据。
- 低可信度、已分类、删除或无权限对象进入排除/人工复核，不进入自动写入。
- 批准前所有文章的 `category_id/version` 保持不变。

在批准前手工修改一篇待处理文章制造 version 变化，然后携带当前 `preview_digest` 批准。重复提交相同确认应返回幂等或冲突结果，不重复写入。

## 5. 验证异步写入、冲突和幂等

- 确认接口快速返回，批量写在 worker 中执行。
- 确认接口只向 LangGraph 发送 resume command，不在 HTTP 请求中执行批量写。
- 版本变化文章标记 conflict 且保持人工修改，不触发删除、覆盖或配置变更。
- 其他文章按逐项 logical operation key 写入；重复投递不会重复提升版本或重复关联分类。
- 撤销 MCP grant、worker 重启或 broker 短暂不可用时，Outbox/恢复流程不会让任务永久保持运行假象。

## 6. 验证回读和报告

- 每个 applied item 都有独立 verification result。
- 只有实际读回的 category 与建议一致才记为 verified。
- 模拟 provider 返回成功但不落库时，该项为 mismatch/manual review，不进入成功数。
- Markdown 包含目标、执行计划、总数、已验证变更、冲突、失败、跳过/未处理、验证结果和后续行动。
- 报告 totals 与数据库逐项 outcome/verification 完全一致。
- 调用 report regenerate 前后文章版本不变，也没有新的业务 MCP write attempt。

## 7. 验证实时 UI 和恢复

- 状态变化 2 秒内反映到一行进度条。
- 页面只突出一个 required action；等待确认只暂停依赖链。
- 步骤和执行记录默认折叠，1,000 项不会展开为 1,000 个 DAG 节点。
- 刷新或断开 SSE 后只恢复最新快照，不重放/展开过期失败记录。
- 杀掉 worker 后重新投递 Graph Run，LangGraph 从 PostgreSQL checkpoint 恢复，已经完成的 operator 不重复执行。
- `aria-live`、键盘焦点、文本/图标状态和 reduced-motion 均可用。

## 8. 自动化验证

```bash
cd backend
pytest tests/unit tests/contract tests/integration tests/reliability tests/security
pytest tests/performance/test_agent_1000_posts.py
ruff check app tests
ruff format --check app tests
alembic check
```

```bash
cd frontend
npm run test
npm run lint
npm run typecheck
npm run build
npm run test:e2e -- agent-generic-orchestration.spec.ts
```

故障注入至少覆盖 MCP 超时/无效 output、授权撤销、broker 发布失败、worker kill、重复 Graph resume、interrupt 恢复、写入 ambiguous outcome、验证失败、报告模型失败和 SSE 乱序重连。

## 9. 当前迁移风险

- Checkpointer schema 由锁定版本的 `langgraph-checkpoint-postgres` 管理；升级
  LangGraph 前必须在预发布环境验证 checkpoint 向前兼容和恢复。
- Graph node 可能在 interrupt 或 worker 丢失后从节点边界重新进入，因此所有
  MCP 写入仍必须依赖业务 effect key、对象版本和回读验证，不能只依赖 checkpoint。
- 兼容期保留 `scheduler.py` 中的计划投影/终态对账函数，但 Celery 不再派发单步
  DAG。后续重构只能移动投影职责，不能引入第二套 ready-step 队列。
- 部署必须同时更新 worker 与 backend；新 API 配合旧 worker 会导致 Graph Run
  无法恢复，禁止只滚动更新其中一个进程。
