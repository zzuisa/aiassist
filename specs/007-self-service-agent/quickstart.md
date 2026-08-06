# Quickstart: 自助式问答与任务执行 Agent

**Feature**: 007-self-service-agent | **Date**: 2026-08-06

本文给出本特性交付后的端到端使用路径，同时充当验收脚本。所有请求走 `/api/v1`，携带同源 HttpOnly Cookie；写方法额外需要 `X-CSRF-Token`。

---

## 0. 前置

| 依赖 | 说明 |
|---|---|
| 迁移 `0019_agent_runtime` 已应用 | 新增 4 张表 |
| spec 006 的 Agent 配置已存在 | 007 消费其生效版本，不自建定义 |
| `AGENT_MAX_BATCH_OBJECTS` / `AGENT_MAX_CONCURRENCY` | 默认 200 / 4，见 data-model |

---

## 1. 只读查询：不读正文

```bash
curl -sS -X POST /api/v1/agent/tasks \
  -H 'Content-Type: application/json' -H "X-CSRF-Token: $CSRF" \
  -b "$COOKIES" \
  -d '{"request_text":"给我最近 10 篇文章"}'
```

返回 `202` 与任务对象：

```json
{ "task_id": "…", "job_id": "…", "intent_key": "articles.list_recent",
  "status": "pending", "created_at": "…" }
```

**验收点**：

- 任务与其配对 Job 在任何模型调用之前已落库（Constitution I）。
- 完成后 `GET /agent/tasks/{task_id}/records` 中**不存在** `operation_type=analyze` 的正文读取条目（SC-001 / FR-009）。
- 结果只含标题、链接、分类、标签等轻量字段。

---

## 2. 实时状态：复用既有 SSE，不开第二条通道

```bash
curl -N -b "$COOKIES" /api/v1/events/jobs
```

```text
event: agent.status_changed
data: {"schema_version":"agent-status-event.v1","task_id":"…","job_id":"…",
       "agent":{"agent_name":"文章查询 Agent","responsibility":"查询、筛选和排序文章元数据，不读取文章正文",
                "current_task":"获取最近发布的 10 篇文章","status":"running",
                "current_tool":"search_articles","progress":{"current":0,"total":10}},
       "timestamp":"…"}
```

**验收点**：

- 首个状态事件在 2s 内到达（SC-002）。
- `status` 取值落在七值枚举内（FR-026）。
- 事件中无模型推理、无系统提示词、无任何凭据（FR-028）。
- **断线重连**：带 `Last-Event-ID` 重连不丢事件；游标失效时先收到 `jobs.snapshot`，其中包含当前在跑的 Agent，面板不会空白。此能力由既有 SSE 实现提供，本特性只扩展快照负载。

---

## 3. 多轮指代：「这些」= 上一轮那 10 篇

```bash
curl -sS -X POST /api/v1/agent/tasks \
  -H 'Content-Type: application/json' -H "X-CSRF-Token: $CSRF" -b "$COOKIES" \
  -d '{"request_text":"给这些文章提取标签和关键词","previous_task_id":"<第 1 步的 task_id>"}'
```

**验收点**：处理对象集合与第 1 步返回集合完全一致，未扩大到全库（SC-009 / FR-035）。此步骤才首次读取正文，且只读这 10 篇（FR-010）。

---

## 4. 并行执行

对象数较多时，主控 Agent 在**单个 Celery 任务内**用有界线程池扇出（默认并发 4）。

**验收点**：

- `GET /agent/tasks/{task_id}` 返回多个 `agent_runs`，各自独立的 `status` 与 `progress`。
- 每个 run 的 `agent_version` 记录提交时绑定的 006 版本；期间修改 006 不影响本次运行（FR-046）。
- 25 对象任务并行相较串行耗时下降 ≥ 50%（SC-010）。
- **不同 run 的 `input_scope` 不重叠**（FR-015）。

---

## 5. 写操作：结构化确认，未确认零写入

生成完标签后任务转入 `waiting_confirmation`：

```bash
curl -sS -b "$COOKIES" /api/v1/agent/tasks/$TASK_ID/confirmations
```

```json
[{ "confirmation_id": "…", "operation_type": "update", "target_type": "post",
   "affected_count": 10, "reversible": true, "high_risk": false,
   "decision": "pending", "preview": { "…": "…" } }]
```

批准：

```bash
curl -sS -X POST /api/v1/agent/tasks/$TASK_ID/confirmations/$CONFIRM_ID \
  -H 'Content-Type: application/json' -H "X-CSRF-Token: $CSRF" -b "$COOKIES" \
  -d '{"decision":"approve"}'
```

**验收点**：

- 批准前对目标对象查询，数据**未发生任何变化**（SC-004 / FR-022）。
- 批准是结构化决策，不靠对话里出现「确认」二字——引用内容中的该词不会误触发（R-004）。
- 批准本身不绕过领域校验：归属、乐观版本、固定事件保护在既有领域服务内重跑；版本不匹配返回冲突而非静默覆盖。
- 删除/覆盖/批量更新即便原始请求已表达执行意图，仍需再次确认（FR-023）。

---

## 6. 能力不足：明说，不编

```bash
curl -sS -b "$COOKIES" /api/v1/agent/tools
```

清单只含 `name` / `type` / `responsibility` / `required_permission` / `available`，**不含端点与凭据**（宪法 1.1.0）。

当请求需要未注册的能力时，回复给出：缺什么能力、缺什么接口或权限、能做哪部分、不能做哪部分、建议补什么（FR-007）。

**验收点**：不声称调用了不存在的接口，不以模拟数据代替失败结果（SC-007 / FR-006）。

---

## 7. 执行留痕

```bash
curl -sS -b "$COOKIES" /api/v1/agent/tasks/$TASK_ID/records
```

**验收点**：

- 每次工具调用一条独立记录，步骤可按序还原，无缺失（SC-005）。
- 全文检索无密码、令牌、API Key、Cookie、认证头、私钥（SC-006 / FR-031）。
- `operation_type` 落在七值枚举内（FR-030）。

---

## 8. 部分失败与数据存活

模拟 LLM 网关不可用后重跑批量任务。

**验收点**：

- 已成功项结果保留率 100%，任务终态为 `partial_success`（SC-008 / FR-034）。
- 失败项与原因单独列出，不被隐藏，不被描述为全部成功（FR-004 行为限制）。
- **用户原有文章保持完整可访问**（Constitution I 数据存活）。

---

## 9. 记录清理

在任务中心执行「清空已完成任务」后：

**验收点**：

- 该任务的 `agent_tasks` / `agent_runs` / `agent_execution_records` / `agent_pending_writes` 随 Job 级联清除。
- **文章等业务实体不受影响**——本特性任何表都不对业务实体建外键（R-006 / data-model 硬约束 2）。这是必须专项验证的一条：写错会导致清空任务历史连带删除用户文章。
