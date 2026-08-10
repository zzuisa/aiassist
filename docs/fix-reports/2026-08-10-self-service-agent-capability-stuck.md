# 修复复盘：自助 Agent 能力问答卡住（2026-08-10）

## 现象

用户在“自助 Agent”页面提交“你能做什么”后，界面持续显示处理中，没有结果、失败提示或重试建议。对应任务 `3d374af8-475d-4561-828d-78098566d612` 长时间保持 `pending`。

## 根因

请求被正确分类为 `capability.unknown`，但当时线上 backend 与 `worker-heavy` 仍运行前一版镜像。该版本已经能够产生这个意图键，却没有注册对应的执行计划。worker 收到任务后抛出 `ValidationError: Unknown intent: capability.unknown`。

异常发生在 Agent run 和终态写入之前，Celery 任务虽然失败，`agent_tasks` 与配对 Job 仍保持 `pending`，错误信息也没有持久化。前端对 `pending/running` 每秒轮询，且没有停滞超时，因此表现为无限等待且无提示。

## 修改

- 部署完整的自助 Agent 实现，注册 `capability.unknown` 意图并路由到 `capability_gap` 执行器。
- 使用已注册的只读工具 `agent.capabilities` 生成结构化能力说明，不调用不存在的接口，也不伪造执行结果。
- 完成 CI、镜像重建、数据库迁移以及 backend、frontend、worker 和网关的滚动替换。
- 重新投递原卡住任务，使其通过新 worker 完成，保留原任务 ID 与执行留痕。
- 修正部署脚本生成的后续 commit subject，使其遵循 emoji、类型与简短中文描述规范。

## 验证

1. 本地 Agent/Assistant 验收集通过：66 个测试通过。
2. Ruff 格式检查、规则检查、Mypy、前端 lint、类型检查、组件测试和生产构建通过。
3. GitHub CI run `31407870352` 全部通过，包括真实 Compose E2E 与 Agent API 流程。
4. 生产迁移成功，网关返回 `{"status":"ready"}`，fast/heavy worker 均返回 `pong`，所有 AI Assist 服务健康。
5. 线上新 worker 将原任务在 0.37 秒内处理完成：任务终态 `partial_success`、Job 终态 `completed`，生成 1 个 Agent run、1 条执行记录和非空结果。
6. 整个恢复过程只执行能力查询，没有修改文章或其他业务实体。

## 日志检索方式

Docker 日志只检索任务 ID、Celery task ID、意图键与状态，不输出 Cookie、令牌、提示词或正文：

```bash
docker logs --since 2h aiassist-worker-heavy-1 2>&1 \
  | rg '3d374af8-475d-4561-828d-78098566d612|agent.execute_task|capability.unknown|Unknown intent'
```

在 ELK 中可按以下安全字段组合检索：

```text
service:"worker-heavy" AND message:"agent.execute_task"
```

必要时再用任务 ID 缩小范围。禁止记录或检索认证头、Cookie、密码、令牌、私钥及 LLM 完整提示词。

## 遗留风险

- 当前修复覆盖了能力问答的具体意图，但 worker 对其他未处理异常仍缺少统一的“任务与 Job 转 failed”兜底；类似异常仍可能留下 `pending` 状态。
- 前端轮询仍缺少最长等待时间、停滞检测与可见的重试入口；后端异常状态未落库时，用户提示仍不充分。
- 原任务以 `partial_success` 表示能力缺口，这是预期语义，但界面文案需要持续区分“能力说明”与“执行失败”。
- 建议后续增加 worker 顶层异常持久化、pending watchdog 和前端超时提示，并覆盖对应故障注入测试。
