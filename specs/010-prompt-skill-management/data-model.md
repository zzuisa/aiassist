# Data Model: 集中 Prompt 与 Skill 管理

## AIConfigProfile

- `id`, `user_id`, `module_key`, `active_prompt_version_id`, `active_skill_version_id`, timestamps
- 每用户每模块唯一；只保存当前生效引用。

## AIPromptVersion

- `id`, `profile_id`, `version_number`, `editable_instruction`, `change_summary`, `created_at`
- 不可变；平台安全前缀和 schema 不保存在用户可编辑字段中。

## AISkillVersion

- `id`, `profile_id`, `version_number`, `name`, `instruction`, `allowed_tool_keys`, `parameter_defaults`, `output_guidance`, `enabled`, `created_at`
- 默认参数必须通过对应工具的公开参数 schema 校验；工具必须属于模块允许集合。

## AIConfigBinding

- `id`, `user_id`, `module_key`, `prompt_version_id`, `skill_version_id`, `model_key`, `run_reference`, `created_at`
- 一次运行创建一条不可变绑定；可关联 Agent task/run、Blog run、Job 或其他运行。

## State transitions

- 草稿版本保存 → 试运行（可重复） → 启用为 profile 当前版本。
- 历史版本 → 回退（创建新的当前引用，不改写历史版本）。
- 运行开始 → 创建 binding → 调用模型/工具 → 记录状态；配置版本不能在运行期间替换。
