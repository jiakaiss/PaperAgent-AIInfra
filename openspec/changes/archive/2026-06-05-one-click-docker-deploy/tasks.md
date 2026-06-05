## 1. Docker image and compose

- [x] 1.1 Create `.dockerignore` excluding secrets, local DB, logs, caches, and virtualenvs
- [x] 1.2 Create `Dockerfile` using Python 3.11 slim image and editable/project install
- [x] 1.3 Ensure Docker image contains CLI entrypoint and web static/templates
- [x] 1.4 Create `docker-compose.yml` with `web` and `daemon` services sharing image and volumes
- [x] 1.5 Add web healthcheck using `GET /health`
- [x] 1.6 Add persistent volume mounts for config, data, logs, and backups

## 2. Environment and deployment config

- [x] 2.1 Create `.env.example` with LLM, SMTP, timezone, web port, and path variables
- [x] 2.2 Create deploy config template under `deploy/config/config.yaml.example`
- [x] 2.3 Update `.gitignore` to exclude `.env`, deployment config, data, logs, and backups
- [x] 2.4 Ensure config template references environment variables for secrets

## 3. Doctor CLI

- [x] 3.1 Add `paper-agent doctor -c config.yaml` CLI command
- [x] 3.2 Implement config load/validation check
- [x] 3.3 Implement storage path writable and SQLite initialization check
- [x] 3.4 Implement web static/templates existence check
- [x] 3.5 Implement global email readiness check using existing subscription helper
- [x] 3.6 Add doctor command tests for success and common failures

## 4. Deployment scripts

- [x] 4.1 Create `scripts/deploy.sh` to validate `.env`, create directories, run doctor, build, and start compose
- [x] 4.2 Create `scripts/backup.sh` to create timestamped SQLite backups
- [x] 4.3 Create `scripts/restore.sh` to restore a selected backup safely
- [x] 4.4 Make scripts POSIX shell compatible and executable
- [x] 4.5 Add script smoke tests or static validation where practical

## 5. Documentation

- [x] 5.1 Add Docker/VPS deployment guide (new docs file or README section)
- [x] 5.2 Document first-time setup: install Docker, copy `.env`, copy config template, deploy
- [x] 5.3 Document operations: logs, restart, upgrade, backup, restore
- [x] 5.4 Document HTTPS/reverse proxy options and security checklist
- [x] 5.5 Document troubleshooting for env vars, SMTP auth, port conflicts, and DB permissions

## 6. Verification

- [x] 6.1 Run `paper-agent doctor` against example/test config
- [x] 6.2 Build Docker image locally if Docker is available (skipped: Docker not available in current environment)
- [x] 6.3 Validate docker-compose configuration if Docker Compose is available (static YAML validation completed; Docker Compose not available in current environment)
- [x] 6.4 Run relevant Python tests
- [x] 6.5 Run lint/format checks on modified Python files
