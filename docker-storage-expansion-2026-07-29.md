# Docker 存储空间耗尽：从 Elasticsearch 启动失败到 500 GB 扩容

2026 年 7 月 29 日，服务器上的 Elasticsearch 进入重启循环，启动日志反复出现：

```text
java.nio.file.FileSystemException: /tmp/elasticsearch-...: No space left on device
```

表面上看，这是 `/tmp` 空间不足；实际原因却是 Docker 独立存储文件系统已满。本文记录完整的诊断、风险判断和扩容过程。

## 现象与定位

主机磁盘当时的关键数据如下：

```text
/dev/sda6       123G   90G   27G   78%  /
/dev/sdb1        15T  2.5T   13T   18%  /mnt/sdc1
/dev/loop26      49G   47G      0  100% /mnt/docker-ext4
```

主机根目录和 `/tmp` 仍有空间，但 Elasticsearch 容器中的 `/tmp` 位于 Docker 的可写层。Docker 的 `data-root` 配置为：

```json
{
  "data-root": "/mnt/docker-ext4"
}
```

因此，真正耗尽的是 `/mnt/docker-ext4`，而不是主机 `/tmp`。

进一步检查后发现，Docker 数据其实早已放在外置大盘中，只是通过一个固定大小的 ext4 镜像承载：

```text
/dev/sdb1 (exFAT, 15 TB)
└── /mnt/sdc1/docker-data.img (ext4 镜像, 50 GB)
    └── /mnt/docker-ext4 (Docker data-root)
```

外层磁盘还有约 13 TB 可用空间，但内层镜像固定为 50 GB，所以 Docker 无法使用外层剩余容量。

## 为什么不把 Docker 目录直接放到 exFAT

Docker 的 `overlay2` 依赖 Linux 文件系统的权限、扩展属性和链接等语义。exFAT 不完整支持这些能力，直接将 Docker 数据目录放入 exFAT 普通目录并不可靠。

因此保留“exFAT 上的 ext4 镜像”结构，只扩大镜像和内部 ext4 文件系统。这既能继续使用大容量外置盘，也为 Docker 提供原生 Linux 文件系统语义。

## 安全取舍

外置盘还保存了约 2 TB 照片，因此本次操作明确限制影响范围：

- 不运行针对整个 `/dev/sdb1` 的 `fsck.exfat`。
- 不格式化、不重新分区外置盘。
- 不把 `overlay2` 直接迁移到 exFAT 目录。
- 不执行 `docker system prune --volumes`，避免误删持久卷。
- 只修改已确认的 `/mnt/sdc1/docker-data.img`。
- 扩容期间停止 Docker 和全部容器，避免并发写入。

## 实际扩容步骤

首先停止 Docker 服务和容器运行时，并安全卸载 Docker 文件系统及外置盘相关挂载：

```bash
systemctl stop docker.service docker.socket containerd.service
umount /mnt/docker-ext4 /appHome/data/immich /appHome/data/cms /storage /mnt/sdc1
```

随后按已有 `/etc/fstab` 配置重新挂载外置盘，并确认它处于读写状态：

```bash
mount /mnt/sdc1
findmnt /mnt/sdc1
```

只扩大 Docker 镜像文件，不修改同盘其他文件：

```bash
truncate -s 500G /mnt/sdc1/docker-data.img
mount /mnt/docker-ext4
resize2fs /dev/loop26
```

`resize2fs` 在线扩展已挂载的 ext4。由于底层是 USB 外置盘上的 exFAT 大文件，建立新块组和同步数据需要较长时间；此时不应强行终止进程。

## 恢复与验证

扩容完成后，恢复 `/etc/fstab` 中的绑定挂载，启动容器运行时和 Docker，并检查：

```bash
mount /appHome/data/immich
mount /appHome/data/cms
mount /storage
systemctl start containerd.service docker.socket docker.service

df -h /mnt/docker-ext4
docker info --format '{{.DockerRootDir}}'
docker ps -a
docker logs --tail 50 elasticsearch
```

验收重点是 Docker 根目录仍为 `/mnt/docker-ext4`、文件系统容量接近 500 GB、原有容器和卷仍存在，以及 Elasticsearch 不再出现 `No space left on device`。

本次操作的最终结果为：

```text
/dev/loop26     492G   37G  436G   8%  /mnt/docker-ext4
Docker Root Dir: /mnt/docker-ext4
Storage Driver: overlay2
```

`containerd`、Docker 和 Docker socket 均恢复为 `active`。aiassist 后端、两个 Worker、RabbitMQ、Redis、PostgreSQL、Nginx 和前端恢复健康；Elasticsearch 成功越过临时目录创建阶段并继续完成节点启动，最新日志中不再出现 `No space left on device`。

## 后续维护建议

这次故障不是 15 TB 外置盘耗尽，而是固定大小的 50 GB Docker 镜像耗尽。后续应同时监控宿主磁盘和 Docker 独立文件系统：

```bash
df -h / /mnt/sdc1 /mnt/docker-ext4
docker system df
```

清理时优先处理悬空镜像和无用构建缓存：

```bash
docker image prune
docker builder prune
```

应谨慎使用带 `--volumes` 的全局清理命令。项目已经为容器日志配置大小和文件数上限；此外可以为 `/mnt/docker-ext4` 增加 80% 和 90% 两级容量告警，避免数据库、队列和搜索服务再次同时受到影响。

## 结论

当容器报告 `/tmp` 无空间时，不能只检查主机 `/tmp`。容器的临时目录通常属于 Docker 可写层，必须同时确认 Docker `data-root` 所在文件系统。对于 exFAT 大盘，使用 ext4 镜像承载 Docker 是可行方案，但镜像容量需要单独规划和监控。
