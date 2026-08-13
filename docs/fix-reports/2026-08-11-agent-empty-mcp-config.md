# 修复复盘：Agent 空 MCP 配置导致会话失败（2026-08-11）

- 分类：AI Assist 修复复盘
- 影响对象：会话 `5f9d8cc9-cdc0-48d7-8d0b-0583951f8a96`（仅业务对象 ID）

## 现象

Agent 的问候和能力说明可以正常回复，但任务型消息连续转为 `failed`，没有路由决定或 AgentTask；用户只能看到“消息已保留，可以安全重试”。

## 根因

部署脚本为可选 MCP 功能创建了空的 `deploy/secrets/mcp_connections.json` 占位文件。MCP 配置加载器将空文件按非法 JSON 处理；每个非快路径会话在同步 MCP 能力时抛出异常，随后由 worker 顶层 finalizer 标记失败。该异常发生在 LLM 路由与其“不可用时澄清提示”降级逻辑之前。

## 修改

- 将空白 MCP secrets 文件视为未配置 MCP，返回空连接集合。
- 增加安全回归测试，覆盖部署脚本生成的空占位文件。
- worker 失败日志新增 turn ID 与异常类型，不记录异常原文，避免泄露外部连接或凭据。
- 新增 Agent 使用手册，说明 LLM、MCP 配置和排障步骤。

## 验证

1. MCP secrets 边界与 turn finalizer 测试共 12 项通过。
2. GitHub CI `31536806611` 全部通过（后端、前端、Compose 与端到端冒烟）。
3. 生产迁移到 head，网关 `/health/ready` 返回 ready，fast worker ping 返回 pong。
4. 生产 worker 读取空 MCP 文件后返回 `connections=0`，不再抛出配置异常。

## 日志检索方式

按 turn ID 和安全事件名检索，不输出认证信息、MCP URL、令牌或提示词：

```bash
./deploy/scripts/deploy.sh logs worker-heavy \
  | rg 'conversation_turn_execution_failed|5f9d8cc9-cdc0-48d7-8d0b-0583951f8a96'
```

## 遗留风险

- 未配置 LLM 时，任务型消息会降级为澄清提示，不会执行任务；管理员仍需按使用手册配置 LLM 才能启用任务路由。
- 既有失败 turn 不会自动重放，避免在用户不知情的情况下执行潜在写操作；用户可在界面中逐条安全重试。
