## MODIFIED Requirements

### Requirement: `paper-agent web` CLI command
The CLI SHALL expose a `web` subcommand that launches the web server. It SHALL accept `--host` (default `127.0.0.1`) and `--port` (default `8000`) options, plus `--config` to locate `config.yaml`. For containerized deployment, the Docker Compose `web` service SHALL run this command with `--host 0.0.0.0` so it is reachable from outside the container.

#### Scenario: Default launch
- **WHEN** the operator runs `paper-agent web`
- **THEN** the server binds to `127.0.0.1:8000` and serves the web UI

#### Scenario: Custom host and port
- **WHEN** the operator runs `paper-agent web --host 0.0.0.0 --port 9000`
- **THEN** the server binds to `0.0.0.0:9000`

#### Scenario: Config path is forwarded
- **WHEN** `paper-agent web --config /etc/paper-agent/config.yaml` is run
- **THEN** the web app reads its storage path and scoring settings from that file

#### Scenario: Container launch
- **WHEN** the Docker Compose `web` service starts
- **THEN** it runs `paper-agent web --host 0.0.0.0 --port <configured-port> --config /app/config.yaml`

### Requirement: Health endpoint
The app SHALL expose `GET /health` returning JSON `{"status": "ok"}` for liveness probes. Docker Compose SHALL use this endpoint as the web container health check.

#### Scenario: Health check
- **WHEN** `GET /health` is requested
- **THEN** the response is `200 OK` with body `{"status": "ok"}`

#### Scenario: Container health check
- **WHEN** Docker runs the configured health check for the web service
- **THEN** it requests `/health` and marks the container healthy only when the endpoint returns successfully
