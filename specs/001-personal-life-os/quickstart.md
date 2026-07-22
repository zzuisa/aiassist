# Quickstart and Acceptance Runbook

> 当前仓库处于 Specify 设计阶段；以下命令是实现必须满足的运行契约。`tasks.md` 完成后，本文件应能在
> 一台全新 Linux 个人服务器上逐条执行。生产环境只发布 Nginx 的 80/443。

## 1. Prerequisites

- Docker Engine with Compose V2（实现时记录经过验证的最低版本）
- 4 CPU / 8 GiB RAM 起步；启用本地 faster-whisper 时建议 16 GiB RAM
- 20 GiB 系统空间 + 独立资产/备份空间
- SMTP relay（可选；不配置时站内提醒仍可用）
- 至少一个 LLM/语音 Provider 配置，或启用本地 Ollama/faster-whisper profile

## 2. Configure

```bash
cp .env.example .env
mkdir -p secrets data/assets backups
```

`.env` 只包含非秘密配置和 secret 文件路径。使用独立文件创建：

- `secrets/postgres_password`
- `secrets/jwt_signing_key`
- `secrets/smtp_password`（可选）
- `secrets/llm_provider_key`（可选）
- `secrets/s3_access_key` / `secrets/s3_secret_key`（仅 S3 profile）

必填非秘密配置：`APP_BASE_URL`、`APP_TIMEZONE`、`POSTGRES_DB`、`POSTGRES_USER`、
`STORAGE_PROVIDER=local`、`ASSET_ROOT=/data/assets`、上传限制和备份保留期。

生成签名密钥时不得把命令输出写入 shell history 或仓库。Secret 文件权限应为仅部署用户可读。

## 3. Validate and start infrastructure

```bash
docker compose config --quiet
docker compose pull
docker compose up -d postgres redis rabbitmq
docker compose ps
```

默认生产使用 `assets` named/bind volume。仅为 S3 adapter 兼容开发启动可选 profile：

```bash
docker compose --profile s3 up -d minio
```

MinIO 社区服务端已停止维护，不是默认公网生产建议；生产 S3 模式应指向部署者选择的受维护服务。

## 4. Migrate and create the first account

```bash
docker compose run --rm migrate
docker compose run --rm backend python -m app.cli create-admin --email owner@example.com
```

`create-admin` 从交互式 stdin 读取密码，使用 Argon2id 哈希，不接受命令行明文密码。重复 email 必须安全失败。

## 5. Start application processes

```bash
docker compose up -d frontend backend outbox-publisher worker-fast worker-heavy celery-beat nginx
docker compose ps
```

Expected readiness:

- `GET /health/live`：进程存活。
- `GET /health/ready`：数据库迁移和必需本地存储可用。
- `GET /health/dependencies`（需管理员）：RabbitMQ/Redis/邮件/AI 可显示 degraded，不暴露凭据。
- PostgreSQL、RabbitMQ、Redis 不发布宿主端口；RabbitMQ management 仅在显式 debug profile 中开放到 localhost。

## 6. Smoke test the user journeys

1. 登录并确认 access/refresh 是 Secure HttpOnly Cookie，URL 和 localStorage 无 token。
2. 停止 worker/AI，创建文字任务；刷新后内容仍存在。
3. 在周日历拖拽任务，制造固定事件冲突；AI/用户操作均不能静默移动固定事件。
4. 创建每日习惯，两次触发生成任务；数据库/页面只出现一个当天习惯任务。
5. 录制语音；上传后立即看到记录。处理完成前不出现正式提醒；确认卡提交后只创建一次。
6. 上传 JPEG；立即看到待处理收藏。检查展示派生图无 GPS/EXIF，原图保持私有。
7. 断开 SSE，等待 Job 完成，再重连；任务中心通过 replay/snapshot 达到最终状态。
8. 从收藏创建博客草稿；AI 改写只出现 revision diff，应用前正文不变。
9. 发布博客并匿名访问；取消发布后匿名访问返回 404。
10. 搜索任务、收藏和博客关键词；验证分组、高亮和其他账户隔离。

## 7. Failure-injection acceptance

### Broker outage

```bash
docker compose stop rabbitmq
# Create a task and upload a small image through the UI/API.
docker compose start rabbitmq
```

Expected: 基础任务/收藏已保存；outbox pending 年龄会上升；broker 恢复后 Publisher 发布，任务只执行一次。

### Worker crash after delivery

在测试 profile 中暂停或 kill worker-heavy 于缩略图处理中，再启动。Expected: 原图可访问；消息 redelivery；
派生资产 unique key 防重复；job 最终完成或以可重试错误失败。

### Redis outage

停止 Redis 后保持 SSE。Expected: job event 仍写 PostgreSQL；SSE 退化为轮询并最终更新；Redis 恢复后无需回填。

### Invalid LLM output

使用 fake provider 返回缺字段/额外字段/固定事件 move。Expected: Schema/业务规则拒绝，正式任务不变，job 显示安全错误。

## 8. Backup

```bash
docker compose run --rm backup
```

Backup output MUST contain:

- PostgreSQL custom-format dump
- asset copy/snapshot
- encrypted configuration/secrets archive or documented external secret backup reference
- manifest with app/database version, timestamp, object count and checksums

Redis、RabbitMQ 和 Celery state 不属于权威备份。备份目标必须位于另一主机/介质并加密。

## 9. Restore drill

在隔离的全新目录/主机：

1. 停止对外代理并创建空 PostgreSQL/asset volume。
2. `pg_restore` 数据库并恢复资产。
3. 注入 secrets，运行当前迁移。
4. 执行对象引用/哈希校验。
5. 将中断 `processing` job 置为可重试，启动 Outbox Publisher 重放 pending 事件。
6. 执行登录、文字保存、资产读取、SSE 和邮件 smoke test。
7. 记录实测 RPO/RTO；至少每季度演练一次。

## 10. Stop and update

```bash
docker compose down
```

不得使用 `-v`，除非明确要销毁数据库、资产和 broker 数据。升级前运行备份与 restore 验证；更新镜像 digest、
依赖 lockfile 和迁移后先在 staging profile 执行 smoke/failure tests，再切换生产。
