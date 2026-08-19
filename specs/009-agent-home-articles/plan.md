# Implementation Plan: Agent 首屏与文章结果交互

**Branch**: `009-agent-home-articles` | **Date**: 2026-08-13 | **Spec**: [spec.md](./spec.md)

## Summary

将 Agent 页面入口从“恢复最近 active 会话”调整为“等待用户发送首条消息再创建会话”。当前页面只维护本次访问创建的会话；现有会话、持久化、所有权与重试接口不变。将文章型任务结果作为消息内容中的安全文章引用解析为可点击卡片，并复用既有文章详情路由。

## Technical Context

**Language/Version**: Python 3.12；TypeScript 5.7；Node 24  
**Primary Dependencies**: FastAPI、SQLAlchemy、Vue 3、Pinia、Vue Router、Vitest、Playwright  
**Storage**: 复用 PostgreSQL 会话、消息、任务与文章；不新增表或迁移。  
**Testing**: 前端组件与端到端测试；后端文章结果契约测试。  
**Target Platform**: Docker Compose 单机部署，桌面与移动端浏览器。  
**Performance Goals**: 首屏不因历史消息查询而阻塞；一篇有效结果可在一次点击内打开详情。  
**Constraints**: 不加载非当前页面会话；文章引用只使用所有者可见数据；不显示原始 JSON、内部 ID、端点或凭据。  

## Constitution Check

| Gate | Result | Notes |
|---|---|---|
| Durable Capture Before Intelligence | PASS | 首条消息仍按既有事务持久化。 |
| Human Authority | PASS | 不改变确认或写入流程。 |
| Operational Simplicity | PASS | 仅调整现有前端状态与消息呈现，无新服务。 |
| Validated AI | PASS | 仅消费既有安全任务结果。 |
| Reliable Async Work | PASS | 复用现有 turn/job 状态。 |
| Privacy and Least Privilege | PASS | 卡片链接使用既有已授权文章详情。 |
| Contract/Test First | PASS | 先增加结果/首屏回归测试。 |
| Observability | PASS | 不新增敏感日志；保留既有 trace 与 turn。 |

## Project Structure

```text
frontend/
├── src/modules/agent/AgentPage.vue
├── src/stores/agentConversations.ts
├── src/components/agent/ConversationPanel.vue
├── src/components/agent/ArticleResultCard.vue
└── tests/{component,e2e}/
backend/
└── tests/contract/test_agent_article_results.py
```

## Design

1. `loadHistory()` no longer calls `ensureConversation()` or fetches messages. It clears local state and leaves `conversationId` empty.
2. `sendMessage()` remains the sole path that creates a conversation; it keeps that ID for this mounted page.
3. Task results are represented through existing assistant message `content.task_id`; `AgentPage` loads the owned task and derives safe article records from its result summary.
4. `ArticleResultCard` renders title, optional category/tags and a semantic link to the existing private article route. Missing metadata does not prevent navigation.
5. A contract test confirms article result links resolve only to existing, owned article detail paths. Component/E2E tests confirm the empty landing state and card interaction.

## Post-design Constitution Check

PASS. No persistence model, authorization rule, provider boundary or deployment topology changes are required. No exception is recorded.

## Complexity Tracking

No constitution exceptions.
