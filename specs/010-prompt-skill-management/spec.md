# Feature Specification: 集中 Prompt 与 Skill 管理

**Feature Branch**: `010-prompt-skill-management`  
**Created**: 2026-08-14  
**Status**: Draft  
**Input**: User description: "将所有写死的系统提示词和 Agent/业务 Skill 集成到系统中统一管理，支持用户按模块灵活调整、版本化、测试和安全回退；LLM 根据语义和 Skill 生成工具调用参数，避免将对话语义硬编码到程序。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 管理模块提示词 (Priority: P1)

管理员可以查看每个 AI 模块的生效系统提示词，创建、编辑、试运行、启用或回退版本，无需改动程序代码。

**Why this priority**: 现有行为散落在程序中，无法由用户快速、安全且可追溯地调整。

**Independent Test**: 为一个模块启用新版本并试运行，验证仅后续运行使用新版本；回退后恢复旧行为。

**Acceptance Scenarios**:

1. **Given** 管理员打开 AI 配置中心，**When** 选择一个模块，**Then** 能看到用途、生效版本、可编辑内容、不可编辑安全边界和版本历史。
2. **Given** 管理员保存合规的新版本，**When** 启用该版本，**Then** 后续新运行使用新版本，历史运行仍引用原版本。
3. **Given** 新版本不符合预期，**When** 管理员回退，**Then** 后续运行恢复历史版本且动作可追溯。

---

### User Story 2 - 用 Skill 驱动 Agent 工具调用 (Priority: P1)

用户以自然语言请求 Agent 服务时，模型依据当前模块 Prompt、对话上下文、适用 Skill 与已授权工具决定工具及参数；例如“最近文章”按 Skill 默认策略完成查询。

**Why this priority**: 对话体验应由语义和配置驱动，不能依赖覆盖少量措辞的硬编码正则。

**Independent Test**: 发送“最近文章”，验证模型产生受约束的文章查询调用并使用 Skill 的默认数量；修改默认值后新请求反映新值。

**Acceptance Scenarios**:

1. **Given** 文章查询 Skill 的默认返回量为 10，**When** 用户说“最近文章”，**Then** Agent 查询并展示最近 10 项，不要求补充数量。
2. **Given** 用户说“最近 3 篇文章”，**When** Agent 执行，**Then** 模型传入数量 3 并展示可用结果。
3. **Given** 模型请求未授权工具、未知参数或超出安全范围的参数，**When** 系统校验，**Then** 不执行调用并给出安全澄清。

---

### User Story 3 - 统一测试与审计 (Priority: P2)

管理员可以对 Prompt/Skill 版本进行不写入业务数据的试运行，并在实际运行记录中识别模块和配置版本。

**Why this priority**: 可编辑行为必须可先验证、后启用，并能在异常时追溯。

**Independent Test**: 对未启用版本试运行，确认结果受结构校验且业务对象未改变；查看实际运行的版本绑定。

**Acceptance Scenarios**:

1. **Given** 管理员编辑中的版本，**When** 提交测试样例，**Then** 返回结构校验结果或安全错误，不创建或修改业务数据。
2. **Given** 一次 AI 运行完成，**When** 管理员查看详情，**Then** 能识别所用模块、Prompt 与 Skill 版本，且看不到其他用户配置或敏感上下文。

### Edge Cases

- 模型不可用、超时或返回格式非法时，业务数据保持不变，并返回可重试提示。
- 模块没有自定义版本时，使用受版本管理的内置基线，功能不中断。
- 安全边界、所有权、schema、限额与写入确认不能被配置削弱。
- 已停用版本不能用于新运行；已开始和历史运行保留固定版本绑定。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 系统 MUST 为每个当前使用 LLM 的业务模块提供用途说明、版本化基线提示词和配置入口。
- **FR-002**: 系统 MUST 允许有管理权限的用户创建、编辑、启用、停用、比较和回退模块 Prompt/Skill 版本。
- **FR-003**: 系统 MUST 在每次新 AI 运行开始时固定绑定 Prompt 与 Skill 版本，后续编辑不得改变该次或历史运行。
- **FR-004**: 系统 MUST 支持模块专属 Skill，包含适用范围、目标、指令、允许工具、参数默认值和输出要求；只允许引用已注册兼容工具。
- **FR-005**: 系统 MUST 让对话 Agent 将用户语义、上下文、适用 Skill 与候选工具提交给模型，由模型生成受约束的工具调用和参数。
- **FR-006**: 系统 MUST 对模型调用强制执行权限、所有权、工具参数 schema、资源限额及写入确认校验；配置不能绕过它们。
- **FR-007**: 系统 MUST 对未给出可选条件的只读查询使用当前 Skill 默认参数，而不是要求用户重复补充信息。
- **FR-008**: 系统 MUST 提供不写入业务数据的 Prompt/Skill 试运行，并执行与实际运行相同的结构和安全校验。
- **FR-009**: 系统 MUST 记录 AI 运行的模块、Prompt/Skill 版本、模型、状态和安全错误类别，且不得记录密钥、Cookie、原始敏感上下文或模型推理过程。
- **FR-010**: 系统 MUST 保留现有博客优化 Skill 的自定义、版本和作用域能力，并将其纳入统一配置中心。
- **FR-011**: 系统 MUST 为所有既有 LLM 场景提供受版本管理的默认基线，使未自定义时原有功能保持可用。
- **FR-012**: 系统 MUST 明确标记可编辑字段和平台强制安全规则，并拒绝修改后者的配置。

### Key Entities *(include if feature involves data)*

- **AI 模块**: 可调用 LLM 的业务能力，包含用途、输入输出契约和安全边界。
- **Prompt 版本**: 模块的版本化系统行为说明，具有状态和不可变历史。
- **Skill 版本**: 面向业务目标/作用域的版本化规则，包含允许工具、参数默认值与模块指令。
- **配置绑定**: 一次 AI 运行固定引用的 Prompt 与 Skill 版本。
- **试运行**: 使用指定版本和样例、但不写入业务数据的验证结果。

### Data Safety & AI Control *(mandatory when the feature stores content or uses AI)*

- **Durable acceptance point**: 配置在管理员明确保存、校验并启用后生效；业务内容仍遵循既有保存与确认点。
- **AI authority boundary**: AI 可提出 schema 约束的只读调用和写入预览；所有写入仍须权限与人工确认，AI 不得修改平台安全规则。
- **Failure fallback**: 模型或配置不可用时不改变业务数据；使用受版本管理的基线或返回可重试提示。
- **Privacy and ownership**: 配置和运行记录默认仅对所有者/获授权管理员可见；提示中不得注入或展示凭据或其他用户数据。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 管理员可在 3 分钟内完成任一 AI 模块 Prompt/Skill 的保存、试运行和启用，无需代码发布。
- **SC-002**: 对“最近文章”等未带数量的只读请求，100% 使用生效 Skill 默认值完成查询或给出模型不可用提示，不出现“缺少必要数量条件”。
- **SC-003**: 100% 的新 AI 运行可关联至模块和配置版本，且历史绑定不会被后续编辑改变。
- **SC-004**: 无效配置、未授权工具与非法参数 100% 在业务写入前被拒绝。
- **SC-005**: 原有博客优化配置与历史运行升级后均可查看，并在默认配置下继续可用。

## Assumptions

- 首期沿用现有登录、所有权和管理权限；普通用户默认只能管理自己的 AI 配置。
- 首期覆盖当前已调用 LLM 的业务模块，不包括纯规则、语音转写、图像生成或第三方 Radio 优化。
- 平台安全前缀、schema 注入、所有权/权限检查、调用限额和写入确认属于不可编辑系统边界。
- 既有 Blog Skill 是统一 Skill 体系的迁移来源，保留其作用域优先级与版本不可变性。
