## Why

The admin dashboard's "system status" panel shipped with two timestamps — *last ingest* and *last digest* — but neither is a reliable liveness signal. On 2026-06-08 the operator confirmed both: a daemon that was fetching 91 papers/cycle yet finding zero new ones (all cache hits) left `papers.scored_at` frozen, making "last ingest = 12:12" look like the daemon was sick when it was actually fine. Conversely, a crashed scheduler leaves both timestamps looking healthy for hours after the process dies.

Without an explicit liveness signal the operator falls back to SSH + `ps`, which defeats the purpose of having a dashboard.

## What Changes

- Add a **heartbeat file** (`<db_path>.daemon.json`) that the scheduler writes on startup, after every ingest/digest tick, and on shutdown. Contains PID, started-at, last-heartbeat-at, and last-event (`"startup"` / `"ingest"` / `"digest"` / `"shutdown"`).
- Add a **PID liveness check** that works on POSIX (`os.kill(pid, 0)`) and Windows (`OpenProcess` via ctypes — no `psutil` dependency).
- Add a **health assessment** combining both signals into one of four statuses:
  - `running` — PID alive AND heartbeat younger than 2× ingest interval (+5 min grace)
  - `stale` — PID alive but heartbeat older than threshold (scheduler wedged)
  - `dead` — PID no longer exists
  - `never_started` — no heartbeat file present
- Add a **colored banner at the top of the admin system panel** showing the status, PID, uptime, time-since-last-heartbeat, and last-event. Replaces inferring liveness from `last_ingest_at`.
- Annotate the existing `最近一次 ingest` row with "(仅在有新论文入库时更新，daemon 仍可能正常运行)" so the operator doesn't conflate the two signals.

## Capabilities

### New Capabilities
- `daemon-liveness`: Heartbeat file format, write contract (when the scheduler ticks it), and the four-state health assessment combining PID liveness with heartbeat freshness.

### Modified Capabilities
- `admin-dashboard`: System panel gains a daemon-status banner and a clarifying annotation on the existing "last ingest" row.

## Impact

**Affected code:**
- `src/paper_agent/daemon_heartbeat.py` — **new file** (~190 lines): `heartbeat_path`, `write_heartbeat`, `read_heartbeat`, `pid_is_alive`, `assess_health`.
- `src/paper_agent/scheduler.py` — +14 lines: startup write + `finally`-block writes around ingest/digest/shutdown.
- `src/paper_agent/web/admin.py` — +30 lines: `_format_duration` helper + `assess_health` call in `admin_system` route.
- `src/paper_agent/web/templates/admin/_system.html` — banner block + annotation on existing row.
- `src/paper_agent/web/static/admin.css` — 4-color banner styles + status dot.
- `tests/test_daemon_heartbeat.py` — **new file** (13 unit tests).

**Dependencies:** none new. PID check uses stdlib (`os.kill` on POSIX, `ctypes` on Windows).

**Out of scope:**
- Active alerting (email/webhook when daemon dies) — out of scope for a passive dashboard.
- Auto-restart on failure — that's the deployment system's job (systemd `Restart=on-failure`, Docker `restart: unless-stopped`, etc.).
- Per-job liveness (separate signal for ingest vs digest) — both share one scheduler; if the scheduler is alive both fire.
