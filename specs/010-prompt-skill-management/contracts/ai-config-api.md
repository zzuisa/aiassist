# AI 配置中心接口契约

## 模块列表

`GET /api/v1/ai-config/modules`

返回用户可管理模块的 key、标题、说明、生效 Prompt/Skill 版本摘要、允许工具和不可编辑安全边界说明。

## 版本管理

- `GET /api/v1/ai-config/modules/{module_key}`：模块与历史版本。
- `POST /api/v1/ai-config/modules/{module_key}/prompt-versions`：保存新的 Prompt 版本。
- `POST /api/v1/ai-config/modules/{module_key}/skill-versions`：保存新的 Skill 版本。
- `POST /api/v1/ai-config/modules/{module_key}/activate`：启用指定版本。
- `POST /api/v1/ai-config/modules/{module_key}/dry-run`：对指定或生效版本执行无写入试运行。

请求不得接受安全前缀、权限、schema、确认策略、凭据或未注册工具定义。所有响应不得返回凭据、其他用户配置或模型推理过程。

## 对话路由调用

模型输出的路由对象包含 route kind、目标和可选单项 `tool_call`；`tool_call` 的 `name` 必须来自候选工具，`arguments` 必须通过该工具公开参数 schema。若参数遗漏且 Skill 含安全默认值，服务在校验前合并默认值；写工具仍要求确认。
