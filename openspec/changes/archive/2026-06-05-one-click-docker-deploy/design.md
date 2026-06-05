## Context

Paper Agent now has a useful public Web UI and subscription flow, but deployment is still a local/manual process:

- Python environment must be created manually.
- `config.yaml` and environment variables must be prepared manually.
- Web UI and daemon need separate long-running processes.
- SQLite data must be kept outside ephemeral runtime directories.
- SMTP and LLM secrets must not be baked into images or committed to git.

The first supported production-ish target will be a Linux VPS running Docker Compose.

## Goals / Non-Goals

**Goals:**
- Provide a repeatable Docker image for Paper Agent.
- Provide Docker Compose orchestration for both `web` and `daemon` services.
- Persist SQLite database and logs on the host via mounted volumes.
- Make deployment configurable via `.env` without committing secrets.
- Provide `paper-agent doctor` to validate deployment readiness.
- Provide basic backup/restore scripts for SQLite database files.
- Document the full VPS deployment flow.

**Non-Goals:**
- Do not implement managed cloud-specific deployment (Render/Fly/Railway) in this change.
- Do not implement HTTPS/certificate automation directly; document reverse proxy options instead.
- Do not replace SQLite with Postgres.
- Do not add user authentication or admin dashboard.

## Decisions

### 1. Use Docker Compose with two app services

Compose will define:

- `web`: runs `paper-agent web -c /app/config.yaml --host 0.0.0.0 --port 8000`
- `daemon`: runs `paper-agent daemon -c /app/config.yaml`

Both services use the same image and share the same mounted data/config/log directories.

Rationale: Web serving and scheduled pipeline execution have different lifecycles and logs; separating them avoids a process supervisor inside the container.

### 2. Use host-mounted volumes for persistence

Recommended layout:

```text
./deploy/config/config.yaml
./deploy/data/paper_agent.db
./deploy/logs/
./deploy/backups/
```

Compose maps these into `/app/config.yaml`, `/app/data`, and `/app/logs`.

Rationale: SQLite must persist across container rebuilds and be easy to back up.

### 3. Keep secrets in `.env`, not the image

`.env.example` will document required variables:

- LLM API key/base URL if used
- SMTP credentials
- app port/timezone

`config.yaml` can reference `${ENV_VAR}` placeholders; compose injects `.env` into containers.

Rationale: secrets should never be baked into Docker layers or committed.

### 4. Doctor command checks deployment readiness

`paper-agent doctor -c config.yaml` should perform non-destructive checks:

- config file loads
- storage directory exists/writable
- database can initialize and open
- static/templates exist
- global email config readiness for subscriptions
- SMTP connectivity/test optional behind a flag or clearly marked check
- schedule/web bind configuration sanity

Rationale: Deployment failures should be caught before users visit the public site.

### 5. Backup/restore are file-based SQLite operations

`backup.sh` creates timestamped copies of the SQLite database and companion WAL/SHM files when present. `restore.sh` stops services before restoring.

Rationale: simple, transparent, and appropriate for SQLite.

## Risks / Trade-offs

- **[Risk] SQLite writes during backup create inconsistent copy** → Mitigation: document/implement backup via `sqlite3 .backup` when available or stop services before restore.
- **[Risk] Two containers write the same SQLite DB** → Mitigation: current database uses WAL and busy timeout; document that web mostly reads while daemon writes.
- **[Risk] Secrets accidentally committed** → Mitigation: `.env` remains ignored; only `.env.example` is committed.
- **[Risk] Direct HTTP exposure is insecure** → Mitigation: document Caddy/Nginx/Cloudflare reverse proxy for HTTPS; default compose exposes configurable port for initial setup only.
- **[Trade-off] Docker Compose is VPS-oriented** → Acceptable for first deployment target; platform-specific PaaS can be added later.
