# Agent 使用手册

Agent 是 AI Assist 内置的对话入口：普通问候和“你能做什么”可直接回复；查询、分析和写入请求会先生成受控任务。写入操作必须先显示预览并由用户确认，MCP 外部能力只允许由服务器管理员预先配置。

## 1. 最小可用配置

先从示例创建 `.env`，并保留已有数据库、JWT 与 RabbitMQ 配置。要使用任务型对话路由，需要配置一个 LLM 提供商：

```dotenv
LLM_PROVIDER=openai
LLM_DEFAULT_MODEL=gpt-4o-mini
# 可选：兼容 OpenAI 的自定义网关地址；留空即使用官方地址
LLM_BASE_URL=
```

将 API 密钥写入 `deploy/secrets/llm_provider_key`，不要写入 `.env`、Git、日志或前端：

```bash
umask 077
printf '%s' '你的提供商密钥' > deploy/secrets/llm_provider_key
chmod 600 deploy/secrets/llm_provider_key
chown 10001 deploy/secrets/llm_provider_key
```

也可选择：

| 提供商 | `.env` | 密钥文件 |
|---|---|---|
| OpenAI | `LLM_PROVIDER=openai` | 必需：`deploy/secrets/llm_provider_key` |
| Anthropic | `LLM_PROVIDER=anthropic` | 必需：`deploy/secrets/llm_provider_key` |
| Ollama | `LLM_PROVIDER=ollama`、`LLM_BASE_URL=http://主机:11434`、`LLM_DEFAULT_MODEL=模型名` | 不需要 |
| 不使用模型 | `LLM_PROVIDER=none` | 不需要；仅确定性问候与能力说明可直接回复，其他请求会提示稍后重试 |

生产环境通过 `./deploy/scripts/deploy.sh up` 发布。脚本会校验必需密钥、修复文件权限、执行迁移并检查 API 与 worker 健康状态。

## 2. 可选：配置 MCP 外部工具

不使用 MCP 时无需创建文件；部署脚本会生成空占位文件，并将其视为“未配置 MCP”。如需启用 MCP：

1. 复制 `deploy/secrets/mcp-connections.example.json` 为 `deploy/secrets/mcp_connections.json`。
2. 填写受控服务端的连接信息和令牌；此文件仅在服务器上保存，不提交 Git。
3. 为每个工具填写 `tool_policies`。只读工具标为 `read`；写工具必须标为 `write` 且 `previewable: true`，否则不会对用户开放。
4. 设为仅运行用户可读：`chmod 600 deploy/secrets/mcp_connections.json && chown 10001 deploy/secrets/mcp_connections.json`。
5. 重新部署。

最小的“已配置但没有外部工具”文件为：

```json
{"connections": {}}
```

不要让浏览器或用户消息提供 MCP URL、令牌或连接字符串。Compose 会把该文件挂载为容器内的 `/run/secrets/mcp_connections`；`.env` 中的 `MCP_SECRETS_FILE` 会由部署配置覆盖，无需改成真实路径。

## 3. 使用与排障

- 打开“Agent”，直接输入自然语言请求。任务会显示“正在理解请求”“等待确认”等状态。
- 出现“等待确认”时，先核对预览再确认；未确认前不会执行写入。
- 出现“可以安全重试”时，可在该轮消息上点击重试。消息与失败记录会保留。
- 查看运行状态：`./deploy/scripts/deploy.sh ps`。
- 查看日志：`./deploy/scripts/deploy.sh logs worker-heavy`，再按 turn ID 或 `conversation_turn_execution_failed` 检索。

常见检查顺序：先确认 `LLM_PROVIDER` 与密钥文件是否匹配；再检查容器健康状态；最后检查 MCP 文件是否为有效 JSON（或保持为空/`{"connections": {}}`）。
