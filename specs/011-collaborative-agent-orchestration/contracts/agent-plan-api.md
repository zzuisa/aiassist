# Agent Plan API Contract

Base path: `/api/v1/agent`

## GET `/conversations/{conversation_id}/plans`

返回当前用户该会话最近计划，默认 20 个。每个计划包含完整的有界步骤视图，用于历史恢复。

## GET `/turns/{turn_id}/plan`

返回该 Turn 的计划；纯聊天或尚未建立计划时返回 404。

## GET `/plans/{plan_id}`

返回所有者的完整计划视图。

## POST `/plans/{plan_id}/retry`

请求体：

```json
{"mode":"failed_chain"}
```

仅允许 `failed` 或 `stalled` 计划。保留仍有效的成功步骤和产物，把失败/停滞步骤及受影响依赖步骤恢复为 pending，返回 202 和更新后的计划。

## Public plan shape

```json
{
  "schema_version": "agent-plan-view.v1",
  "plan_id": "uuid",
  "turn_id": "uuid-or-null",
  "task_id": "uuid",
  "user_message_id": "uuid-or-null",
  "objective": "查询并分析最近文章",
  "status": "running",
  "version": 4,
  "counts": {"total": 3, "completed": 1, "failed": 0, "skipped": 0},
  "elapsed_ms": 1250,
  "result_summary": null,
  "error": null,
  "steps": [
    {
      "step_id": "uuid",
      "step_key": "step_query",
      "position": 1,
      "title": "查询最近文章",
      "responsibility": "取得后续分析所需文章范围",
      "agent": {"key": "article-query-agent", "name": "文章查询 Agent"},
      "tool_name": "posts.list_recent",
      "operation_type": "query",
      "depends_on": [],
      "status": "success",
      "progress": null,
      "attempt_count": 1,
      "stage_label": "查询完成",
      "result_summary": "找到 5 篇文章",
      "error": null,
      "started_at": "date-time",
      "finished_at": "date-time",
      "duration_ms": 120
    }
  ],
  "created_at": "date-time",
  "finished_at": null
}
```

安全约束：响应不包含静态/动态工具参数、Prompt、Skill、推理、正文、原始工具结果、端点或凭据。

