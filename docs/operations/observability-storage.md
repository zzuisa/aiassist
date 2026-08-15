# Observability storage layout

AI Assist file logs and the ELK data/log paths live on the dedicated Docker
filesystem so that observability growth does not consume the host root volume.

| Component | Host path |
| --- | --- |
| AI Assist structured and gateway logs | `/mnt/docker-ext4/observability/aiassist/logs` |
| Elasticsearch data | `/mnt/docker-ext4/observability/elk/data/elasticsearch` |
| Elasticsearch diagnostics and logs | `/mnt/docker-ext4/observability/elk/logs/elasticsearch` |
| Kibana/Filebeat state and logs | `/mnt/docker-ext4/observability/elk/{data,logs}` |

Filebeat keeps reading the host-wide `/www/wwwlogs` mount for other services,
and reads AI Assist logs through its dedicated read-only mount at
`/var/log/aiassist`. This avoids following host symlinks across a container
mount boundary.

## Operations

Run the AI Assist deployment script after changing its Compose file. The ELK
stack is managed from `/www/dk_project/dk_app/elk` with `docker compose`.

Do not delete Elasticsearch indices or diagnostics merely to recover disk
space. Configure and approve an explicit index-retention policy first. The
Elasticsearch heap dumps currently retained under the observability log path
are historical OOM diagnostics and should be reviewed before removal.
