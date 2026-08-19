# 快速部署前端探活误判复盘（2026-08-19）

## 现象

首次执行 `deploy.sh fast-up` 时，镜像构建、数据库迁移和应用容器重建均已完成，Docker 显示前端、后端、Worker 与 Nginx 全部健康，但脚本停留在应用探活阶段，未打印发布完成。

## 根因

脚本在前端容器内请求 `http://localhost/`。该 Alpine 容器将 `localhost` 优先解析为 IPv6 `::1`，而前端 Nginx 当前仅在 IPv4 监听，导致 `wget` 收到连接拒绝。Compose 自带的前端健康检查使用 `127.0.0.1`，因此容器实际健康，属于脚本探活误判。

## 修改

- 将快速发布和重启共用的前端探活地址改为 `http://127.0.0.1/`。
- 增加部署契约测试，固定前端探活必须使用容器 IPv4 回环地址。
- 保留后端、前端、两个 Worker 与 Nginx 网关逐项探活，避免为了速度省略上线验证。

## 验证

- `bash -n deploy/scripts/deploy.sh` 通过。
- Ruff 检查通过。
- 部署契约检查通过。
- 生产容器 `backend`、`frontend`、`worker-fast`、`worker-heavy`、`outbox-publisher`、`celery-beat` 和 `nginx` 均为 healthy。
- 容器内访问 `http://127.0.0.1/` 成功，生产网关 `/health/ready` 返回成功。

## 日志检索方式

```bash
./deploy/scripts/deploy.sh ps
./deploy/scripts/deploy.sh logs frontend
./deploy/scripts/deploy.sh logs nginx
```

可重点检索 `Connection refused`、`health`、`wget`、`ERROR` 和 `exception`。

## 遗留风险

- 当前快速发布仍会完整构建前端和后端；即使依赖层命中缓存，前端类型检查与生产打包仍可能需要约一分钟。
- `fast-up` 不等待 GitHub CI，适合已有运行环境的日常代码发布；首次部署、中间件或 Compose 基础设施变化仍应使用完整 `up`。
- 若未来前端镜像改为只监听 IPv6，需要同步调整 Compose 健康检查与部署探活策略。
