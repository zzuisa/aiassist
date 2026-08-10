# 修复复盘：AI Assist 日志 message 补全、错误可见性与 Nginx 分流（2026-07-30）

## 现象

Kibana 的 logs-aiassist-* 文档没有 message 字段，日志正文只能从 event 查看。同时 AI Assist 自身的 Nginx access/error 文件没有独立采集，业务索引中还混有 Uvicorn access 行，难以区分访问日志和业务错误。

## 根因

1. Structlog 默认将日志名称和正文写入 event，原日志 formatter 没有复制到 ECS 常用的 message。
2. 已处理的 AppError、请求校验错误和 HTTPException 只返回 Problem Details，没有生成独立的业务错误事件。
3. AI Assist Nginx 日志位于 /www/wwwlogs/aiassist/nginx/，而通用 Filebeat input 排除了整个 /aiassist/ 路径。
4. backend.log 同时接收 uvicorn.access，造成 Nginx access 与应用访问日志重复。

## 修复

### 业务日志

- 所有 Structlog 和标准库日志同时保留 event 并生成 message。
- event 继续作为稳定的机器事件名，message 用于 Kibana 默认日志正文列。
- 4xx 业务/API 错误记录为 warning。
- 5xx 错误记录为 error。
- 未捕获异常记录 exception 堆栈、error_type、error_code、status_code、method、path 和 trace_id。
- backend.log 排除 uvicorn.access，避免和 Nginx 重复。

### Nginx 日志

新增两个独立 Filebeat input：

- aiassist-nginx-access-v1
- aiassist-nginx-error-v1

写入独立索引：

~~~text
nginx-aiassist-YYYY.MM.dd
~~~

Nginx access 格式调整为标准 combined 格式，可由现有 nginx-access ingest pipeline 提取：

- client_ip
- method
- url
- status
- bytes
- referer
- user_agent
- @timestamp

业务日志继续写入：

~~~text
logs-aiassist-YYYY.MM
~~~

### 历史数据

对现有 AI Assist 文档执行一次安全回填：

~~~text
event -> message
total: 450
updated: 450
version conflicts: 0
missing message with event: 0
~~~

## 现网验证

使用安全的不存在路径请求验证，trace_id：

~~~text
a24c26ddd31aa1c4feb67dc44194a8f1
~~~

业务索引只产生一条错误事件：

~~~json
{
  "message": "api_http_error",
  "event": "api_http_error",
  "level": "warning",
  "status_code": 404,
  "error_code": "not_found",
  "trace_id": "a24c26ddd31aa1c4feb67dc44194a8f1"
}
~~~

Nginx 索引只产生一条访问记录：

~~~json
{
  "log_category": "nginx",
  "url": "/api/v1/log-separation-check",
  "status": 404
}
~~~

backend.log 中同一 trace_id 记录数为 1，不再包含重复的 Uvicorn access 行。

当前索引：

~~~text
logs-aiassist-2026.07
nginx-aiassist-2026.07.30
~~~

两者均为 green。

## Kibana 检索建议

业务错误：

~~~text
level: "error"
level: "warning" and event: api_*
status_code >= 500
error_code: *
trace_id: "<trace id>"
~~~

Nginx 请求：

~~~text
app: "aiassist"
status >= 500
url: "/api/v1/*"
client_ip: *
~~~

定位一次请求时，先在 nginx-aiassist-* 中找到 URL、状态码和时间，再到 logs-aiassist-* 中通过页面响应的 X-Trace-Id 查询业务错误详情。

## 验证结论

- 新业务日志全部具有 message。
- 历史 event 文档已全部补齐 message。
- API 失败会生成独立结构化业务错误事件。
- 未捕获异常支持 exception 堆栈。
- Nginx 和业务日志使用不同索引。
- Uvicorn access 不再污染业务日志文件。
