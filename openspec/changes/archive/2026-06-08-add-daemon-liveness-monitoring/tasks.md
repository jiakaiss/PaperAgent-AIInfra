## 1. Heartbeat module (`daemon_heartbeat.py`)

- [x] 1.1 Create `src/paper_agent/daemon_heartbeat.py` with `HEARTBEAT_SUFFIX = ".daemon.json"` and `heartbeat_path(db_path)` deriving the on-disk location.
- [x] 1.2 Implement `write_heartbeat(db_path, *, started_at=None, last_event="tick", extra=None)`. Preserve existing `started_at` across ticks when not given. Write atomically via `.tmp` + `os.replace`. Best-effort — never raise; log warnings on failure.
- [x] 1.3 Implement `read_heartbeat(db_path)` returning the parsed dict or `None` for missing/corrupt files.
- [x] 1.4 Implement `pid_is_alive(pid: int) -> bool` working cross-platform:
  - POSIX: `os.kill(pid, 0)`, treating `ProcessLookupError` as dead and `PermissionError` as alive.
  - Windows: `ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, …)` + `GetExitCodeProcess`, checking for `STILL_ACTIVE (259)`.
- [x] 1.5 Implement `assess_health(db_path, ingest_interval_minutes)` returning the four-state dict per the spec. Use `max(120, ingest_interval_minutes * 60 * 2 + 300)` as the stale threshold. Always return the full dict shape, even when no heartbeat exists.

## 2. Scheduler integration

- [x] 2.1 In `src/paper_agent/scheduler.py`, write an initial heartbeat with `last_event="startup"` BEFORE the scheduler starts.
- [x] 2.2 Wrap each scheduled job's body in `try/finally`; in the `finally`, write a heartbeat with `last_event="ingest"` or `"digest"` so failed jobs still tick.
- [x] 2.3 Add a heartbeat write with `last_event="shutdown"` in the SIGINT/SIGTERM handler, best-effort (wrap in `try/except`).
- [x] 2.4 Log the heartbeat file path on startup so the operator knows where to look.

## 3. Admin route + template + CSS

- [x] 3.1 Import `daemon_heartbeat.assess_health` in `src/paper_agent/web/admin.py`.
- [x] 3.2 Add `_format_duration(seconds)` helper rendering `45 秒` / `3 分钟` / `2 小时 15 分钟` / `5 天 3 小时`.
- [x] 3.3 In `admin_system` route, call `assess_health(config.storage.db_path, config.schedule.ingest_interval_minutes)` and pass it into the template context as `daemon`. Pre-compute `uptime_human` and `last_heartbeat_human` strings.
- [x] 3.4 In `admin/_system.html`, render a `.daemon-banner` with one of `daemon-running` / `daemon-stale` / `daemon-dead` / `daemon-never` classes at the top of the panel.
- [x] 3.5 Annotate the existing "最近一次 ingest" row with a note clarifying it only updates when new papers are scored.
- [x] 3.6 Add CSS in `admin.css` for the four banner colors, the colored status dot, and the muted secondary text.

## 4. Tests

- [x] 4.1 Create `tests/test_daemon_heartbeat.py`. Cover path derivation, write/read roundtrip, corrupt-file handling, `started_at` preservation, `pid_is_alive` for own/invalid/missing PIDs, and `assess_health` for all four states.
- [x] 4.2 Run the heartbeat tests in isolation: `pytest tests/test_daemon_heartbeat.py -v`.
- [x] 4.3 Run the full suite to confirm zero regressions: `pytest tests/`.

## 5. Validation + smoke test

- [x] 5.1 `ruff check src/ tests/` clean. Suppress the false-positive `N806` on the Windows API constant with `# noqa: N806`.
- [x] 5.2 `ruff format src/ tests/`.
- [x] 5.3 Restart the daemon + web; confirm the heartbeat file is created and the admin panel shows green-dot "Daemon 运行中".
- [x] 5.4 Kill the daemon mid-run; confirm the panel flips to red-dot "Daemon 已停止" without restarting the web process.
- [x] 5.5 `openspec validate add-daemon-liveness-monitoring --strict` passes.
