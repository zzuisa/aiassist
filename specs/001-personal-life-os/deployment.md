# AI Assist 部署说明

**文档状态**：部署设计与执行约定  
**目标域名**：`https://llm.roguelife.de/`  
**目标主机**：当前承载 `llm.roguelife.de` 的 Linux 服务器  
**项目目录**：`/opt/aiassist`  
**部署方式**：Docker Compose V2  
**前端入口**：域名根路径 `/`，不使用 `/aiassist` 等子路径

> 2026-07-23 实机核验：目标主机由 BaoTa Nginx
> `/www/server/nginx/sbin/nginx` 承载 80/443，实际 vhost 是
> `/www/server/panel/vhost/nginx/llm.roguelife.de.conf`。`/etc/nginx` 的 systemd
> 服务处于停用状态，不是生产流量入口。

## 1. 部署拓扑

```text
Internet
   |
   v
llm.roguelife.de:443
   |
   v
宿主机 Nginx（保留现有证书与 TLS 配置）
   |
   | proxy_pass http://127.0.0.1:18080
   v
Compose nginx/gateway
   |-- /                  -> frontend
   |-- /api/v1/*          -> backend:8000
   |-- /api/v1/events/jobs -> backend:8000 SSE
   `-- 受保护资产          -> backend 鉴权 + internal asset location

Compose 内网：
backend / outbox-publisher / worker-fast / worker-heavy / celery-beat
PostgreSQL / Redis / RabbitMQ / 本地私有资产卷
```

只有宿主 Nginx 的 80/443 对公网开放。Compose 网关只绑定 `127.0.0.1:18080`；PostgreSQL、Redis、
RabbitMQ、后台 Worker 和管理端口均不得发布到公网。

## 2. 目标服务器目录

```text
/opt/aiassist/
├── compose.yaml
├── .env
├── deploy/
│   ├── nginx/
│   ├── scripts/
│   └── secrets/
├── data/
│   ├── assets/
│   └── backups/
└── logs/
```

建议所有者为专用部署用户 `aiassist`，容器使用非 root 用户。Secret 文件权限使用 `0600`，资产与备份
目录不得位于宿主 Nginx 的公开 Web Root 内。

## 3. Nginx 修改前备份

当前生产配置路径为：

```text
/www/server/panel/vhost/nginx/llm.roguelife.de.conf
```

先用实际 BaoTa 二进制验证当前配置：

```bash
NGINX_BIN=/www/server/nginx/sbin/nginx
NGINX_MAIN=/www/server/nginx/conf/nginx.conf
NGINX_CONF=/www/server/panel/vhost/nginx/llm.roguelife.de.conf
sudo "$NGINX_BIN" -t -c "$NGINX_MAIN"
```

验证文件存在且当前配置有效后，必须先创建带时间戳的原样备份：

```bash
BACKUP_CONF="${NGINX_CONF}.bak.$(date +%Y%m%d-%H%M%S)"
sudo cp --preserve=mode,ownership,timestamps "$NGINX_CONF" "$BACKUP_CONF"
sudo test -s "$BACKUP_CONF"
echo "备份完成：$BACKUP_CONF"
```

不要用未验证的变量、通配符或覆盖命令删除历史备份。

## 4. Nginx 配置修改

生产模板已保存为
`deploy/nginx/host/baota-llm.roguelife.de.conf`。安装时保留 BaoTa 的证书路径、ACME include、
日志路径和面板标记，代理目标统一为 `127.0.0.1:18080`。

将原来的静态文根和 index 指令注释，例如：

```nginx
# 原站点文根，AI Assist 启用后不再直接使用
# root /var/www/llm.roguelife.de;
# index index.html;
```

前端直接挂载域名根路径 `/`。在对应的 HTTPS `server` 块中加入或合并以下配置：

```nginx
# AI Assist 上传上限；应用层仍会再次校验类型、大小和内容
client_max_body_size 60m;

# 后台任务状态流必须关闭代理缓冲
location = /api/v1/events/jobs {
    proxy_pass http://127.0.0.1:18080;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 1h;
    proxy_send_timeout 1h;
    add_header X-Accel-Buffering no;
}

# API、前端和受保护资源统一由 Compose 网关处理。
# proxy_pass 不带尾部路径，保留原始 URI。
location / {
    proxy_pass http://127.0.0.1:18080;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_connect_timeout 10s;
    proxy_read_timeout 120s;
    proxy_send_timeout 120s;
}
```

Vue/Vite 必须使用根路径：

```text
VITE_BASE_URL=/
APP_BASE_URL=https://llm.roguelife.de
```

Vue Router 使用 HTML5 history 时，`index.html` 回退由 Compose 内的 frontend/gateway Nginx 处理，宿主
Nginx 只负责 TLS 与反向代理。

## 5. 检查并重载 Nginx

修改后先检查配置，检查成功才重载：

```bash
sudo /www/server/nginx/sbin/nginx -t -c /www/server/nginx/conf/nginx.conf
sudo /www/server/nginx/sbin/nginx -s reload -c /www/server/nginx/conf/nginx.conf
```

不要使用已停用的 `systemctl reload nginx` 或 `/usr/sbin/nginx -s reload`。只有 BaoTa 配置检查成功
时才向 `/www/server/nginx/logs/nginx.pid` 指向的实际 master reload。

确认 reload 后：

```bash
curl -I https://llm.roguelife.de/
curl -fsS https://llm.roguelife.de/health/live
curl -fsS https://llm.roguelife.de/health/ready
```

### 回滚

如果新站点返回异常，使用本次输出的明确备份文件路径恢复：

```bash
sudo cp --preserve=mode,ownership,timestamps "$BACKUP_CONF" "$NGINX_CONF"
sudo "$NGINX_BIN" -t -c "$NGINX_MAIN"
sudo "$NGINX_BIN" -s reload -c "$NGINX_MAIN"
```

回滚只恢复 Nginx 配置，不删除数据库、资产卷或 Compose 容器。

## 6. Docker Compose 服务清单

| 服务 | 数量 | 网络/端口 | 持久化 | 说明 |
|---|---:|---|---|---|
| `frontend` | 1 | 内网 `80` | 无 | Vue 构建产物和 SPA fallback |
| `backend` | 1 | 内网 `8000` | 无 | REST、SSE、资产鉴权、健康检查 |
| `outbox-publisher` | 1 | 仅内网 | 无 | 从 PostgreSQL 发布已提交事件到 RabbitMQ |
| `worker-fast` | 1 | 仅内网 | 无 | critical、notification、schedule、search |
| `worker-heavy` | 1 | 仅内网 | 资产卷 | voice、image、llm、maintenance |
| `celery-beat` | 1 | 仅内网 | 小型 schedule volume | 到期提醒、习惯、补偿任务触发 |
| `postgres` | 1 | 内网 `5432` | `postgres-data` | 业务数据、Outbox、Job、全文搜索 |
| `redis` | 1 | 内网 `6379` | 可选 `redis-data` | 缓存、锁和 SSE 唤醒；不是业务真相 |
| `rabbitmq` | 1 | 内网 `5672` | `rabbitmq-data` | quorum queues、DLQ、消息确认 |
| `nginx` | 1 | `127.0.0.1:18080 -> 80` | 无 | Compose 内部网关 |
| `migrate` | 按需 | 仅内网 | 无 | 一次性 Alembic migration job |
| `backup` | 按需 | 仅内网 | assets/backups | PostgreSQL dump、资产和 manifest |
| `minio` | 可选 | 仅 `s3` profile | `minio-data` | 只做 S3 兼容调试，不是默认生产存储 |

本地私有资产默认使用 `/opt/aiassist/data/assets` bind mount，同时挂载给 backend、worker-heavy 和 Compose
Nginx。Compose Nginx 对资产目录使用 `internal`，浏览器必须先经过 backend 所有权检查。

## 7. 固定版本清单

以下是 2026-07-22 的部署基线。镜像落地时必须进一步固定到 SHA-256 digest，禁止使用 `latest`。

| 组件 | 版本基线 | 镜像/来源 | 备注 |
|---|---|---|---|
| PostgreSQL | `18.4` | `postgres:18.4` | 当前稳定 18.x 修复版本 |
| RabbitMQ | `4.3.2` | `rabbitmq:4.3.2-management` | management 只允许内网/调试 profile |
| Redis Open Source | `8.8.0` | `redis:8.8.0` | 仅临时状态与锁；可关闭持久化或使用 AOF |
| Nginx | `1.30.4` stable | `nginx:1.30.4-alpine` | Compose 网关；宿主版本单独核验 |
| Python | `3.12.x` | `python:3.12-slim` | backend/worker/outbox 基础镜像 |
| Celery | `5.6.x` | backend Python lockfile | 与 RabbitMQ 4.3 做真实 worker smoke test |
| Node.js | `24.x LTS` | `node:24-alpine` | 仅前端构建阶段 |
| Docker Compose | V2 | Docker CLI plugin | 不支持旧 `docker-compose` V1 |
| MinIO | 不设生产版本 | 可选 `s3` profile | 社区服务端停止维护，默认使用本地存储 |

版本升级规则：

1. Patch/安全版本先在 staging Compose profile 运行迁移、契约、消息、上传和恢复测试。
2. PostgreSQL/RabbitMQ/Redis major 升级前必须完成备份和隔离恢复演练。
3. RabbitMQ 4.3.2 是本部署文件的新基线；实现时必须验证 Celery quorum queues、publisher confirm、DLQ 和
   redelivery，验证失败则在受支持版本中固定已通过组合，不允许静默降级可靠性。
   Celery 5.6 的 pidbox 控制/心跳队列仍使用 RabbitMQ 已弃用的 transient non-exclusive
   队列，`deploy/rabbitmq/rabbitmq.conf` 显式放行该兼容项；业务命令队列仍为 durable quorum
   queues。Celery 移除该依赖后应删除兼容项。
4. 每次镜像 digest 更新都通过 Git 提交审查，不允许服务器自行漂移。

## 8. 必需配置与 Secrets

### 非秘密环境变量

```text
APP_ENV=production
APP_BASE_URL=https://llm.roguelife.de
APP_TIMEZONE=Europe/Berlin
VITE_BASE_URL=/
POSTGRES_DB=aiassist
POSTGRES_USER=aiassist
STORAGE_PROVIDER=local
ASSET_ROOT=/data/assets
UPLOAD_IMAGE_MAX_BYTES=26214400
UPLOAD_AUDIO_MAX_BYTES=52428800
```

### Secret 文件

```text
deploy/secrets/postgres_password
deploy/secrets/jwt_signing_key
deploy/secrets/rabbitmq_password
deploy/secrets/smtp_password
deploy/secrets/llm_provider_key
```

SMTP/LLM 未配置时，系统允许基础数据保存并将相应依赖标为 degraded。JWT、数据库和 RabbitMQ secret 为
生产启动必需项。任何 secret 都不得写入 `.env`、Compose YAML、Git、Nginx 配置或日志。

## 9. 一键部署约定

最终实现必须提供以下单一入口：

```bash
cd /opt/aiassist
./deploy/scripts/deploy.sh up
```

`deploy.sh up` 必须按顺序执行：

1. 检查 Docker Compose V2、磁盘、目录权限、必需变量和 secret 文件。
2. 运行 `docker compose config --quiet`。
3. 拉取按版本和 digest 固定的中间件镜像，构建 frontend/backend 镜像。
4. 启动 PostgreSQL、Redis、RabbitMQ 并等待真实 healthcheck。
5. 运行一次性 `migrate` 服务；迁移失败立即停止，不启动新应用容器。
6. 启动 frontend、backend、outbox-publisher、worker-fast、worker-heavy、celery-beat 和 Compose nginx。
7. 验证 `/health/live`、`/health/ready`、数据库 migration head、Outbox Publisher heartbeat 和 Worker heartbeat。
8. 输出域名、服务状态、镜像版本/digest、volume 和备份路径；不得输出 secret。

手工等价命令仅用于排障：

```bash
docker compose config --quiet
docker compose pull
docker compose build frontend backend
docker compose up -d postgres redis rabbitmq
docker compose run --rm migrate
docker compose up -d frontend backend outbox-publisher worker-fast worker-heavy celery-beat nginx
docker compose ps
```

一键停止应用但保留数据：

```bash
./deploy/scripts/deploy.sh down
```

`down` 不得使用 `docker compose down -v`。删除 volume 必须是独立、显式、带二次确认的管理操作。

## 10. 首次部署步骤

1. 在服务器创建部署用户和 `/opt/aiassist`，确认 DNS `llm.roguelife.de` 指向该主机。
2. 克隆远程仓库并检出目标 release tag 或部署分支，不直接部署未提交工作区。
3. 创建 `.env`、secret 文件、assets/backups 目录和权限。
4. 执行 `./deploy/scripts/deploy.sh up`。
5. 交互式创建首个管理员，不在命令行参数中传明文密码。
6. 按第 3–5 节备份并修改宿主 Nginx，运行 `nginx -t` 和 `nginx -s reload`。
7. 运行登录、任务保存、SSE、上传、提醒和备份 smoke test。
8. 创建不可变 release tag 并记录部署的 commit、镜像 digest 和数据库 migration head。

## 11. 每个 Phase 的 Git 提交与推送规则

每完成 `tasks.md` 中一个 Phase，必须在进入下一 Phase 前完成测试、提交并推送。禁止把多个已完成 Phase
长期堆积在未推送的工作区。

```bash
git status --short
git diff --check

# 运行该 Phase 定义的 lint、类型、单元、契约、集成或 E2E 测试

git add --all
git commit -m "feat(phase-N): <本阶段可独立验收的结果>"
git push origin HEAD
```

首次推送当前功能分支时设置上游：

```bash
git push -u origin 001-personal-life-os
```

提交规则：

- 每个 Phase 至少一个提交；同一 Phase 可以有多个小提交，但最终 checkpoint 必须有明确提交。
- 只有 Phase 的独立验收测试通过才能 push；失败测试不得用跳过标记隐藏。
- 禁止 force push 已供部署或评审使用的分支。
- migration、OpenAPI/AsyncAPI/LLM Schema、Compose 和 Nginx 变更必须与实现一起提交。
- push 失败时停止进入下一 Phase，保留本地 commit，修复远程/认证问题后重试。
- commit message 示例：`feat(phase-4): add reliable voice capture confirmation flow`。

## 12. 发布与回滚

### 发布前检查

- 工作树干净，HEAD 已推送，部署 commit 可从远程读取。
- Compose 配置、镜像 digest 和所有 healthcheck 通过。
- Alembic migration 已在备份副本上验证。
- 数据库与资产备份完成并校验 manifest。
- `nginx -t` 通过；宿主配置备份文件路径已记录。
- 浏览器验证 `/` 前端、登录、任务保存、SSE 和受保护资产。

### 应用回滚

1. 切回上一个已验证 release tag/commit。
2. 使用该版本锁定的镜像 digest 重新执行 `deploy.sh up`。
3. 只有迁移文档明确支持 downgrade 才执行数据库 downgrade；否则恢复备份或前向修复。
4. 验证 health、登录、数据读取和 Outbox backlog。

### Nginx 回滚

使用第 5 节的明确 `$BACKUP_CONF` 恢复，随后必须执行：

```bash
sudo nginx -t
sudo nginx -s reload
```

## 13. 部署完成验收

- `https://llm.roguelife.de/` 返回前端，刷新任意 Vue route 不返回 404。
- `/api/v1` 与 SSE 同源，Cookie 不进入 URL/localStorage。
- SSE 在至少 60 秒连接内不中断，宿主和 Compose 两层代理均不缓冲。
- 基础任务在 AI、Redis或 RabbitMQ 降级时仍可保存，Outbox 在恢复后补发。
- 图片原图进入私有资产卷，浏览器只获取授权派生资源，不看到服务器真实路径。
- PostgreSQL、Redis、RabbitMQ、management、backend 和 Worker 端口均无法从公网直接访问。
- critical reminder 在 heavy worker 满载时仍按独立队列处理。
- `docker compose ps` 全部必需服务 healthy，migration 为当前 head。
- 已完成首次备份，并能在隔离目录验证数据库 dump 与资产 manifest。
- 本次 Phase 的 Git commit 已推送到远程分支。
