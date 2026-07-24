# Deployment secrets

Each file in this directory holds exactly one secret value with **no trailing
newline dependency** (the app strips surrounding whitespace). These files are
mounted into containers as Docker secrets / bind mounts and are **never**
committed. `.gitignore` excludes everything here except this README and
`.gitkeep`.

Set permissions to `0600`. Because Docker Compose file-backed secrets preserve
host ownership, production files must be owned by the backend runtime UID
`10001` so the non-root application process can read them:

```bash
sudo chown 10001 deploy/secrets/{postgres_password,jwt_signing_key,rabbitmq_password}
sudo chmod 0600 deploy/secrets/{postgres_password,jwt_signing_key,rabbitmq_password}
```

`deploy.sh up` applies this ownership automatically when run as root and fails
closed with the required command when an unprivileged deploy user owns the files.

## Required for production startup

| File | Purpose | How to generate |
|---|---|---|
| `postgres_password` | PostgreSQL role password | `openssl rand -base64 32` |
| `jwt_signing_key` | Access-token HMAC signing key | `openssl rand -base64 64` |
| `rabbitmq_password` | RabbitMQ user password | `openssl rand -base64 32` |

## Optional (feature is marked *degraded* when absent)

| File | Purpose |
|---|---|
| `smtp_password` | SMTP relay password for email reminders |
| `llm_provider_key` | API key for the configured LLM/speech provider |
| `s3_access_key` | S3 access key (only when `STORAGE_PROVIDER=s3`) |
| `s3_secret_key` | S3 secret key (only when `STORAGE_PROVIDER=s3`) |

## Creating a secret without leaking it to shell history

```bash
umask 077
printf '%s' "$(openssl rand -base64 32)" > deploy/secrets/postgres_password
```

Do not paste secret values into `.env`, `compose.yaml`, Nginx config, logs or
Git. Rotating a secret means replacing the file and restarting the dependent
services.
