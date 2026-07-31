# 修复复盘：任务取消冲突的可读日志与前端反馈（2026-07-30）

## 现象

用户对已经结束的任务 `b439d11a-2abe-44a6-935a-d6698537027c` 调用取消接口时，接口正确返回 HTTP 409 和 `job_finished`，但 Kibana 的 `message` 只有 `api_request_failed`，无法直接看出冲突原因。任务中心还会给失败任务展示“取消”按钮，导致同一任务在数秒内发出多次无效取消请求。

## 根因

1. 通用 `AppError` 日志只将稳定事件名写入 `message`，没有写入安全的业务 `detail`。
2. 任务取消服务将 `completed`、`failed`、`cancelled` 三种终态统一为 `Job already finished`，未向客户端提供当前状态。
3. 任务中心把失败任务视为可取消对象；失败其实是终态，取消不能改变其状态。
4. 任务详情页没有针对 `job_finished` 做本地化且可恢复的提示。

## 修改

- 对已处理 API 错误，保留稳定 `event`，并把业务原因写入 `message`。
- 对终态取消冲突新增结构化字段：`operation`、`outcome`、`job_id`、`job_status`、`error_code` 和 `trace_id`；事件名为 `job_cancel_rejected`。
- Problem Details 返回 `job_status`，前端无需解析英文 `detail` 即可作出正确提示。
- 已取消任务的重复取消改为幂等成功（202），避免双击或重试造成假错误。
- 移除任务中心中失败任务的“取消”按钮；保留可重试任务的“重试”。
- 任务详情页对 `job_finished` 显示中文状态提示并刷新任务；其他失败显示明确的重试提示。

## 现网验证

已在现网对该任务执行一次只读的终态取消验证，返回：

~~~json
{
  "status": 409,
  "code": "job_finished",
  "detail": "Job has already failed",
  "job_status": "failed",
  "trace_id": "d74debf71a8d4943113a45ee108c3326"
}
~~~

对应业务日志：

~~~json
{
  "event": "job_cancel_rejected",
  "message": "Job has already failed",
  "level": "warning",
  "status_code": 409,
  "error_code": "job_finished",
  "operation": "job.cancel",
  "outcome": "rejected",
  "job_id": "b439d11a-2abe-44a6-935a-d6698537027c",
  "job_status": "failed",
  "trace_id": "d74debf71a8d4943113a45ee108c3326"
}
~~~

前端定向组件测试通过（20 项），生产构建通过。服务已健康重建。

## Kibana 检索

~~~text
event: "job_cancel_rejected"
error_code: "job_finished"
operation: "job.cancel"
job_id: "b439d11a-2abe-44a6-935a-d6698537027c"
trace_id: "d74debf71a8d4943113a45ee108c3326"
~~~

`logs-aiassist-*` 中，`message` 现在可直接作为 Discover 的默认可读正文；`event` 和 `error_code` 继续用于聚合、告警和仪表盘。

## 遗留风险

- 其他业务冲突仍沿用通用 `api_request_failed` 事件；后续应按高频业务动作逐步补充领域事件和安全上下文。
- 前端通用错误映射尚未覆盖全部错误码；本次优先覆盖任务取消这一实际高频路径。
