# Feature Specification: 对话式协作 Agent 调度

**Feature Branch**: `011-collaborative-agent-orchestration`

**Created**: 2026-08-18

**Status**: Draft

**Input**: User description: "每次对话时前端实时展示当前调度情况，执行完后折叠且可展开；把自助 Agent 改造成类似 Codex 的工具，先拆分任务，再分别异步调度 Agent 协同合作。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 实时查看任务计划与执行 (Priority: P1)

用户在自助 Agent 中提交任务后，立即看到该轮任务的目标、拆分步骤、依赖关系和当前调度状态。执行过程中，界面实时更新每个步骤正在等待、执行、调用能力、完成、失败或等待用户确认的状态，而无需刷新页面。

**Why this priority**: 透明的实时反馈是 Codex 式体验的基础；如果用户看不到系统正在做什么，多 Agent 调度只会表现为更长的等待。

**Independent Test**: 提交一个至少包含两个步骤的只读任务，验证计划先出现，两个步骤的状态按实际执行实时变化，并且最终结果与步骤状态一致。

**Acceptance Scenarios**:

1. **Given** 用户提交一个可执行任务，**When** 系统接受该轮消息，**Then** 在首次后台执行开始前持久化并展示任务目标及至少一个计划步骤。
2. **Given** 一个任务包含多个步骤，**When** 步骤进入等待、运行或终态，**Then** 用户在 2 秒内看到对应步骤、负责 Agent、当前能力和安全摘要的变化。
3. **Given** 页面刷新或实时连接重建，**When** 用户重新进入同一会话，**Then** 系统从持久状态恢复完整计划和当前运行状态，不依赖仅存在于浏览器内存中的事件。
4. **Given** 系统正在执行任务，**When** 某个步骤等待用户确认，**Then** 计划视图明确显示阻塞原因和所需操作，且依赖该步骤的后续步骤不被执行。

---

### User Story 2 - 任务拆解与异步协作 (Priority: P1)

用户用自然语言提出复合任务后，主控 Agent 先把任务拆为有依赖关系的子任务，再把当前可并行的子任务异步交给合适的 Agent 或能力执行。各子任务只使用被授权的输入范围，并通过结构化产物把结果交给依赖它的后续步骤。

**Why this priority**: 这是从“单工具路由器”升级为“协作 Agent 工具”的核心能力，并能完成当前必须分多轮才能完成的查询后分析任务。

**Independent Test**: 提交“查找最近几篇文章，分析标签并汇总”的请求，验证系统生成查询、分析和汇总步骤；查询完成后将其对象范围传给分析步骤，独立分析步骤可并行，最终只汇总真实成功结果。

**Acceptance Scenarios**:

1. **Given** 一个复合任务，**When** 主控完成规划，**Then** 每个子任务都有稳定标识、职责、依赖、输入来源、预期产物和允许能力。
2. **Given** 两个子任务互不依赖，**When** 它们的依赖均已满足，**Then** 系统在配置的并发上限内异步调度它们，而不是无条件串行执行。
3. **Given** 一个后续步骤依赖前置结果，**When** 前置步骤成功，**Then** 后续步骤只获得经过校验的结构化产物和授权对象范围，不获得其他 Agent 的隐藏上下文或推理过程。
4. **Given** 某个独立子任务失败，**When** 其他子任务仍可安全完成，**Then** 系统保留成功结果、停止仅依赖失败结果的步骤，并以部分成功结束。
5. **Given** 任务只需要一个原子操作，**When** 系统规划任务，**Then** 仍生成一个单步骤计划，但不创建无价值的额外 Agent 或并行层级。
6. **Given** 规划结果引用未注册、未授权或类型不匹配的能力，**When** 平台校验计划，**Then** 计划不得进入执行，并向用户请求补充信息或说明能力缺口。

---

### User Story 3 - 完成后自动折叠并可追溯展开 (Priority: P2)

任务完成、部分成功、失败或被拒绝后，实时调度面板自动折叠为紧凑摘要，避免长计划淹没对话。用户可以随时展开查看原计划、每步状态、用时、能力调用和安全结果摘要。

**Why this priority**: 长会话需要保持可读性，同时又不能牺牲执行过程的可审计性。

**Independent Test**: 完成一个三步骤任务，验证面板自动折叠并显示终态摘要；展开后仍能看到三个步骤及其最终状态，刷新后内容不丢失。

**Acceptance Scenarios**:

1. **Given** 一个正在运行的任务，**When** 尚未进入终态，**Then** 调度面板默认展开并突出当前活动步骤。
2. **Given** 一个任务进入任意终态，**When** 最终状态到达前端，**Then** 面板自动折叠为包含状态、步骤统计、总耗时和结果入口的摘要。
3. **Given** 已折叠的任务，**When** 用户选择展开，**Then** 展示原始步骤顺序、依赖、负责 Agent、工具、状态、耗时、重试和安全摘要。
4. **Given** 用户展开一个已完成任务，**When** 页面收到无关任务事件，**Then** 不擅自改变该任务的展开状态。

---

### User Story 4 - 安全确认、失败恢复与重试 (Priority: P2)

用户可以在同一计划视图中处理写入确认、观察失败原因并重试安全失败的步骤或整轮任务。恢复执行时，已经成功且产物仍有效的步骤不会重复运行。

**Why this priority**: 异步协作增加了部分失败和中断的可能，必须让用户能安全恢复而不是重新执行全部工作。

**Independent Test**: 让一个三步骤任务在第二步发生可重试故障，验证第一步产物保留、失败原因可见、重试只重新执行失败步骤及其未完成依赖链。

**Acceptance Scenarios**:

1. **Given** 计划包含业务写入，**When** 写入步骤就绪，**Then** 系统先展示影响范围和预览，并暂停该步骤及其依赖步骤直到用户决定。
2. **Given** 用户拒绝写入，**When** 决定被记录，**Then** 业务数据保持不变，写入步骤标记为已拒绝，计划形成可解释终态。
3. **Given** 一个步骤因暂时性依赖故障失败，**When** 用户重试，**Then** 系统复用仍然有效的成功产物，仅重新调度失败步骤及受其影响的后续步骤。
4. **Given** 运行进程中断，**When** 监控检测到超时，**Then** 受影响步骤和整轮任务进入可操作的停滞或失败状态，不保持永久运行假象。

### Edge Cases

- 规划模型不可用时，原始用户消息和任务记录保持可见，并显示可重试状态；不得创建伪计划或模拟执行结果。
- 规划只产生循环依赖、空计划、超过步骤上限或超过深度上限时，计划校验失败且不调度任何子任务。
- 多个步骤同时完成或事件乱序到达时，界面以持久版本为准，不回退到旧状态或重复步骤。
- 用户在任务运行时刷新、离线或切换页面时，执行继续；恢复连接后重建最新计划快照。
- 前置步骤只获得部分结果时，依赖步骤必须按计划声明决定继续、跳过或停止，不能默认扩大处理范围。
- 用户撤销 MCP 授权或对象归属在规划后变化时，实际调用前重新校验并使相关步骤失败或等待用户处理。
- 超过并发、批量或总步骤限制时，系统明确说明实际执行范围并要求用户收窄请求。
- 任务终态事件与用户手动展开操作同时发生时，首次进入终态可自动折叠；用户随后手动展开的选择优先。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST durably accept the user message and its conversation turn before planning or executing any task.
- **FR-002**: System MUST distinguish pure conversational replies from task requests; every task request MUST have a visible plan before its first business capability executes.
- **FR-003**: System MUST represent an atomic task as a one-step plan and a composite task as a bounded dependency graph.
- **FR-004**: Each plan MUST record a stable plan identifier, objective, version, status, creation time and terminal summary.
- **FR-005**: Each plan step MUST record a stable step identifier, user-visible title, responsibility, assigned Agent, dependencies, input source, expected output, allowed capabilities, status, progress when knowable, attempt count, timestamps and safe result or error summary.
- **FR-006**: System MUST validate that a plan is non-empty, acyclic, within configured step/depth limits, and contains only registered, available and authorized capabilities before dispatch.
- **FR-007**: System MUST constrain every step to the current user's owned objects and MUST prevent a child step from expanding inherited scope unless a registered query step explicitly produces that scope.
- **FR-008**: System MUST dispatch dependency-ready steps asynchronously and concurrently within a bounded per-task and per-user limit.
- **FR-009**: System MUST NOT recursively create unbounded child Agents; the initial release supports one coordinator and one level of worker steps, with fan-out over bounded objects inside a worker step.
- **FR-010**: Worker steps MUST collaborate only through validated, persisted artifacts and declared object scope; prompts, chain-of-thought, credentials and raw private tool responses MUST NOT become collaboration artifacts.
- **FR-011**: A step MUST enter running state only after all required dependencies have reached an acceptable state defined by the plan.
- **FR-012**: A failed independent step MUST NOT discard successful sibling results; dependent steps MUST be blocked or skipped with a durable reason.
- **FR-013**: System MUST support success, partial success, failure, waiting for clarification, waiting for confirmation, blocked, skipped and stalled outcomes at the appropriate plan or step level.
- **FR-014**: System MUST apply bounded retry policy only to retryable failures and MUST record every attempt without duplicating successful business effects.
- **FR-015**: Business writes MUST remain behind the existing structured confirmation boundary; a planning decision or natural-language request MUST NOT count as approval.
- **FR-016**: Approval MUST revalidate ownership, authorization, object versions, frozen preview arguments and idempotency before executing a write.
- **FR-017**: System MUST persist plan and step state as the source of truth and publish replayable versioned status events in the same transaction as each visible state transition.
- **FR-018**: The UI MUST show the plan inline with the corresponding conversation turn and update active steps without a page refresh.
- **FR-019**: While a plan is non-terminal, its panel MUST be expanded by default and identify queued, ready, running, blocked, waiting-user and terminal steps with text and non-color indicators.
- **FR-020**: When a plan first reaches a terminal state, its panel MUST automatically collapse to a summary containing final status, completed/failed/skipped counts, total elapsed time and an expand control.
- **FR-021**: Users MUST be able to expand or collapse a terminal plan without unrelated events overriding their latest manual choice during the current page session.
- **FR-022**: Reopening a conversation or reconnecting the live event stream MUST reconstruct the latest complete plan from persisted state.
- **FR-023**: User-visible events and plan details MUST include only safe task descriptions, public Agent identity, registered capability name, coarse progress, timestamps and bounded summaries.
- **FR-024**: User-visible events, logs and execution records MUST exclude system prompts, Skill instructions, chain-of-thought, endpoints, credentials, tokens, connection strings and unbounded private payloads.
- **FR-025**: The final assistant response MUST be grounded in persisted successful step artifacts and clearly distinguish completed, failed, skipped, waiting-user and unprocessed work.
- **FR-026**: System MUST allow a safe retry of a failed or stalled plan and reuse successful artifacts that remain valid, rerunning only invalid failed steps and their affected dependents.
- **FR-027**: System MUST expose a truthful capability-gap or clarification outcome when no valid plan can be produced; it MUST NOT claim that unavailable Agents or tools ran.
- **FR-028**: System MUST continue supporting existing single-tool article queries, analysis, MCP reads and confirmed writes through the new plan representation without weakening current ownership or confirmation behavior.
- **FR-029**: The existing legacy task entry point MUST either create the same plan representation or be explicitly adapted through a compatibility layer so task status remains consistent across both entry points.
- **FR-030**: The system MUST provide independently verifiable tests for planning contracts, dependency scheduling, concurrent execution, partial failure, write confirmation, event replay, UI collapse behavior and dependency outage data survival.

### Key Entities

- **Execution Plan**: The durable, versioned plan for one conversation turn or legacy task, containing the objective, graph status, aggregate counters and terminal summary.
- **Plan Step**: One bounded unit of work with dependencies, assigned Agent/capability, execution state, retry policy and safe user-visible activity.
- **Step Dependency**: A directed prerequisite relationship specifying which predecessor outcome permits a step to become ready.
- **Step Artifact**: A validated, persisted output reference passed from one step to another, containing only the minimum structured result and authorized object scope.
- **Step Attempt**: One auditable execution attempt with timing, stable error category and retryability.
- **Plan Event**: A replayable, ordered public state transition used to update the conversation UI.

### Data Safety & AI Control *(mandatory when the feature stores content or uses AI)*

- **Durable acceptance point**: The user message, conversation turn and paired job are considered accepted only after they commit together; the execution plan and every step transition are persisted before their corresponding asynchronous command or public event is emitted.
- **AI authority boundary**: AI may propose a bounded task graph, assignments and read-only actions. Deterministic policy validates the graph and every capability call. Any business write requires a separate persisted preview and explicit user approval.
- **Failure fallback**: If planning, execution workers, event delivery or an external provider fails, the original message, last valid plan, completed artifacts and audit records remain accessible and retryable; no synthetic result replaces missing work.
- **Privacy and ownership**: Plans and artifacts are private to their owner. Child steps inherit only explicitly authorized object scope. Public activity never exposes prompts, private reasoning, credentials or raw tool payloads.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For at least 95% of accepted task messages under normal conditions, users see the first persisted plan or actionable planning failure within 2 seconds.
- **SC-002**: For at least 95% of plan state changes under normal conditions, the visible step state updates within 2 seconds without manual refresh.
- **SC-003**: A task with two independent, equally slow steps completes at least 30% faster than the same steps executed serially, while respecting configured concurrency limits.
- **SC-004**: After refresh or live-connection recovery, 100% of active plans reconstruct with no missing, duplicated or regressed steps.
- **SC-005**: In partial-failure tests, 100% of successful independent artifacts remain available and no dependent step consumes a failed or unauthorized artifact.
- **SC-006**: In all write-path tests, business data remains unchanged until a separate approval is recorded, including when the original message explicitly requests immediate execution.
- **SC-007**: Every terminal task collapses to a compact summary on first completion and can be expanded to show the complete persisted execution trace in one user interaction.
- **SC-008**: No tested plan event, user-visible activity, log or execution record contains a system Prompt, Skill instruction, chain-of-thought, endpoint, credential, token or connection string.
- **SC-009**: Existing supported article query, article analysis, MCP read and confirmed write acceptance scenarios continue to pass through the planned workflow.
- **SC-010**: A failed or stalled multi-step task can be retried without rerunning still-valid successful steps or duplicating a previously applied write.

## Assumptions

- Pure greetings, thanks, goodbye messages and capability-help questions remain eligible for the existing no-model fast path; all task requests receive a visible plan, including one-step tasks.
- The first release uses one coordinator and a single worker-step level. Worker steps may fan out over bounded objects, but workers cannot recursively create arbitrary Agent trees.
- The plan panel is automatically expanded while active and collapses once on first terminal transition. The user's subsequent expand/collapse choice is kept for the current browser session.
- Collaboration uses persisted typed artifacts rather than free-form Agent-to-Agent chat.
- Existing authentication, ownership rules, tool registry, MCP grants, write confirmation, async jobs and global live-event channel are reused.
- Initial planning and collaboration cover the capabilities currently registered in the self-service Agent; installing new external capabilities is outside this feature.
- User cancellation and arbitrary manual editing of the generated plan are deferred; clarification, confirmation and retry remain supported.

