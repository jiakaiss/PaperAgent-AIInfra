## MODIFIED Requirements

### Requirement: System status panel
The system SHALL serve `GET /admin/_system` as an HTML fragment summarizing the runtime state of the deployment, including: scoring model name, ingest interval, digest hour and timezone, SMTP host (NOT credentials), database path and on-disk size in bytes, the most recent `scored_at` timestamp from `papers` (used as a proxy for *paper-level activity*, NOT daemon liveness — the panel SHALL annotate this row to make the distinction clear), the most recent `sent_at` timestamp from `sent_papers` (last successful digest), the count of active subscriptions, the count of users currently loaded in the runtime `AppConfig.users` (so the operator can detect a load discrepancy), AND a daemon-liveness banner derived from `daemon_heartbeat.assess_health(db_path, ingest_interval_minutes)`.

The daemon banner SHALL appear at the top of the panel (above the data rows, because it's the most actionable signal) and SHALL render one of four visually-distinct states:

- `running` — green dot, shows PID, uptime, time-since-last-heartbeat, and last-event
- `stale` — amber dot, shows PID and age of last heartbeat with a "scheduler may be wedged" hint
- `dead` — red dot, shows PID with "process no longer exists" and the last recorded event
- `never_started` — gray dot, shows a hint to run `paper-agent daemon -c config.yaml`

#### Scenario: Renders without crashing on empty DB
- **WHEN** the panel loads against a freshly-created database with no papers, no sent rows, and no heartbeat file
- **THEN** the response is `200 OK`, the daemon banner renders `never_started`, and "last ingest" and "last digest" fields render `—` (or equivalent)

#### Scenario: Detects active-vs-runtime mismatch
- **WHEN** 10 active subscriptions exist in the database but only 9 users appear in the live `AppConfig.users`
- **THEN** the panel renders both numbers and visually highlights the mismatch (e.g., differing color or a warning glyph)

#### Scenario: Database size reported
- **WHEN** the panel loads
- **THEN** the database file size (in bytes, formatted human-readably) is rendered alongside the database path

#### Scenario: Daemon running banner
- **WHEN** the daemon is alive and its heartbeat is fresh
- **THEN** the panel renders a green-dot banner showing the daemon's PID, uptime, and the age of its last heartbeat

#### Scenario: Daemon dead banner
- **WHEN** the heartbeat file exists but the recorded PID is gone (e.g., the daemon crashed)
- **THEN** the panel renders a red-dot banner with the missing PID and the last recorded event

#### Scenario: Daemon stale banner
- **WHEN** the daemon process is alive but the heartbeat is older than 2× the ingest interval
- **THEN** the panel renders an amber-dot banner indicating the scheduler may be wedged

#### Scenario: Daemon never-started banner
- **WHEN** no heartbeat file exists next to the database
- **THEN** the panel renders a gray-dot banner with a hint to run `paper-agent daemon`

#### Scenario: Last-ingest row is annotated
- **WHEN** the panel renders the "最近一次 ingest" row
- **THEN** the row includes a note clarifying that the timestamp only advances when new papers are scored, distinct from daemon liveness
