# Research: 对话式 Agent 与 MCP 任务路由

**Feature**: 008-conversational-agent-mcp | **Date**: 2026-08-10

## R-001：对话与任务的统一路由

**Decision**: 使用两段式路由。严格限定的纯问候、感谢和能力说明使用确定性快路径；其余消息通过 LLM 生成版本化 `conversation-route.v1`，只表达 route kind、目标、范围、参数、读写性质和候选能力，不保存或展示推理链。策略层对结果做最终校验。

**Rationale**: 当前关键词分类器把 `hi` 送进 `capability.unknown`，继续添加关键词不能可靠覆盖自然表达。结构化路由能处理混合消息和多轮指代，而策略层避免把模型判断直接当授权。

**Alternatives considered**:

- 扩大关键词表：实现快，但同义表达、混合语言和复合任务持续漏判。
- 所有消息都直接交给模型：问候延迟和成本更高，模型故障会破坏基础入口。
- 让模型直接调用工具：缺少确定性权限、确认和参数审计边界。

## R-002：能力候选与参数生成

**Decision**: 工具注册表提供安全清单；先按名称、职责、读写性质、权限和会话对象类型缩减到最多 12 个候选，再让路由模型选择。只有被策略层接受的单个工具参数 schema 会进入参数生成阶段，输出必须再次校验。

**Rationale**: 避免把所有工具细节、端点或服务器说明放入提示词，也控制上下文大小。无需引入被宪法延期的向量数据库。

**Alternatives considered**:

- 把全部工具 schema 发送给模型：工具增加后上下文不可控，且扩大提示注入面。
- 完全确定性映射：无法覆盖用户要求的自然对话和新增 MCP 能力。

## R-003：MCP 协议与 SDK

**Decision**: 使用官方 Python SDK 2.x，后端作为 MCP client 连接 operator 预配置的 Streamable HTTP 服务；首版不支持用户提供任意 URL 或 stdio。采用 2026-07-28 协议语义，并让 SDK 负责对旧版服务器的协商兼容。

**Rationale**: 官方 2026-07-28 规范采用无会话的自描述请求、`server/discover` 和可缓存列表结果；官方 SDK 2.x 是稳定线并兼容旧协议。Streamable HTTP 适合现有 Compose 服务端架构，浏览器无需接触 MCP 凭据。

**Alternatives considered**:

- 手写 JSON-RPC client：协议演进、授权和兼容成本高。
- stdio：等同允许启动本地命令，扩大自托管服务攻击面。
- 浏览器直连：暴露凭据、增加 CORS 和授权复杂度。

**Primary sources**:

- [MCP 2026-07-28 release](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- [Official Python SDK v2 changes](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/whats-new.md)
- [Official Streamable HTTP specification](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/transports/streamable-http.mdx)

## R-004：授权与凭据

**Decision**: 数据库不保存端点或令牌，只保存不可逆 `config_key` 与授权元数据。实际连接配置从只读 secrets provider 解析。远程授权遵守资源绑定、issuer 校验、PKCE 和禁止 token passthrough；首版运维流程负责建立连接，产品 UI 只管理是否允许当前用户使用具体工具。

**Rationale**: 个人自托管仍需要防止提示、日志和数据库备份泄露外部服务令牌。工具级 grant 比连接级全开放更符合最小权限。

**Alternatives considered**:

- 在业务表存明文 token：备份和审计泄露风险不可接受。
- 自动按需授权：会把普通聊天变成权限升级入口。
- 一个连接下全部工具默认开放：无法控制高风险能力。

**Primary source**: [MCP authorization security requirements](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization)

## R-005：外部结果与提示注入

**Decision**: MCP 返回值是数据而非指令。gateway 限制大小和媒体类型，按工具声明的结果 schema 校验；原始 server instructions 不进入路由提示。任何后续工具调用都必须产生新的本地计划和安全检查，写入仍需 PendingWrite。

**Rationale**: MCP 工具内容可能包含“忽略规则”“确认写入”等恶意文本。将结果直接拼入 agent system context 会越过用户授权边界。

**Alternatives considered**:

- 信任已配置服务器的所有输出：连接被攻陷或数据源含恶意内容时没有隔离。
- 允许模型自由循环调用：难以限定成本、范围与外部影响。

## R-006：持久化会话和任务恢复

**Decision**: 每条用户消息与对应 Turn 在任何模型或工具调用前同事务保存。Turn 关联可选 AgentTask/Job。worker 顶层 finalizer 记录错误终态；beat watchdog 依据最后心跳将停滞项转 `stalled`，重试沿用 `client_message_id` 与 execution idempotency key。

**Rationale**: 现有 Agent 曾因 worker 在 run 创建前异常而永久 `pending`。只加前端超时不能恢复事实状态，也无法保证重试不产生重复外部影响。

**Alternatives considered**:

- 只在前端增加倒计时：后端事实仍错误。
- 仅依赖 Celery 状态：违反数据库作为业务状态真相的宪法约束。

## R-007：实时 UI

**Decision**: 复用 `/events/jobs` SSE，增加 `conversation.message_created` 和 `conversation.turn_updated` 事件；断线继续使用 Last-Event-ID 重放与快照。对话页面按 message/turn/task 关联展示聊天、阶段、工具活动和确认卡片。

**Rationale**: 现有 SSE 已具备认证、重放和任务快照，无需第二条实时通道或 WebSocket。

**Alternatives considered**:

- 单独建立聊天 SSE/WebSocket：增加连接、重连与鉴权状态。
- 仅轮询：延迟高，且当前无限轮询问题已经存在。

## R-008：基线集成

**Decision**: 实施以 `006-agent-content-management@d70e39c` 的自助 Agent 为前置基线，先集成其 `0019_agent_runtime`、agent 模块、worker、SSE 和前端页面，再应用本特性迁移与增量代码。

**Rationale**: 当前 feature branch 从 master 创建，不含被本规格明确扩展的功能。重复实现会产生两套任务和确认语义。

**Alternatives considered**:

- 在 master 上另建聊天模块：与已部署 Agent 分叉。
- 把整个既有 Agent 重写进本特性：范围和回归风险过大。
