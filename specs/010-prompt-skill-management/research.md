# Research: 集中 Prompt 与 Skill 管理

## Decision: 统一版本化配置而非继续复制每模块表

**Rationale**: 当前八个 LLM 场景都通过同一网关并具备明确 scenario/schema；统一模块目录和不可变版本可提供一致的编辑、回退、试运行和审计能力。

**Alternatives considered**:

- 每个模块新增独立表：会复制版本、所有权和 UI 逻辑，长期难维护。
- 仅用环境变量：无法按用户编辑、试运行或回退，且不可审计。

## Decision: Prompt 可编辑区与平台强制前缀分离

**Rationale**: 用户可调整语气、目标、业务默认值和工具策略，但不能移除 JSON schema、权限、确认、数据所有权和事实安全边界。

**Alternatives considered**:

- 保存完整任意 Prompt：容易覆盖安全约束，无法可靠验证。
- 完全不允许编辑：不满足用户可灵活调整需求。

## Decision: LLM 生成调用参数，注册表做最终校验

**Rationale**: 模型负责语义、上下文和 Skill 默认值；确定性代码负责权限、类型、范围、审计与写入确认。这样避免正则对自然语言的脆弱假设。

**Alternatives considered**:

- 程序解析所有参数：不能处理语义和上下文，当前“最近文章”即为例证。
- 允许模型直接调用：会绕过工具 schema 和确认机制。

## Decision: 既有 Blog Skill 渐进兼容

**Rationale**: Blog Skill 已有用户版本、作用域和运行历史，首期以适配器纳入中心，避免破坏文章优化。

**Alternatives considered**:

- 立即删除并重建：会破坏历史引用与用户配置。
