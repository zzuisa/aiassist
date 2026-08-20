# Research: 通用 MCP 任务编排与报告

## Decision 1: 使用 LangGraph 替换自研编排内核

**Decision**: 使用 LangGraph 的固定安全元图作为唯一运行时编排内核，使用 PostgreSQL Checkpointer 保存 Graph State。Celery/Outbox 只负责可靠启动和恢复 Graph Run；现有 Agent Plan 表保留为用户/审计投影，移除自研 scheduler 的 ready-step、依赖推进、重试和恢复职责。

**Rationale**: LangGraph 已提供 checkpoint、interrupt、人机协同恢复、Send 动态 fan-out、并行 fan-in、节点重试和子图能力，正好覆盖 012 需要而 011 仍需扩展的通用编排语义。继续扩展自研 scheduler 会重复实现成熟运行时并增加面试可解释性负担。关键是只保留一套运行时真相：LangGraph checkpoint；Agent Plan 是投影，不再同时驱动执行。

**Alternatives considered**: 继续自研 scheduler 因重复建设 checkpoint/interrupt/Send 而拒绝；LangGraph Cloud/Agent Server 因引入外部控制面和破坏当前 Compose modular monolith 而拒绝；Celery canvas/chord 因把业务编排状态放在 broker 而拒绝；递归 Agent 因成本和权限无界而拒绝。

**Runtime boundary**: 固定 `orchestrate_task` 图负责 `load_snapshot → validate_plan → dispatch → fan_in → preview → approval_interrupt → apply → verify → report → finalize`。LLM 只能生成数据计划，不能动态注入 Python 节点、工具权限或任意图结构。

官方能力依据：LangGraph Checkpointer 提供 checkpoint、故障恢复和 pending writes；`interrupt()` 提供可恢复的人机协同暂停；`Send` 提供动态 map/fan-out；PostgreSQL Checkpointer 适用于生产持久化。实现时分别遵循官方 [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)、[Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)、[Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api) 和 [PostgreSQL checkpointer](https://docs.langchain.com/oss/python/integrations/checkpointers) 文档。

## Decision 2: 规划前持久化不可变能力快照，并按用户解析 MCP

**Decision**: 新建 plan-bound capability snapshot。每个条目包含平台安全名、定义版本、读写类型、输入/输出 Schema、风险、权限、目录版本、批处理/幂等/验证策略，以及仅后端可见的 provider binding。运行时按当前用户解析，不把用户 connection ID 固化到全局 ToolDefinition。

**Rationale**: 当前 `McpToolSnapshot` 是连接目录历史而非计划快照；计划只保存实时 registry 的工具名，不能审计规划时所见能力或检测 Schema 漂移。进程全局 MCP definition 被不同用户刷新时还可能覆盖 connection binding。

**Safe naming**: 模型可见名称使用 `mcp_<server_slug>_<tool_slug>_<8hex>`，只允许 `[A-Za-z0-9_-]` 且不超过 64 字符；远端原名只在私有映射中保存，解决 Anthropic 工具名限制和碰撞。

**Alternatives considered**: 只引用现有 `McpToolSnapshot` 无法覆盖内部能力；每步重新使用 live registry 无法审计漂移；把端点或凭据复制进快照违反安全边界。

## Decision 3: 计划升级为 v2，使用类型化产物绑定和平台注册 operator

**Decision**: 步骤增加 kind、能力快照引用、显式 input bindings、output contract、scope policy、batch policy 与 failure policy。首期 operator 仅允许 select、map、filter、aggregate、analyze、mutate、verify、report 的平台注册实现。

**Rationale**: v1 只有粗粒度 input_source，执行器依赖文章工具特判并把全部父产物交给后继，无法验证任意 MCP 输出到输入的兼容性。严格绑定能限制对象范围和提示注入，并允许输出 Schema 校验后再释放依赖。

**Alternatives considered**: 自由文本 Agent 协作不可验证；把所有转换都变成远程 MCP 增加故障与权限面；允许模型提交 Python、JSONata 或通用表达式会形成执行注入，首期拒绝。

## Decision 4: 少量可见步骤加持久批次/逐项 outcome

**Decision**: 可见计划继续最多 12 步；LangGraph 固定图中的 dispatcher/operator 以 50～100 项批次、最多 1,000 项总范围、并发 4 处理。每批结果写入业务 outcome 和 checkpoint，Graph 从 checkpoint 继续，逐项保存对象键、版本、状态、attempt/effect key 和安全 digest。

**Rationale**: 当前 scope 截断 500、进程内 fan-out 最大 200，worker 崩溃会丢失精确进度。LangGraph 的 checkpoint 负责图位置，持久逐项 outcome 负责业务去重、局部重试和报告对账，同时保持 UI 紧凑。

**Alternatives considered**: 一对象一 DAG 节点会膨胀事件和查询；一次进程处理 1,000 项产生长事务并丢断点；单个大 JSON artifact 不适合并发领取和逐项唯一约束。

## Decision 5: LangGraph 只执行受控 operator，副作用仍由领域服务保证幂等

**Decision**: LangGraph node 不直接把 MCP client 暴露给模型。Graph node 通过 AI Assist ToolRegistry/MCP Gateway 调用已快照绑定的能力；所有有副作用的代码放在独立 task/operator 中，并使用稳定 logical effect key。`interrupt()` 前不得执行不可幂等副作用；恢复时允许 node 从头重跑但不能重复业务效果。

**Rationale**: LangGraph 的 checkpoint/interrupt 解决运行恢复，不替代领域权限、乐观锁、幂等和验证。把工具直接绑定给 ReAct Agent 会让计划边界、确认屏障和对象范围难以审计。

**Alternatives considered**: 让模型直接自由调用 MCP 会绕过计划和权限；把每个 MCP 工具包装成可任意选择的 graph node 会扩大攻击面；依赖 provider 自己保证 exactly-once 不可靠。

## Decision 6: 用 Outbox 启动/恢复 Graph Run，不再派发内部 DAG 步骤

**Decision**: graph start/resume 命令在状态事务中写入现有 Outbox，由既有 publisher 确认发布并有界退避；一个 Celery task 对应一次 LangGraph invoke/resume，`thread_id=plan_id`，`checkpoint_id` 由 LangGraph 管理。watchdog/扫描只做 Graph Run 补偿，不计算 ready step。

**Rationale**: 当前 queued 状态提交后再 `.delay()` 存在 commit/publish gap。Outbox 消除 start/resume 丢失窗口；LangGraph checkpoint 负责节点边界恢复，Celery 不再承担图内状态机。

**Alternatives considered**: 为每个 Graph node 创建 Celery 消息会重新构造第二套调度器；只周期扫描 Graph Run 会增加延迟；直接 broker publish 无法与业务事务原子化。

## Decision 7: 扩展 PendingWrite 为冻结批量预览，批准后异步执行

**Decision**: 预览保存 schema version、digest、来源 digest、快照/步骤绑定、过期时间和逐项 mutation item。确认请求绑定 exact preview digest，只记录批准并排队；worker 执行前重新校验权限、归属、版本和稳定 effect key。

**Rationale**: 当前 generic MCP preview 没有对象/版本范围，确认后在 HTTP 事务内同步调用工具，不适合大批量。逐项冻结数据可以安全报告低可信度、排除、冲突、失败与未知结果。

**Alternatives considered**: 原始自然语言请求或 plan-level approval 不能替代预览确认；同步 HTTP 批量写有超时和长事务风险；版本冲突覆盖、删除文章/分类/配置被明确禁止。

## Decision 8: 外部写入必须独立回读验证

**Decision**: provider acknowledgement 只标 applied/unknown；verify operator 用已授权 read capability 比较 intended 和 observed，只有一致才是 verified。发送后超时属于 ambiguous outcome，优先回读，不盲目重试。

**Rationale**: MCP provider 当前不保证端到端幂等，写工具返回 success 也不能证明最终状态。报告成功数必须来自可复现的 post-condition。

**Alternatives considered**: 信任写工具 success 会误报；由写工具自验不独立；缺少读取能力时不能模拟验证，只能进入 manual review。

## Decision 9: 报告采用确定性对账数据、可选 LLM 组织和确定性降级

**Decision**: 从持久逐项 outcome 和 verification 构建严格 `task-report.v1` 数据，先校验 totals，再渲染 Markdown。可选 LLM 只能重组安全事实，输出复核失败时回退确定性 Markdown。报告按 source digest 版本化并支持独立重生成。

**Rationale**: 当前 final summary 只拼少数步骤摘要，不能区分 applied 与 verified，也不能重生成。结构化事实是审计真相，Markdown 只是表现形式。

**Alternatives considered**: 直接让 LLM 读取原始 MCP 输出有注入和隐私风险；只保存 Markdown 无法重新对账；继续拼步骤摘要不满足完整报告。

## Decision 10: 首期继续 Vue 固定控制面和 SSE，不采用 OpenUI

**Decision**: 当前阶段使用 Vue 计划卡、固定确认组件、按需报告卡和 `/events/jobs` SSE。OpenUI 不作为执行、确认、取消、重试或状态来源；未来只能读取安全 TaskReport 做可选展示，且禁用浏览器直连写 MCP。

**Rationale**: OpenUI 是生成式 UI 层，不提供本功能要求的持久 DAG、版本冲突、确认和验证语义。当前完整聊天工具链仍以 React 为主，而项目已具备 Vue、Markdown、图表和 SSE 基础。引入它会扩大首期范围并可能让生成界面绕过服务端安全边界。

**Alternatives considered**: 全量 React/Next 迁移与项目宪章和现有栈冲突；浏览器 OpenUI Mutation 直连 MCP 会绕过权限、冻结预览和审计；首期只做报告实验也会增加依赖而没有闭环收益。

## Decision 11: 博客分类写使用逐项乐观锁，不复用旧无版本批量入口

**Decision**: 新的内部博客分类写能力接受文章 ID、existing category ID、expected version 和 stable operation key；逐项调用领域服务的版本检查并返回 applied/conflict/failed。配套读取能力用于验证。

**Rationale**: 现有博客 MCP 是只读的，旧批量 set_category 路径没有逐项 expected version，无法满足冲突安全。分类建议只能从已读取的启用分类中选择，低可信度项保持人工复核。

**Alternatives considered**: 自动创建分类扩大写权限；忽略版本会覆盖用户编辑；用删除配置解决兼容或冲突不具备业务合理性且被禁止。
