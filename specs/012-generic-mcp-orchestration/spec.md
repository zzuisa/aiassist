# Feature Specification: 通用 MCP 任务编排与报告

**Feature Branch**: `012-generic-mcp-orchestration`

**Created**: 2026-08-19

**Status**: Draft

**Input**: User description: "AI 收到任务后，根据当前 MCP 能力拆分任务并形成依赖计划，按计划调用多个 MCP 和 AI 分析能力完成读取、判断、确认写入、结果验证，实时展示编排与实施进度，最后重新组织为结构化 Markdown 报告。首个完整场景是检查情感类博客文章是否有分类，并为未分类文章分析、确认和添加已有分类。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 根据可用能力规划并执行复合任务 (Priority: P1)

用户用自然语言提交一个需要多种能力协作的任务。系统识别目标，读取该用户当前可用且已授权的能力，形成有边界、有依赖的执行计划，并在计划通过安全校验后按依赖关系执行。用户不需要知道能力名称或手动拼接调用顺序。

**Why this priority**: 这是把自助 Agent 从单次能力调用升级为可完成真实复合业务任务的核心价值。

**Independent Test**: 提交“检查所有情感类博客文章是否有分类”的只读任务；系统生成并执行搜索文章、读取分类、筛选缺失分类文章和汇总结果的计划，且只使用当前已授权能力。

**Acceptance Scenarios**:

1. **Given** 用户拥有完成任务所需的多个可用能力，**When** 用户提交复合任务，**Then** 系统在执行任何业务能力前展示包含目标、步骤、依赖、预期结果和风险标记的计划。
2. **Given** 两个计划步骤彼此独立，**When** 它们的依赖均已满足，**Then** 系统在安全上限内并行处理并分别保存可验证结果。
3. **Given** 后续步骤需要前一步的结果，**When** 前一步完成，**Then** 后续步骤只接收已声明、经过校验且属于当前用户的结构化结果范围。
4. **Given** 某项必要能力不存在、不可用或未授权，**When** 系统校验计划，**Then** 系统不虚构调用或结果，并明确说明能力缺口、受影响步骤和可继续完成的范围。
5. **Given** 可用能力在任务执行期间发生变化，**When** 一个步骤准备调用能力，**Then** 系统重新检查可用性和权限，并在检查失败时安全停止相关依赖链。

---

### User Story 2 - 安全分析并批量修复博客分类 (Priority: P1)

用户要求系统查找与情感相关的博客文章，识别没有分类的文章，并为这些文章推荐现有分类。系统先展示批量变更预览，等待用户明确确认，再执行添加分类并回读验证，不会通过删除数据或绕过版本检查来处理冲突。

**Why this priority**: 该场景同时验证搜索、遍历、AI 判断、批量写入、人工确认和结果验证，是通用编排能力的首个端到端业务闭环。

**Independent Test**: 准备包含已有分类、缺少分类和存在并发版本变更的情感类文章；执行任务并确认预览，验证仅为确认范围内且版本有效的未分类文章添加现有分类，冲突文章保持不变并被准确报告。

**Acceptance Scenarios**:

1. **Given** 搜索结果同时包含已分类和未分类文章，**When** 系统检查文章，**Then** 系统只把确实缺少分类的文章纳入待分析范围。
2. **Given** 系统已取得当前可选分类，**When** 分析未分类文章，**Then** 每项建议引用一个现有分类，并包含文章标识、分类标识、可信度和简短依据。
3. **Given** 存在待应用的分类建议，**When** 写入步骤就绪，**Then** 用户看到文章、建议分类、影响数量、低可信度项目和不可处理项目的批量预览，且业务数据尚未改变。
4. **Given** 用户确认批量预览，**When** 系统执行变更，**Then** 系统只修改确认范围内、仍归属当前用户且版本仍匹配的文章，并防止重复请求产生重复效果。
5. **Given** 某篇文章的版本在预览后变化，**When** 系统准备修改该文章，**Then** 系统跳过该项或重新生成建议和预览，不删除配置、文章、分类或关联数据来绕过冲突。
6. **Given** 变更调用返回成功，**When** 系统完成写入步骤，**Then** 系统重新读取变更对象并验证分类关系实际存在，再将该项计为成功。
7. **Given** 用户拒绝或未确认预览，**When** 任务停止或等待，**Then** 所有待确认业务数据保持不变，已完成的只读结果继续可查看。

---

### User Story 3 - 实时查看紧凑的编排进度 (Priority: P2)

任务运行期间，用户在对应对话轮次中实时看到当前阶段、活动步骤、完成数量、失败或冲突数量以及需要本人处理的确认。详细执行记录默认折叠，状态区域保持紧凑且不会重复展示过期失败记录。

**Why this priority**: 复合任务可能持续较长时间，清晰而克制的进度反馈能建立信任，同时避免执行日志淹没对话内容。

**Independent Test**: 执行包含搜索、分析、确认、写入和验证的任务，观察页面无需刷新即可更新当前阶段；刷新页面后恢复最新状态，详情仍默认折叠且不重复旧事件。

**Acceptance Scenarios**:

1. **Given** 计划正在执行，**When** 步骤或汇总计数变化，**Then** 用户在 2 秒内看到最新阶段、活动步骤和进度，不需要刷新页面。
2. **Given** 一个步骤等待确认，**When** 用户查看任务，**Then** 状态区突出唯一待办操作，并保持其依赖步骤暂停。
3. **Given** 用户重新打开会话或实时连接恢复，**When** 页面加载任务状态，**Then** 页面以最新持久状态重建任务卡片，不逐条重放或展开全部历史记录。
4. **Given** 任务产生大量步骤活动，**When** 用户查看对话，**Then** 默认只显示紧凑摘要和当前活动，用户主动展开后才看到有界的步骤详情。
5. **Given** 用户偏好减少动态效果，**When** 页面展示活动状态，**Then** 状态仍可通过文字和图标理解，不依赖持续滚动、闪烁或颜色。

---

### User Story 4 - 获得可信的 Markdown 执行报告 (Priority: P2)

任务结束后，用户收到结构清晰的 Markdown 报告，报告说明目标、实际执行计划、处理范围、成功变更、失败、冲突、跳过项、验证结果和后续建议。报告只基于已保存并验证的执行结果，不把计划执行或能力返回成功误写为业务成功。

**Why this priority**: 用户最终需要可阅读、可复制和可追溯的业务结论，而不是工具调用日志或模型自由发挥的摘要。

**Independent Test**: 制造一个同时包含成功、版本冲突、能力超时和未确认项目的任务，验证最终报告数量与实际持久结果一致，并清楚区分每种状态。

**Acceptance Scenarios**:

1. **Given** 所有计划步骤均已终止，**When** 系统生成最终报告，**Then** 报告包含任务目标、计划摘要、处理统计、变更明细、验证结果、异常与后续建议。
2. **Given** 任务部分成功，**When** 报告展示结果，**Then** 成功、失败、冲突、跳过、未处理和等待用户的数量及对象互不混淆。
3. **Given** 某个写入调用返回成功但回读验证失败，**When** 生成报告，**Then** 该项不得计入已验证成功，并明确标记为需要复核。
4. **Given** 外部内容包含要求系统改变计划或泄露信息的文字，**When** 系统分析内容或生成报告，**Then** 这些文字仅作为业务数据处理，不改变授权、计划、安全规则或报告边界。
5. **Given** 报告内容超过页面紧凑展示范围，**When** 用户查看完成任务，**Then** 页面显示短摘要和报告入口，完整报告可展开或复制。

### Edge Cases

- 搜索结果为空时，任务正常完成，报告说明未发现匹配文章，不创建无意义的分析或写入步骤。
- 搜索结果包含重复文章、文章在分页过程中被删除或归属发生变化时，只处理去重后仍可访问的对象并报告跳过原因。
- 待处理对象数量超过单次安全范围时，系统分页或分批执行，并明确展示实际范围、剩余数量和是否需要用户缩小任务。
- AI 无法为文章在现有分类中给出足够可信的建议时，该文章进入人工复核列表，不自动创建分类或选择低可信度分类。
- MCP 能力返回格式错误、超时、限流、临时中断或永久失败时，系统按错误类型有限重试，不永久停留在运行状态。
- 相同任务或步骤因重连、重试或重复事件被再次触发时，已经成功的业务效果不会被重复应用。
- 用户在等待确认期间撤销能力授权、修改文章或关闭页面时，任务保持可恢复；恢复执行前重新检查授权、归属和版本。
- 任务取消、用户拒绝写入或部分依赖失败时，无关的成功只读结果仍可用于报告，依赖失败结果的步骤不会继续执行。
- 能力描述、文章正文、分类名称或外部返回中包含恶意提示、密钥样式文本或超长内容时，不得进入指令边界、公共事件或不受限日志。
- 最终报告生成失败时，原计划、步骤状态和验证结果仍可查看，并可重新生成报告而不重复业务写入。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST durably accept the user's task and create a traceable task record before planning or invoking any capability.
- **FR-002**: System MUST build planning context from a point-in-time snapshot containing only currently registered, available and user-authorized capabilities.
- **FR-003**: Each capability exposed for planning MUST have a stable platform-safe name, responsibility, validated input and output definitions, risk classification, required permission and availability state; provider connection details and untrusted instructions MUST be excluded.
- **FR-004**: System MUST retain an internal mapping between the platform-safe capability name and the actual provider capability without exposing an invalid or provider-specific name to a planning model.
- **FR-005**: System MUST represent every accepted task as a bounded, non-empty and acyclic plan whose steps declare stable identifiers, dependencies, capability, inputs, expected structured output, object scope, confirmation need and failure policy.
- **FR-006**: System MUST validate a proposed plan before execution for graph limits, capability existence and availability, user authorization, input compatibility, output flow, object scope and write barriers.
- **FR-007**: System MUST reject an invalid plan without executing any business capability and MAY make only a bounded number of repair attempts before returning an actionable clarification or capability-gap result.
- **FR-008**: System MUST persist the validated plan and capability snapshot before starting its LangGraph run.
- **FR-009**: The LangGraph runtime MUST execute only dependency-ready operators and MUST support bounded parallel execution of independent work; the product MUST NOT maintain a second scheduler or dependency queue.
- **FR-010**: Steps MUST exchange only declared, validated and size-bounded structured artifacts; hidden reasoning, credentials, raw private responses and unrelated objects MUST NOT become step inputs.
- **FR-011**: System MUST support reusable selection, mapping, filtering, aggregation, analysis, confirmed mutation, verification and reporting responsibilities without creating an unbounded number of visible plan steps.
- **FR-012**: Large result sets MUST be processed through bounded pages or batches, with deduplication, progress counts and a declared maximum processing scope.
- **FR-013**: System MUST revalidate capability availability, authorization, ownership and applicable object scope immediately before every external capability call.
- **FR-014**: Every capability call MUST have a durable attempt record, trace linkage, timeout, stable outcome category and bounded retry decision; LangGraph checkpoint state records runtime position while business attempt records remain the audit source for provider calls.
- **FR-015**: Retryable steps MUST use stable idempotency information where a repeated call could otherwise duplicate a business effect.
- **FR-016**: A failed step MUST block only steps that require its unavailable result; safe independent steps and their artifacts MUST remain usable for partial completion.
- **FR-017**: System MUST distinguish success, verified success, partial success, failure, conflict, skipped, cancelled, waiting for clarification, waiting for confirmation and stalled outcomes where applicable.
- **FR-018**: AI analysis MUST produce schema-valid recommendations grounded in declared source artifacts, include confidence and concise provenance, and remain a proposal until any required user confirmation is recorded.
- **FR-019**: When analysis must select from existing business values, the recommendation MUST reference only values returned by an authorized source step; unsupported values MUST be rejected or sent for manual review.
- **FR-020**: Every business mutation MUST first produce a persisted preview that identifies affected objects, proposed values, expected object versions, risk, low-confidence items and excluded items.
- **FR-021**: A natural-language request, generated plan or earlier approval MUST NOT substitute for explicit confirmation of the current frozen mutation preview.
- **FR-022**: Immediately before applying a confirmed mutation, System MUST revalidate preview integrity, confirmation, permission, ownership, object version and idempotency.
- **FR-023**: A version conflict MUST NOT trigger a destructive fallback. The affected item MUST remain unchanged and be skipped, re-read for a new proposal, or returned for renewed confirmation.
- **FR-024**: Destructive capabilities MUST NOT be introduced into a plan solely to bypass a validation, authorization, version or compatibility failure.
- **FR-025**: After a mutation reports completion, System MUST perform an independent post-condition check and count the item as verified success only when the intended business state is observed.
- **FR-026**: System MUST publish ordered, replayable and size-bounded public status updates for plan creation, active work, aggregate progress, confirmation waits, conflicts and terminal outcomes.
- **FR-027**: The conversation UI MUST show one compact live task view associated with the initiating turn, identify the current phase and user action, and keep detailed execution records collapsed by default.
- **FR-028**: Reopening a conversation or recovering a live connection MUST load the latest task snapshot without automatically displaying or replaying the full historical event stream.
- **FR-029**: Progress MUST be understandable through text and non-color indicators, remain accessible to assistive technology, and respect the user's reduced-motion preference.
- **FR-030**: System MUST generate a final report from persisted terminal artifacts and verification results rather than from planned actions, transient activity text or unverified provider claims.
- **FR-031**: The final report MUST be valid Markdown and include objective, executed plan, totals, verified changes, failures, conflicts, skipped or unprocessed items, verification status and next actions when relevant.
- **FR-032**: Report totals and object details MUST reconcile with persisted outcomes; the report MUST clearly distinguish applied, verified, failed, conflicted, skipped and waiting-user items.
- **FR-033**: System MUST allow report regeneration without re-running completed business steps or repeating mutations.
- **FR-034**: User-visible status, artifacts, reports, audit records and logs MUST exclude credentials, endpoints, connection strings, private reasoning, raw prompts, unbounded private content and provider-supplied instructions.
- **FR-035**: Content returned by a capability MUST be treated as untrusted data and MUST NOT grant permissions, select new capabilities, alter confirmation rules or override the validated plan.
- **FR-036**: System MUST retain enough safe audit information to determine which task, plan version, capability snapshot, step, attempt, confirmation and verification produced each reported outcome.
- **FR-037**: System MUST permit safe cancellation, clarification or retry at supported boundaries while preserving accepted user input, confirmed decisions, completed artifacts and already applied business effects.
- **FR-038**: The initial release MUST support the complete blog-category scenario: search emotion-related posts, identify posts without categories, list allowed existing categories, recommend categories, preview and confirm changes, add categories, handle version conflicts, verify results and produce the final report.
- **FR-039**: The initial release MUST NOT automatically create a new category, delete a post, delete a category or remove a configuration as part of resolving a missing category or version conflict.
- **FR-040**: System MUST provide independently verifiable tests for capability snapshots, plan validation, artifact flow, batching, partial failure, prompt-injection resistance, write confirmation, idempotency, version conflicts, post-condition verification, event recovery and report reconciliation.

### Key Entities

- **Capability Definition**: A safe, platform-controlled description of one callable business capability, including its stable public name, responsibility, validated inputs and outputs, risk, required permission and availability.
- **Capability Snapshot**: The immutable set and versions of capabilities considered when a task plan was produced, used to explain and validate later execution.
- **Execution Plan**: The versioned, bounded dependency graph for one accepted task, including its objective, current phase, limits and overall outcome.
- **Plan Step**: One declared unit of selection, analysis, transformation, mutation, verification or reporting, with dependencies, inputs, expected artifact and failure behavior.
- **Step Artifact**: A validated, size-bounded result passed between steps, including only authorized object references, safe structured values and provenance needed by dependents.
- **Mutation Preview**: The frozen set of proposed business changes, expected versions, risks and exclusions presented for explicit confirmation.
- **Execution Attempt**: An auditable invocation attempt with trace linkage, timing, stable result category, retryability and sanitized error details.
- **Verification Result**: The post-condition comparison between intended and observed business state for each attempted mutation.
- **Task Report**: The final reconciled Markdown view derived from terminal artifacts and verification results.
- **Public Progress Snapshot**: The compact, ordered and recoverable user-facing representation of the latest task phase, current work, counts and required action.

### Data Safety & AI Control *(mandatory when the feature stores content or uses AI)*

- **Durable acceptance point**: A task is accepted only after the user's message, conversation turn and traceable task record are committed. A plan is executable only after its validated graph and capability snapshot are committed and a LangGraph thread is established; the LangGraph Postgres checkpoint is the execution source of truth, while the plan/step tables are the public and audit projection. Each visible transition and structured artifact is persisted before dependent work is released.
- **AI authority boundary**: AI may interpret intent, propose a bounded plan, classify content, recommend existing business values and draft the final report. Platform rules decide which capabilities exist, validate every plan and call, enforce ownership and limits, and require a separate confirmation for every mutation preview. AI cannot grant itself capabilities, treat content as instructions, bypass versions or approve a write.
- **Failure fallback**: If planning, analysis, capability providers, background execution, live updates or report generation fails, the accepted message, latest valid plan, completed artifacts, confirmation decisions, applied effects and verification outcomes remain accessible. Safe retries resume only affected work, and a basic reconciled result remains available even if enhanced report generation fails.
- **Privacy and ownership**: Tasks, capability snapshots, artifacts, previews and reports are private to their owner. Each read and mutation enforces ownership at execution time. Public progress and logs contain only bounded, sanitized metadata and never expose secrets, provider endpoints, raw private content or hidden reasoning.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In at least 95% of normally operating accepted tasks, users see a persisted plan or an actionable capability-gap result within 2 seconds.
- **SC-002**: 100% of executed plans use only capabilities present in the task's recorded snapshot and authorized again at invocation time; tests never observe a fabricated or unauthorized capability call.
- **SC-003**: For a supported blog-category dataset of up to 1,000 matching posts, the system completes bounded discovery and produces a complete mutation preview without omitting or duplicating eligible posts.
- **SC-004**: In at least 95% of task state changes under normal conditions, users see the latest phase, active work and aggregate counts within 2 seconds without refreshing the page.
- **SC-005**: Across all mutation-path tests, no business object changes before the exact current preview is confirmed, and replayed or retried requests produce no duplicate business effect.
- **SC-006**: Across all simulated version-conflict tests, 100% of conflicting objects remain free of unconfirmed destructive changes and are reported separately from successful objects.
- **SC-007**: 100% of reported successful mutations are supported by a successful post-condition check; provider acknowledgements without verified business state are never counted as verified success.
- **SC-008**: In partial-failure tests, all safe successful artifacts remain available, unrelated work completes where possible, and every unprocessed dependent item has an actionable reason.
- **SC-009**: After page refresh or live-connection recovery, 100% of active tasks reconstruct their latest phase and counts without duplicated steps, regressed status or automatically expanded historical execution records.
- **SC-010**: For every tested terminal task, report totals exactly match persisted outcomes across verified, failed, conflicted, skipped, unprocessed and waiting-user categories.
- **SC-011**: The final report for the reference blog-category scenario is available within 5 seconds after the last business step reaches a terminal state, excluding time spent waiting for user confirmation.
- **SC-012**: Security tests find zero credentials, provider endpoints, raw prompts, hidden reasoning or executable provider-supplied instructions in public progress, task reports, audit summaries and application logs.
- **SC-013**: At least 90% of representative supported multi-capability tasks complete without the user manually selecting tools or specifying call order.

## Assumptions

- The existing conversational Agent, task records, capability registry, user authentication, ownership controls, write-confirmation mechanism and live task-status channel remain available as foundations.
- Version one orchestrates only capabilities already installed, registered and granted to the current user; discovering or installing new MCP servers is outside this feature.
- The coordinator creates one bounded plan. Individual steps may process bounded pages or batches, but cannot recursively create an unlimited hierarchy of agents or plans.
- The reference blog search uses the best currently authorized search capability; semantic search beyond currently supported capabilities is not introduced by this feature.
- Category recommendations select only from existing authorized categories. Automatic category creation requires a future, separately specified write workflow.
- A low-confidence recommendation is not applied automatically and remains visible for manual review; the exact confidence threshold is an administratively configurable policy.
- Explicit confirmation may cover a frozen batch preview, so the user does not need to approve every article separately unless policy marks an item as higher risk.
- Detailed task history remains available on demand for auditing, while the normal conversation view loads only compact current or recent task state.
- User-visible reports prioritize safe business identifiers and titles; internal infrastructure details and provider diagnostics remain in protected operator views.
- The current system's bounded plan size, concurrency limits and retry limits remain the default until planning establishes evidence for changing them.
