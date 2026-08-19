# Research: 对话式协作 Agent 调度

## Decision 1: 使用持久化有向无环计划，不使用进程内 Agent 树

**Decision**: 一个任务对应一个有界执行计划；步骤、依赖、尝试和产物分别持久化。协调器按数据库状态计算 ready 集合。单个 ready 步骤通过 Celery 子任务执行；多个独立 ready 步骤复用项目既有的 worker 内有界线程池，每个线程创建独立数据库 session。

**Rationale**: 当前服务依赖 Celery 的至少一次投递和 SSE 重放。进程内 Agent 树在 worker 重启后无法恢复，也无法向前端提供可信快照。持久 DAG 允许锁定领取、部分失败、依赖阻断和精确重试。

**Alternatives considered**:

- Celery chord/canvas 直接表达 DAG：编排状态主要存在消息系统，难以满足数据库真相和用户级重放。
- 只在内存保存线程池工作项：无法提供跨工具的逐步骤状态和恢复；本方案先把每步状态落库，再把持久 ready 集合交给线程池，因此 worker 崩溃后可由 watchdog 标记并重试。
- 递归 Agent 自主创建子 Agent：难以限制深度、权限、成本和可解释性，首期明确不采用。

## Decision 2: 规划由 LLM 提议，调度由确定性策略执行

**Decision**: 新增 `agent_task_plan` 场景，输出严格的 `agent-task-plan.v1`。模型选择安全清单中的工具、参数和依赖；平台验证 DAG、工具、参数、范围、写确认、步骤数量和深度，并根据工具映射 Agent 身份。

**Rationale**: 自然语言任务拆解需要模型语义能力，但权限和副作用不能由 Prompt 保证。沿用当前 `conversation_route` 的“模型提议、平台裁决”模式能复用安全边界。

**Alternatives considered**:

- 只用关键词模板拆解：无法可靠处理复合任务和依赖关系。
- 允许模型指定任意 Agent/Prompt：可能引用未注册身份并绕过工具权限。
- 让 `conversation_route` 同时承担完整规划：路由和执行计划生命周期不同，单一 Schema 会变得难以演进和试运行。

## Decision 3: 步骤通过结构化产物协作

**Decision**: 前置步骤保存类型化、大小受限的产物；后续步骤只引用产物 ID、对象 ID 和允许的结构化字段。原始正文仍由获得授权的步骤按 ID 从领域服务读取。

**Rationale**: 直接拼接其他 Agent 的完整输出或 Prompt 会泄露私有内容并产生 Prompt injection 传播。结构化产物可校验、可审计、可做新鲜度检查。

**Alternatives considered**:

- 自由文本 Agent-to-Agent 消息：难以校验范围和数据来源。
- 在事件中传输完整结果：会让浏览器和日志接触不必要的私有内容。
- 只在内存传递 Python 对象：无法恢复和重试。

## Decision 4: 使用现有 SSE 通道发送有界计划快照

**Decision**: 新增 `agent.plan_updated` 事件，每次携带版本号和最多 12 步的安全计划视图；`jobs.snapshot` 同时包含活跃计划。前端仅接受版本更高的快照。

**Rationale**: 完整小快照可显著降低增量 patch 的乱序与丢事件复杂度。12 步上限使事件大小可控，现有 Last-Event-ID 重放和数据库轮询回退可直接复用。

**Alternatives considered**:

- 新 WebSocket：违反当前基础设施约束且无双向实时需求。
- 每个字段一个增量事件：前端合并和恢复复杂，容易产生幽灵状态。
- 只轮询：无法达到 2 秒内实时反馈且增加持续请求。

## Decision 5: 活动自动展开、终态只自动折叠一次

**Decision**: 活动计划默认展开。首次由非终态进入终态时自动折叠；用户之后的手动选择存于页面会话，不被无关事件覆盖。

**Rationale**: 运行时透明，完成后保持对话紧凑，同时尊重用户正在查看的历史计划。

**Alternatives considered**:

- 所有计划一直展开：长会话不可读。
- 每次终态快照都强制折叠：用户展开后会被轮询或重放事件打断。
- 跨设备持久化折叠偏好：不属于执行状态，首期没有必要增加服务端数据。

## Decision 6: 复用现有写确认作为计划屏障

**Decision**: 写步骤先创建 `PendingWrite` 并进入 `waiting_confirmation`。协调器把依赖步骤保持 pending/blocked；批准后同一确认服务执行写入、完成步骤并重新调度计划。

**Rationale**: 现有确认服务已经实现归属、乐观版本、工具 allow_write 和审计记录，不应建立第二套批准机制。

**Alternatives considered**:

- 规划时一次确认整张计划：后续预览尚未产生，用户无法知情批准。
- 用户原始请求视为批准：违反 Human Authority。

## Decision 7: 首期并发和规模限制

**Decision**: 计划最多 12 步、依赖深度最多 4、每计划同时运行最多 4 步、每步骤最多重试一次。继续遵守现有对象批量上限。

**Rationale**: 足以覆盖当前文章和 MCP 组合任务，同时控制个人服务器资源、事件体积和模型成本。

**Alternatives considered**:

- 无限制并发：可能压垮数据库、LLM 或 MCP 服务。
- 全局串行：不能实现用户要求的协作收益。
