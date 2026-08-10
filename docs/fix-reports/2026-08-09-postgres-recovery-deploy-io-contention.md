# 修复复盘：Postgres 崩溃恢复与部署 I/O 争用（2026-08-09）

- 分类：AI Assist 修复复盘
- 可见性：AI Assist 内部草稿

## 现象

阶段部署构建前端镜像期间，生产环境的 `/health/ready` 开始返回
`500 Internal Server Error`。Postgres、backend 和 nginx 先后被 Docker
健康检查标记为 `unhealthy`，后端日志显示数据库拒绝连接并处于恢复模式。

旧版前端页面仍由已有容器提供，但所有依赖数据库的接口在恢复期间不可用。

## 根因

Postgres 日志记录到一个未跟踪子进程以退出码 `2` 结束，主进程随后按保护机制
终止其他服务进程并重新初始化。现有日志没有保留该子进程异常退出的更具体原因，
因此不能把触发源进一步确定为某个请求或作业。

重新初始化触发了崩溃恢复。与此同时，本次前端 `package.json` 变化使 Docker 中的
`npm ci` 层失效，宿主机正在写入约 786 MB 的依赖层。数据库恢复所需的全目录
`fsync` 与镜像构建争用同一块磁盘，最终该步骤耗时约 945 秒，扩大了不可用窗口。

## 修改

- 暂停部署续跑，避免在数据库恢复期间切换或重启任何生产容器。
- 保留现有 Postgres 恢复进程，不执行强制重启、数据文件修改或 WAL 干预。
- 等待自动恢复、WAL redo 和 end-of-recovery checkpoint 全部完成。
- 数据库恢复后复用 BuildKit 已保留的 `npm ci` 缓存，单独完成前端镜像构建。
- 从发布脚本的安全中断点续跑基础设施检查、Alembic 迁移、前端容器切换、
  nginx 重解析以及 fast/heavy worker 检查。

## 验证

1. Postgres 于 `2026-08-09 13:50:42 UTC` 完成 WAL redo 和恢复检查点，并记录
   `database system is ready to accept connections`。
2. `GET /health/ready` 恢复为 `200` 和 `{"status":"ready"}`。
3. Postgres、backend、frontend、nginx、Redis、RabbitMQ、outbox publisher、
   celery beat 及两个 worker 均为 `healthy`。
4. Alembic 成功执行到 head；fast 与 heavy worker 均返回 `pong`。
5. 未登录访问 `GET /api/v1/agent/tasks` 返回预期的 `401`。
6. 版本 `2026.08.09.131751` 的 CI 全绿；隔离 E2E 已通过登录、CSRF、只读
   Agent 任务、SSE 状态和终态结果的一键验证。

## 日志检索方式

以下命令只检索运行状态和数据库恢复事件，不输出密码、令牌、Cookie 或请求体：

```bash
docker logs --since 2026-08-09T13:30:00Z aiassist-postgres-1 2>&1 \
  | rg 'untracked child|reinitializing|automatic recovery|redo|checkpoint|ready to accept'

docker inspect aiassist-postgres-1 aiassist-backend-1 aiassist-nginx-1 \
  --format '{{.Name}} {{.State.Health.Status}}'

curl --fail --silent --show-error https://llm.roguelife.de/health/ready
```

## 遗留风险

- Postgres 子进程退出码 `2` 的最初触发原因未被当前日志捕获；若再次发生，需要在
  同一时间窗采集宿主机内核、Docker daemon 和 Postgres 完整日志后再归因。
- 应用镜像构建和生产数据库仍共享单机磁盘，大依赖层失效时可能再次放大恢复或
  checkpoint 延迟。后续应评估远端构建/镜像仓库，或为构建与数据库提供独立 I/O。
- 当前健康探针在恢复期间会产生大量拒绝连接日志；可评估降低恢复态探针频率，
  但不得以放宽就绪语义掩盖数据库不可用。
