## ADDED Requirements

### Requirement: Docker image build
The project SHALL provide a Dockerfile that builds a runnable Paper Agent image without embedding secrets.

#### Scenario: Image builds successfully
- **WHEN** the operator runs `docker build -t paper-agent .`
- **THEN** Docker builds an image containing the installed `paper-agent` CLI and web assets

#### Scenario: No secrets in image
- **WHEN** the Docker image is built
- **THEN** `.env`, `config.yaml`, SQLite database files, logs, and backups are not copied into the image

### Requirement: Docker Compose services
The project SHALL provide `docker-compose.yml` with separate `web` and `daemon` services sharing the same image and persistent volumes.

#### Scenario: Start web and daemon
- **WHEN** the operator runs `docker compose up -d`
- **THEN** both `web` and `daemon` services start successfully

#### Scenario: Web binds to public interface in container
- **WHEN** the `web` service starts
- **THEN** it runs `paper-agent web` with `--host 0.0.0.0` and exposes the configured container port

#### Scenario: Daemon uses same config and database
- **WHEN** the `daemon` service runs
- **THEN** it reads the same config file and SQLite database volume as the `web` service

### Requirement: Persistent host volumes
Docker deployment SHALL persist config, SQLite data, logs, and backups in host-mounted directories.

#### Scenario: Data survives rebuild
- **WHEN** the operator rebuilds the Docker image and restarts services
- **THEN** the SQLite database and subscriptions remain present

#### Scenario: Logs written to mounted directory
- **WHEN** services write logs configured to `/app/logs`
- **THEN** logs are visible on the host under the deployment logs directory

### Requirement: Environment template
The project SHALL provide `.env.example` documenting all environment variables required for Docker deployment.

#### Scenario: Operator prepares environment
- **WHEN** the operator copies `.env.example` to `.env` and fills values
- **THEN** Docker Compose can inject LLM and SMTP secrets into the containers

#### Scenario: .env ignored by git
- **WHEN** `.env` exists locally
- **THEN** git does not track it by default
