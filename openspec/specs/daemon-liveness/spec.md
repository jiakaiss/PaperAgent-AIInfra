# daemon-liveness Specification

## Purpose

Provide a liveness signal for the `paper-agent daemon` process that the admin dashboard (or any operator tooling) can read to distinguish "scheduler running and ticking" from "scheduler crashed" from "scheduler wedged" — without confusing those with "no new papers were available to score". The signal lives in a small JSON heartbeat file co-located with the SQLite database so that read paths work even when the database is locked under write load.

## Requirements

### Requirement: Heartbeat file location and format
The daemon SHALL maintain a heartbeat file at `<storage.db_path>.daemon.json` containing a JSON object with at least the keys `pid` (integer, process id), `started_at` (ISO timestamp, daemon start time), `last_heartbeat_at` (ISO timestamp, most recent tick), and `last_event` (string: one of `"startup"`, `"ingest"`, `"digest"`, `"shutdown"`, `"tick"`). The path SHALL track `storage.db_path` so that moving the database also moves the heartbeat.

#### Scenario: Heartbeat path derivation
- **WHEN** `storage.db_path` is `paper_agent.db`
- **THEN** the heartbeat is written at `paper_agent.db.daemon.json` in the same directory

#### Scenario: File is parseable JSON
- **WHEN** the heartbeat has been written at least once
- **THEN** `json.loads(open(heartbeat_path).read())` returns a dict containing `pid`, `started_at`, `last_heartbeat_at`, `last_event`

#### Scenario: Custom db_path moves the heartbeat
- **WHEN** `storage.db_path` is `/var/lib/papers/prod.db`
- **THEN** the heartbeat is written at `/var/lib/papers/prod.db.daemon.json`

### Requirement: Heartbeat write contract
The daemon SHALL write the heartbeat:
- Once on startup, with `last_event="startup"`
- Once at the end of every scheduled `ingest` invocation, with `last_event="ingest"`, regardless of whether the ingest succeeded
- Once at the end of every scheduled `digest` invocation, with `last_event="digest"`, regardless of whether the digest succeeded
- Best-effort once on graceful shutdown, with `last_event="shutdown"`

Writes SHALL preserve the original `started_at` across ticks. Writes SHALL be atomic (write to `.tmp` then `os.replace`). Write failures SHALL be logged but MUST NOT crash the daemon.

#### Scenario: Startup writes initial heartbeat
- **WHEN** the daemon starts
- **THEN** the heartbeat file exists with `last_event="startup"` and `pid` equal to the daemon's process id, before any scheduled job has run

#### Scenario: Failed job still ticks heartbeat
- **WHEN** a scheduled ingest raises an exception (e.g., arXiv API down)
- **THEN** the heartbeat is still updated with `last_event="ingest"` and a fresh `last_heartbeat_at`

#### Scenario: Started-at survives across ticks
- **WHEN** the daemon writes its startup heartbeat at T0 and then ticks an ingest at T1
- **THEN** the heartbeat at T1 has `started_at = T0` and `last_heartbeat_at = T1`

#### Scenario: Atomic write
- **WHEN** the heartbeat is being written and a reader opens it concurrently
- **THEN** the reader sees either the old complete file or the new complete file, never a partially-written file

#### Scenario: Write failure does not crash daemon
- **WHEN** the heartbeat write fails (e.g., disk full)
- **THEN** the daemon logs a warning and continues running

### Requirement: PID liveness check
The system SHALL provide `pid_is_alive(pid: int) -> bool` that returns `True` when a process with the given PID exists and `False` otherwise. The implementation SHALL work on POSIX and Windows without requiring any third-party dependency.

#### Scenario: Own PID is alive
- **WHEN** `pid_is_alive(os.getpid())` is called
- **THEN** it returns `True`

#### Scenario: Invalid PID
- **WHEN** `pid_is_alive(0)` or `pid_is_alive(-1)` is called
- **THEN** it returns `False`

#### Scenario: Far-out-of-range PID
- **WHEN** `pid_is_alive(999_999_999)` is called on a system where no such PID exists
- **THEN** it returns `False`

### Requirement: Health assessment
The system SHALL provide `assess_health(db_path, ingest_interval_minutes) -> dict` returning a dict with at minimum the keys `status` (one of `"running"`, `"stale"`, `"dead"`, `"never_started"`), `pid`, `started_at`, `last_heartbeat_at`, `last_event`, and `age_seconds`. Status semantics:

- `never_started`: no heartbeat file present
- `dead`: heartbeat file exists but the recorded PID is no longer alive
- `stale`: PID is alive but `last_heartbeat_at` is older than `2 * ingest_interval_minutes * 60 + 300` seconds (with a floor of 120 seconds)
- `running`: PID is alive AND heartbeat is within the freshness window

The function SHALL handle missing files, corrupt JSON, and unparseable timestamps without raising — every failure mode maps to one of the four statuses.

#### Scenario: Never-started returns the right dict shape
- **WHEN** `assess_health` is called against a `db_path` that has no `.daemon.json` next to it
- **THEN** the return dict has `status="never_started"`, `pid=None`, `started_at=None`, `last_heartbeat_at=None`, `last_event=None`, `age_seconds=None`

#### Scenario: Running daemon
- **WHEN** the heartbeat file was just written and the recorded PID is the current process
- **THEN** `assess_health` returns `status="running"` with matching `pid`

#### Scenario: Stale heartbeat
- **WHEN** the heartbeat file is 7 hours old and `ingest_interval_minutes=180` (3 hours)
- **THEN** `assess_health` returns `status="stale"`

#### Scenario: Dead PID
- **WHEN** the heartbeat file records a PID that no longer exists
- **THEN** `assess_health` returns `status="dead"` regardless of heartbeat freshness

#### Scenario: Corrupt heartbeat file
- **WHEN** the heartbeat file exists but contains invalid JSON
- **THEN** `assess_health` treats it as missing and returns `status="never_started"` rather than raising
