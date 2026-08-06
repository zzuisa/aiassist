# Phase 0 Research: 自助式问答与任务执行 Agent

**Feature**: 007-self-service-agent | **Date**: 2026-08-06

本文解决 spec.md 中遗留的 4 项 NEEDS CLARIFICATION，并记录 3 项在代码核查中发现的、与 spec 假设不符的事实。后者优先级更高——它们会直接推翻 spec 中的某些 Assumption 与 Success Criteria。

---

## 一、代码核查发现的事实修正

### R-000（最高优先级）：现有"多 Agent"不是并行执行，而是单次 LLM 调用内的提示词角色组合

**核查过程**：

- `backend/app/modules/posts/orchestrator.py:build_plan()` 产出 `OrchestrationPlan.selected_agents`（`editor-agent` / `logic-agent` / `data-agent` / `scene-image-agent` / `illustration-agent`）。
- 但 `build_system_prompt(config, plan, instruction)`（同文件 526 行）消费该列表的方式是 **拼提示词**：`if "logic-agent" in plan.selected_agents: parts.append("...请在 enhancements 中返回一项 status=executed...")`。
- `backend/app/workers/tasks/blog.py` 中全文件仅有 3 处 LLM 调用点（653/807 附近的 `structured()`），一次 `optimize_run` 主链路是**一次** `get_llm_gateway().structured(...)`。
- 全仓检索无 `group(` / `chord(` / `apply_async` 的 agent 级扇出。

**结论**：系统当前**不存在**可复用的"多 Agent 并行执行能力"。存在且可复用的是 **Agent 选择与门控逻辑**（价值评分、能力可用性检查、跳过原因码、`max_agent_calls` 上限）。

**对 spec 的影响**：

- spec Assumptions 中"复用 `posts/orchestrator.py` 中既有的 Agent 选择与并发上限机制（含 `max_agent_calls`），不另建一套调度器"——**前半句成立，后半句需修正**：并行执行器必须新建。
- `max_agent_calls`（`max(1, min(8, ...))`，默认 4）**不是并发度上限**，而是"提示词中最多提及几个 agent 角色"的成本闸门。不可直接当作并发上限沿用。

**决策**：Phase 1 明确区分两层——**选择层**复用 orchestrator 的门控逻辑，**执行层**新建真正的并行调度。spec 的 Assumption 与 D-002 措辞需同步修正。

---

### R-001（最高优先级）：`worker-heavy` 并发为 1，SC-010 在当前拓扑下不可达成

**核查过程**：

`compose.yaml:176` — `["celery", ..., "worker", "-Q", "voice,image,llm,maintenance", "-c", "1", ...]`

`worker-heavy` 以 **`-c 1`** 运行，且 `voice`、`image`、`llm`、`maintenance` 四个队列共用这唯一一个执行槽位。任何"扇出成 N 个 Celery 子任务"的设计都会在这里串行化，且会与语音转写、图片处理抢占同一槽位。

**对 spec 的影响**：SC-010（"25 篇文章批量提取，并行相比串行耗时下降不低于 50%"）在不改动执行模型的前提下**无法达成**。

**候选方案**：

| 方案 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| A. 提高 worker-heavy 并发 | `-c 1` → `-c N` | 改动最小 | 与语音/图片抢槽位；N 个并发 LLM 调用的内存与配额压力不可控；影响既有功能 |
| B. Celery group 扇出 + 新增 worker | 新增专用 agent worker | 隔离性好 | 违反宪法"worker 拓扑限于 worker-fast/worker-heavy 加一个 beat" |
| **C. 单 Celery 任务内线程池扇出（选定）** | 一个 `agent.task` 任务占用一个 heavy 槽位，内部用有界线程池并发调用 LLM 网关 | 不改拓扑、不抢额外槽位、并发度可配置且可限流；LLM 调用是 I/O 密集，线程池有效 | 单任务失败影响整批（需内部容错）；需显式控制线程数 |

**决策：方案 C**。理由：LLM 调用是网络 I/O 密集型，GIL 不构成瓶颈；`gateway.structured()` 是同步接口，线程池是最小改动的并发化手段；宪法的 worker 拓扑约束得以保持。

**备选拒绝理由**：A 破坏既有功能隔离；B 直接违反宪法架构约束，且本特性没有强到需要修宪的理由。

**衍生约束**：并发度必须可配置且有上限（见 R-004），且失败必须逐项隔离（对应 FR-033/FR-034）。

---

### R-002：复用 SSE 通道有一个硬约束——事件必须绑定 Job

**核查过程**：

`backend/app/models/foundation.py:232` `AsyncJobEvent`：

- `job_id` — `ForeignKey("async_jobs.id", ondelete="CASCADE")`，**NOT NULL**
- `event_type` — `String(40)`
- `user_id` + 索引 `ix_async_job_events_user_id_id`
- 注释明确："Append-only SSE replay log; written in the same transaction as job updates."

**结论**：任何走这条 SSE 通道的事件都**必须**挂在一个 `AsyncJob` 上。这不是障碍——现有 `assistant` 模块本就是"一次 run 建一个 job"（`jobs_service.create_job(..., job_type=f"assistant.{intent}", entity_type="assistant_run")`）——但它决定了数据模型：**AgentTask 必须与一个 AsyncJob 一一对应**，而不是独立实体。

`event_type` 限长 40 字符，`agent.status_changed`（20 字符）满足。

---

## 二、澄清项决策

### R-003：Agent 状态通道 → 复用现有 `GET /events/jobs`，新增事件类型

**Decision**：复用现有 SSE 流，新增 `agent.status_changed` 事件类型；不新建任务级 SSE 端点。

**Rationale**：

`backend/app/modules/jobs/sse.py` 已经解决了自建通道必须重新解决的全部难题：

| 能力 | 现有实现 |
|---|---|
| 断线重连不丢事件 | `Last-Event-ID` 游标重放（`events_after`） |
| 游标失效/过期 | 自动降级为 `jobs.snapshot` 全量重同步 |
| 持久化事件源 | PostgreSQL `async_job_events`，**不依赖 Redis**（Redis 仅作唤醒提示，不可用时退化为有界 DB 轮询且不丢事件） |
| 心跳保活 | `HEARTBEAT_SECONDS = 20` |
| 客户端重连间隔 | `retry: 3000` |
| 用户级隔离 | `user_id` 过滤 + 复合索引 |

这直接消掉了 spec Edge Cases 里的"状态事件通道断开后重连，前端如何恢复到当前真实状态而不丢失中间进度"——**该问题已由现有实现解决**，无需在本特性中重新设计。

**Alternatives considered**：

- *新建任务级 SSE 端点 `/events/tasks/{task_id}`*：边界更清晰，但要重新实现重放、快照、心跳、鉴权，且前端要维护两条长连接。为"事件类型不混杂"这一审美收益付出可靠性重造的代价，不值得。
- *WebSocket 双向通道*：宪法明令 "The MVP MUST NOT add WebSocket or GraphQL without a reviewed requirement"，且本特性的状态推送是单向的，无需双向。拒绝。

**Consequences**：

- AgentTask 与 AsyncJob 一一对应（见 R-002）。
- 前端消费 `/events/jobs` 时需按 `event_type` 分流；非 Agent 任务事件对 Agent 面板不可见。
- 快照 `_snapshot_payload` 需扩展，使重连时能恢复"当前有哪些 Agent 在跑"，否则重连后 Agent 面板会空到下一次状态变化。**这是本决策唯一需要新增的工作量。**

---

### R-004：确认交互 → 结构化确认动作，不用对话往返

**Decision**：写操作确认走结构化端点（`POST /agent/tasks/{task_id}/confirmations/{confirmation_id}`，body 含 `decision: approve|reject`），不依赖用户在对话里回复"确认"两个字。

**Rationale**：

1. **可审计**：宪法 Principle VIII 要求每个后台操作暴露可持久化状态。结构化确认天然产生一条带 `confirmation_id`、决策者、决策时间的记录；解析自然语言"确认/好的/嗯"无法可靠留痕，也无法回答"用户到底批准了哪一批对象"。
2. **防误触**：自然语言确认存在歧义与注入风险——用户消息里出现"确认"字样可能来自引用的文章内容。对删除、批量覆盖这类不可逆操作，这个风险不可接受（FR-023 明确要求高风险操作二次确认）。
3. **已有先例可复用**：现有 assistant 的 `POST /assistant/runs/{run_id}/actions/{action_id}` 就是这个形态，且 `execute_action` 已实现"重新校验归属 + 乐观版本 + 固定事件保护"的正确模式（`service.py:119`）。沿用同一形态，D-003 要求保留的既有保障可以直接迁移而非重写。

**Alternatives considered**：

- *对话往返确认*：交互更自然，但审计、防误触、并发（用户在等待确认期间发新请求）三个问题都要另外解决。拒绝。
- *混合式（对话确认低风险 + 结构化确认高风险）*：两套路径意味着两套审计与两套测试，收益不足以抵消复杂度。拒绝。

**Consequences**：需要前端配合渲染确认卡片。待确认写操作以 `PendingWrite` 持久化，Agent 状态置 `waiting_confirmation`（该状态已在 FR-026 枚举中）。

---

### R-005：批量与并发上限 → 单批 200 对象、并发 4，均可配置

**Decision**：

| 参数 | 默认值 | 上限 | 配置项 |
|---|---|---|---|
| 单次任务对象数上限 | 200 | 500 | `AGENT_MAX_BATCH_OBJECTS` |
| 并发工作线程数 | 4 | 8 | `AGENT_MAX_CONCURRENCY` |
| 单对象 LLM 调用超时 | 沿用 LLM 网关既有超时 | — | 沿用 |

**Rationale**：

- **不沿用 `max_agent_calls`**：如 R-000 所述，它是提示词成本闸门而非并发度，语义不同，复用会造成误导。但其 `min(8, ...)` 的硬上限是经过实践的保守值，并发上限沿用同一数量级（8）。
- **并发默认 4**：方案 C 的线程池运行在**一个** `worker-heavy` 槽位内（R-001），并发过高会让单个 Agent 任务长时间占用该槽位，饿死语音转写与图片处理。4 是在吞吐与不饿死邻居之间的保守起点。
- **单批 200**：超出即向用户说明实际处理范围并要求收窄（对应 spec Edge Case"用户一次请求的对象数量远超单次处理能力"）。200 对应 25 篇的 8 倍，覆盖个人自托管场景的现实上限。
- 两个值都必须可配置：自托管用户的机器规格差异极大，硬编码必然对某些人过大或过小。

**Alternatives considered**：*不设上限，按对象数动态扇出* —— 在 `-c 1` 的拓扑下等同于让单个任务无限期占用唯一的 LLM 槽位。拒绝。

---

### R-006：执行记录保留 → 复用 Job 生命周期级联，不新增定时清理

**Decision**：`ExecutionRecord` 与 `AgentRun` 通过 `task_id` 关联到 `AsyncJob`，并以 `ondelete="CASCADE"` 随 Job 删除而清理。不新增独立的定时清理任务。

**Rationale**：

核查现有清理机制：

- `jobs_service.clear_completed_jobs()`（`service.py:239`）：用户主动触发，删除本人 `completed` 状态的 Job，`AsyncJobEvent` 由数据库级联外键自动清除。函数注释明确保证："No business entity is referenced by a foreign key from AsyncJob, so clearing task history cannot delete the underlying post, capture, or other result."
- `cleanup_stale_jobs`（beat，每小时 15 分）：只把超过 24h 未更新的非终态 Job 置为 `cancelled`，**不删除**记录。
- **`async_job_events` 当前没有任何基于时间的清理**——事件随 Job 删除而级联，仅此而已。

沿用同一模型的好处：用户已有的"清空已完成任务"操作会同时清掉对应的 Agent 记录，语义一致、无需新的心智模型；也不引入第二套保留策略。

**Consequences**：

- 执行记录的留存时长 = Job 的留存时长，由用户主动清理决定，不自动过期。
- **必须验证**：`ExecutionRecord` 不得对业务实体（Post 等）建立外键，否则清理任务历史会连带删除业务数据——这正是现有注释所警惕的陷阱。列入 Phase 1 数据模型硬约束与测试项。

**Alternatives considered**：*新增按时间的定时清理（如保留 90 天）* —— 引入第二套保留语义，且个人自托管场景的数据量（每次任务数十条记录）远未到需要时间窗清理的程度。拒绝，留待数据量真实成为问题时再议。

---

## 三、对 spec.md 的修正项

以下修正需在 Phase 1 同步回 spec.md：

| 位置 | 原表述 | 修正 |
|---|---|---|
| Assumptions | "复用 `posts/orchestrator.py` 中既有的 Agent 选择与并发上限机制（含 `max_agent_calls`），不另建一套调度器" | 复用**选择与门控逻辑**；并行**执行器需新建**；`max_agent_calls` 是提示词成本闸门，不是并发度 |
| SC-010 | "并行处理后端到端耗时相比串行下降不低于 50%" | 保留指标，但达成前提是 R-001 方案 C 落地；需在 plan 中列为显式依赖 |
| Edge Cases | "状态事件通道断开后重连…" | 已由现有 SSE 的 `Last-Event-ID` + snapshot 机制解决，本特性只需扩展快照负载 |

## 四、未解决项

无。spec.md 中的 4 项 NEEDS CLARIFICATION 已全部收敛（R-003 ~ R-006），另新增 3 项事实修正（R-000 ~ R-002）。
