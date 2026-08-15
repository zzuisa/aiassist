# 修复复盘：ELK 日志占满根盘（2026-08-16）

- 分类：AI Assist 修复复盘
- 影响范围：AI Assist、Elasticsearch、Kibana、Filebeat 的单机运行环境

## 现象

根文件系统使用率达到 90%。主要占用来自旧 ELK 目录：Elasticsearch 数据约 4.9GB，日志目录约 12GB；其中日志目录包含 16 份历史 Java 堆转储。AI Assist 的应用日志仍写在根盘的 `/www/wwwlogs/aiassist`，持续增加根盘压力。

## 根因

ELK 的数据、日志和 AI Assist 文件日志未与 Docker 的大容量专用文件系统隔离。Elasticsearch 配置了 OOM 堆转储，历史转储没有放到容量充足的观测盘；同时未设置经审批的索引或诊断保留策略。

## 修改

- 将 ELK 的 `DATA_PATH` 与 `LOG_PATH` 切换到 `/mnt/docker-ext4/observability/elk`。
- 将 AI Assist Compose 与部署脚本的日志根目录切换到 `/mnt/docker-ext4/observability/aiassist/logs`。
- 为 Filebeat 增加该目录的只读挂载，并将 AI Assist 输入改为容器内的 `/var/log/aiassist`，避免跨挂载点跟随宿主机路径失败。
- 迁移 Elasticsearch 数据、常规日志和 16 份历史堆转储；堆转储保留在新盘的 `observability/elk/diagnostics/heapdumps`。
- 清理已校验的旧 ELK 数据与日志目录，并新增观测存储运维说明。

## 验证

1. Elasticsearch 从新盘挂载启动，认证健康检查通过；647 个主分片恢复，单节点集群为 yellow 仅因 6 个副本未分配。
2. Kibana 与 Filebeat 均恢复健康；`logs-aiassist-*` 与 `nginx-aiassist-*` 索引持续写入。
3. AI Assist 网关 `/health/ready` 返回 `ready`，后端、两个 worker 和 Nginx 均为 healthy，两个 worker ping 均返回 `pong`。
4. AI Assist 与 Nginx 容器的日志挂载已确认指向新盘。
5. 16 份堆转储的源/目标文件清单、大小和修改时间一致后才删除旧目录；根盘使用率从 90% 降至 76%。

## 日志检索方式

在 Kibana 中检索 `logs-aiassist-*` 和 `nginx-aiassist-*`；服务端可使用：

```bash
./deploy/scripts/deploy.sh logs backend | rg 'error|exception'
docker logs filebeat --tail 100
```

检索时不得输出认证 Cookie、令牌、密码或其他密钥。

## 遗留风险

- 单节点 Elasticsearch 的副本分片会保持未分配，集群状态为 yellow；这不影响主分片读写，但没有副本容灾能力。
- 尚未设置自动删除策略。索引保留周期和堆转储保留期限需经业务确认后再启用，避免误删审计或排障证据。
- Elasticsearch 冷启动会扫描大量历史索引，恢复时间受观测盘随机读性能影响。
