## ADDED Requirements

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

### Requirement: FastAPI application
The web layer SHALL be implemented as a FastAPI application. The app SHALL mount Jinja2 templates from `src/paper_agent/web/templates` and static assets from `src/paper_agent/web/static`.

#### Scenario: Templates render
- **WHEN** a browser requests `/`
- **THEN** the response is HTML rendered by a Jinja2 template

#### Scenario: Static assets served
- **WHEN** a browser requests `/static/style.css`
- **THEN** the response is the CSS file with `Content-Type: text/css`

### Requirement: HTMX partial rendering
Interactive UI elements (keyword chip filter, pagination, search) SHALL use HTMX `hx-get` attributes to swap the paper-list fragment without full reloads. HTMX JS SHALL be served from `static/vendor/` (no CDN dependency). Mode toggle and sub-domain selection are handled client-side (JS updates `localStorage` and re-issues the HTMX request with new query params).

#### Scenario: Chip filter updates in place
- **WHEN** the user clicks a sub-domain chip
- **THEN** only the paper list fragment is re-fetched and swapped; the rest of the page is untouched

### Requirement: PaperDatabase dependency injection
The FastAPI app SHALL expose `PaperDatabase` via a dependency function so route handlers receive a per-request instance. The database SHALL be opened with SQLite WAL journal mode.

#### Scenario: Concurrent reads while daemon writes
- **WHEN** the `paper-agent daemon` is inserting scored papers and a web request queries the paper list
- **THEN** the web request returns successfully without `database is locked`

### Requirement: Health endpoint
The app SHALL expose `GET /health` returning JSON `{"status": "ok"}` for liveness probes. Docker Compose SHALL use this endpoint as the web container health check.

#### Scenario: Health check
- **WHEN** `GET /health` is requested
- **THEN** the response is `200 OK` with body `{"status": "ok"}`

#### Scenario: Container health check
- **WHEN** Docker runs the configured health check for the web service
- **THEN** it requests `/health` and marks the container healthy only when the endpoint returns successfully

### Requirement: Graceful shutdown
On SIGTERM / SIGINT the server SHALL close the SQLite connection and exit cleanly.

#### Scenario: Ctrl-C
- **WHEN** the operator presses Ctrl-C while `paper-agent web` is running
- **THEN** the process exits with status 0 and no pending writes are lost

### Requirement: Conditional admin router registration
The FastAPI app factory SHALL conditionally register the admin router. The admin router SHALL be registered only when `AppConfig.admin.enabled` is `true` AND `AppConfig.admin.password` is a non-empty, non-whitespace-only string. When this condition does not hold, the admin router SHALL NOT be registered, with the effect that every `/admin*` URL is handled by FastAPI's default 404 handler.

#### Scenario: Admin enabled and password set
- **WHEN** `create_app` runs with `admin.enabled=true` and a real password
- **THEN** the admin router is registered and `/admin` returns `401` (with `WWW-Authenticate`) for an unauthenticated request

#### Scenario: Admin disabled
- **WHEN** `create_app` runs with `admin.enabled=false`
- **THEN** the admin router is not registered and `/admin` returns `404`

#### Scenario: Admin enabled but password empty
- **WHEN** `create_app` runs with `admin.enabled=true` and an empty `admin.password`
- **THEN** the admin router is not registered and `/admin` returns `404`

#### Scenario: Public routes unaffected
- **WHEN** the admin router is or is not registered
- **THEN** the public routes (`/`, `/_paper_list`, `/subscribe`, `/api/subscribe`, `/unsubscribe`, `/health`) are reachable and behave identically in both cases
