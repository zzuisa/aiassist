# 修复复盘：URL 博客导入可靠投递与 ELK 日志闭环（2026-07-30）

## 摘要

URL 导入 https://javaguide.cn/java/basis/java-basic-questions-01.html 曾长时间停留在待处理状态，页面只显示“处理失败”，而 worker 文件日志为空，无法直接定位根因。

本次修复完成了 URL 导入任务的可靠投递、状态闭环、结构化文件日志和 ELK 采集，并额外修复了排查期间发现的 Kibana 健康检查与 CMS Nginx 日志权限问题。

## 用户影响

- URL 导入事务已经写入 Post、PostSource 和 AsyncJob，但异步解析任务可能没有被 worker 正确执行。
- 失败详情只存在于 outbox publisher 日志和数据库 last_error，worker 日志缺少有效记录。
- Elasticsearch 因 JVM 堆过小反复 OOM 重启，Filebeat 队列积压，Kibana 不稳定。
- CMS Nginx 无法写入动态 $host access log，Kibana 中持续出现 Permission denied。

## 根因

### 1. Outbox 使用了不兼容的 Kombu 参数

现网 Kombu 版本不接受：

~~~text
Producer(..., confirm_publish=True)
~~~

对应 outbox 事件重试 10 次后进入 failed，核心错误为：

~~~text
Producer.__init__() got an unexpected keyword argument 'confirm_publish'
~~~

Publisher confirm 应配置在 Connection 的 transport options，而不是 Producer 构造参数。

### 2. 原始 outbox JSON 不是 Celery task 协议

即使修正 confirm 参数，把普通事件 JSON 直接投递到 Celery queue 也不会变成 Celery task。Worker 会将其识别为 unknown message 并丢弃。

### 3. 事务内直接调用 .delay() 存在提交竞态

旧代码在数据库事务提交前直接投递任务。Worker 可能先于事务提交查询 PostSource，得到不存在后直接跳过，导致 source/job 永久停留在 pending。

### 4. URL 解析任务路由和日志级别不正确

- blog.* 通配路由把 URL 抓取送到 heavy/llm worker，而不是 fast/search worker。
- Worker 未启用 info 日志。
- Uvicorn/Celery 使用不传播到 root logger 的独立 logger，导致配置了文件路径但 worker 文件仍为空。

### 5. ELK 资源与路径配置问题

- Elasticsearch JVM 堆仅 512MB，历史上累计发生 322 次容器重启。
- Filebeat 把 AI Assist JSON 日志当普通多行文本处理，无法稳定提取 service、trace_id、source_id、job_id 等字段。
- Kibana 配置了 /kibana basePath，但健康检查访问 /api/status，导致容器永久 unhealthy。
- Filebeat 配置曾直接保存 Elasticsearch 管理员凭据。

### 6. CMS Nginx UID 不匹配

宿主 CMS 日志目录/文件属于 UID/GID 1001:1002 且权限为 0700，容器内 Nginx worker 使用 1000:1000，因此无法进入目录或写入动态 access log。

## 修复内容

### 应用任务链路

- URL capture、AI generate、AI optimize 统一只写 transactional outbox，不再在事务内直接 .delay()。
- Outbox publisher 将已知 blog command 转换成正式 Celery task protocol，并使用稳定的 outbox event ID 作为 task ID。
- 修正 Kombu publisher confirm 配置。
- 将 app.workers.tasks.blog.extract 精确路由到 search queue。
- Worker 启用 info 级别日志。
- URL 抓取任务补齐 processing/completed/failed 状态流转和幂等恢复。

### 可观测性

- backend、Uvicorn、Celery、outbox publisher 统一输出单行 JSON。
- 日志包含 service、level、logger、trace_id，抓取任务额外包含 source_id、post_id、job_id、耗时、HTTP 状态和提取字符数。
- 文件日志继续落在宿主 /www/wwwlogs/aiassist/，10MB 轮转并保留 5 份。

关键文件：

~~~text
/www/wwwlogs/aiassist/backend.log
/www/wwwlogs/aiassist/outbox-publisher.log
/www/wwwlogs/aiassist/worker-fast.log
/www/wwwlogs/aiassist/worker-heavy.log
/www/wwwlogs/aiassist/celery-beat.log
~~~

### ELK

- 新增 Filebeat aiassist-json-v1 ndjson input。
- 从普通 business input 排除 /aiassist/，避免重复采集。
- 新增月度索引 logs-aiassist-YYYY.MM，单主分片、零副本。
- 新增 logs-aiassist-* index template 和 Kibana data view。
- Elasticsearch JVM 堆从 512MB 调整为 2GB。
- 修正 Kibana basePath 健康检查。
- Filebeat 改为通过环境变量读取 Elasticsearch 凭据。

### CMS 日志权限

- 为容器 Nginx UID 1000 添加定向读写/目录执行 ACL。
- 为 CMS 日志目录设置默认 ACL，使后续新建日志继承权限。
- 未将目录开放为全局 0777。

## 验证结果

### 自动化测试

定向测试共 60 项：

~~~text
60 passed
~~~

覆盖 outbox、URL 抓取失败矩阵、博客 API contract、taxonomy API 和结构化日志。

### 现网 URL 导入

通过现网 API 再次导入同一 JavaGuide URL：

~~~text
HTTP:           202
source_id:      fe68db2d-447b-4096-9f88-0b698b3c13d5
job_id:         3b4547dd-555f-49b6-95a9-262cd3d03b2a
source status:  completed
job status:     completed
title:          Java基础常见面试题总结(上)
text chars:     28543
markdown chars: 32985
duration:       4832 ms
~~~

### ELK

- Elasticsearch：healthy，重建后 RestartCount=0
- Kibana：healthy
- Filebeat：running
- logs-aiassist-2026.07：green，1 primary / 0 replica
- 使用 source_id 可查询到 blog_extract_started 和 blog_extract_finished

### CMS

本机请求验证：

~~~text
z_movie log: 0 bytes -> 2325 bytes
Permission denied count: 53513 -> 53513
~~~

错误计数不再增长，Nginx worker 已恢复写日志。

## 日志检索

Kibana 选择 data view：

~~~text
logs-aiassist-*
~~~

常用 KQL：

~~~text
source_id: "fe68db2d-447b-4096-9f88-0b698b3c13d5"
job_id: "3b4547dd-555f-49b6-95a9-262cd3d03b2a"
service: "worker-fast" and event: "blog_extract_finished"
level: "error"
trace_id: "<页面或接口返回的 trace id>"
~~~

本机快速检查：

~~~bash
rg 'SOURCE_ID|JOB_ID|TRACE_ID' /www/wwwlogs/aiassist/*.log
~~~

## 遗留风险与建议

- 整体 Elasticsearch 集群仍为 yellow，原因是单节点环境中 6 个历史副本分片无法分配；当前主分片均可用，不影响读写。后续可逐一确认这些历史索引并将副本数调整为 0。
- 旧 Filebeat 配置曾保存管理员凭据。配置已不再硬编码，但应安排一次凭据轮换，并同步 Kibana/Filebeat/初始化脚本。
- 通用领域事件仍使用原始 outbox envelope；后续应为非 Celery 事件配置专用消费者，避免由 Celery queue 接收 unknown message。
- CMS ACL 已覆盖当前与默认新建权限。下一次午夜轮转后应复查；若外部脚本强制 chmod 0700，需同步修改该轮转任务。
