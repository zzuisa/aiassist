# 修复复盘：博客 MCP 工具名不兼容 Anthropic（2026-08-19）

- 分类：AI Assist 修复复盘
- 影响范围：通过 Claude/Anthropic 调试或调用 AI Assist 内部博客 MCP 的用户

## 现象

博客 MCP 可以完成 Streamable HTTP 连接与工具发现，但 Claude 在注册工具时提示 `Invalid tool name(s) for Anthropic`，六个 `blog.*` 工具均不可用。错误明确要求工具名只能包含字母、数字、下划线和连字符，且最长 64 个字符。

## 根因

MCP Server 最初采用点号作为命名空间分隔符，例如 `blog.list_posts`。该名称可被 MCP SDK 正常发现和调用，但不满足 Anthropic API 对工具名的更严格校验规则。现有契约测试只验证了工具集合，没有覆盖下游模型供应商的名称字符集限制。

## 修改

- 将六个工具统一重命名为 `blog_list_posts`、`blog_get_post`、`blog_search_posts`、`blog_timeline`、`blog_list_categories` 和 `blog_list_tags`。
- 不再暴露带点号的旧名称，避免 Claude 因工具清单中存在任一非法名称而整体拒绝注册。
- 在 MCP 契约测试中增加 Anthropic 兼容正则 `[A-Za-z0-9_-]{1,64}` 断言。
- 同步更新 MCPJam/Claude 使用说明。

## 验证

1. Ruff、Shell 语法检查和 Git diff 检查通过。
2. MCP、认证及文章 API 相关回归共 23 项通过。
3. 后端热更新后健康检查通过。
4. 使用官方 MCP 客户端经公网 Nginx 完成握手，发现的六个工具名全部通过 Anthropic 兼容正则。
5. 使用短期探测令牌成功调用 `blog_list_posts`，返回非错误结果；探测过程中未输出或持久化令牌。

## 日志检索方式

服务端按 MCP 路径检索连接和调用状态：

```bash
./deploy/scripts/deploy.sh logs backend | rg '/api/v1/mcp/blog/mcp|ERROR|exception'
./deploy/scripts/deploy.sh logs nginx | rg '/api/v1/mcp/blog/mcp'
```

Anthropic 的名称校验发生在客户端或模型 API 注册阶段，服务端访问日志可能只有工具发现成功记录。排查时还应检查 Claude 客户端错误信息中的非法工具名，但不得记录或分享 Bearer Token。

## 遗留风险

- 工具重命名属于协议目录变更；已缓存旧工具清单的客户端需要断开后重新连接或刷新工具列表。
- 其他模型供应商可能存在不同的工具数量、描述长度或 JSON Schema 限制，新增工具时需继续在契约层加入跨供应商兼容断言。
- 线上后端目前已热更新并完成验证，源代码仍需按项目发布流程提交和纳入下一次正式发布记录。
