## Context

The `add-admin-dashboard` change shipped a system panel with `last_ingest_at` (max of `papers.scored_at`) and `last_digest_at` (max of `sent_papers.sent_at`) — both derived from work *outputs*, not from the scheduler's own state. This creates two failure modes:

1. **False alarm**: every ingest fetches papers and finds them all already cached → no new papers scored → `last_ingest_at` stops advancing → looks like the daemon died.
2. **False reassurance**: scheduler thread crashes after a successful run → both timestamps stay fresh for hours/days while no new work happens.

The operator hit #1 on 2026-06-08 (91 papers fetched, 91 cache hits, `scored_at` frozen at 12:12 even though daemon was healthy at 20:00) and that was the prompt for this change.

The signal we actually want is whether the **scheduler thread is still calling its jobs**, regardless of whether the jobs produce output. This is exactly what a heartbeat is for.

**Constraints:**
- Reuse existing dependencies — the project keeps a strict no-new-deps policy. Rules out `psutil`.
- Work on both POSIX (production VPS) and Windows (operator's dev machine).
- Robust to corrupt / missing files — admin dashboard must never crash because the heartbeat is malformed.
- File-based, not DB-based — the heartbeat reader (web process) must work even if SQLite is locked by the daemon writer.

## Goals / Non-Goals

**Goals:**
- One look at `/admin` tells the operator whether the daemon is alive and ticking.
- Distinguish four distinct failure modes (running / stale / dead / never-started) with different recovery actions.
- Add no new Python dependencies.
- Work cross-platform.

**Non-Goals:**
- Push notifications when status degrades. The dashboard is pull-only by design.
- Restarting the daemon from the dashboard. Process supervision is the deployment system's job.
- Tracking per-job latency or success rate. A binary "is it ticking" is sufficient for now; granular metrics would belong in a separate observability change.
- Replacing the existing `last_ingest_at` / `last_digest_at` rows. They still answer "did anything land?", which is a different and useful question. They get an annotation to make their semantics clear.

## Decisions

### Decision 1: Heartbeat file beside the SQLite DB, not in a table

**Choice:** Write `<db_path>.daemon.json` (e.g., `paper_agent.db.daemon.json`).

**Rationale:**
- File-based so the reader works even when SQLite is locked under load.
- Co-located with the DB so deployments that move `storage.db_path` move the heartbeat automatically.
- Human-readable for debugging: `cat paper_agent.db.daemon.json` shows the daemon's view of the world.

**Alternative considered:** SQLite `daemon_state` table. Rejected — couples web reads to writer's lock contention, and gives no `cat`-friendly debugging.

### Decision 2: PID liveness via stdlib only (`os.kill` + `ctypes`)

**Choice:** POSIX uses `os.kill(pid, 0)`; Windows uses `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION) + GetExitCodeProcess` via `ctypes.windll.kernel32`.

**Rationale:**
- Adding `psutil` for one function is overkill. ~20 lines of ctypes is well within reason.
- Matches the project's "stdlib-first" pattern (see `secrets.compare_digest` for auth, `csv` for CSV export).

**Alternative considered:** `psutil`. Rejected — first new dependency for the whole project, only used in one function.

### Decision 3: 2× ingest interval (+ 5 min grace) as the "stale" threshold

**Choice:** `stale_after_s = max(120, ingest_interval_minutes * 60 * 2 + 300)`.

**Rationale:**
- A daemon that misses one full cycle is suspicious; missing two is definitely wedged.
- 5-minute grace covers slow ingest (large arXiv response, slow LLM call), avoiding flaps right after a cycle boundary.
- Floor of 2 min guards against pathologically short configured intervals (testing setups with `ingest_interval_minutes: 1`).

**Alternatives considered:**
- *1× interval*: too tight — flaps any time ingest takes more than half a cycle.
- *Fixed 1-hour threshold*: works for the 6-hour default but lies for a 30-min-interval deployment.

### Decision 4: Tick the heartbeat in a `finally` block, not after success

**Choice:** Each scheduled job wraps its work in `try/finally` and the heartbeat write is in the `finally`.

**Rationale:**
- A failed ingest (arXiv timeout, LLM API down) still proves the scheduler is alive and trying — that's exactly what we want to surface.
- A wedged scheduler (deadlock, infinite loop in a job) stops ticking entirely, which is what `stale` status detects.

### Decision 5: Four discrete states, not a score

**Choice:** `running` / `stale` / `dead` / `never_started`.

**Rationale:**
- Each state has a different recovery action: nothing / investigate logs / restart process / first-time setup. A numeric "health score" obscures that.
- Color-codes naturally in the UI: green / amber / red / gray.

### Decision 6: Spec-first reconciliation (this change is retroactive)

**Choice:** Write proposal/design/specs/tasks describing the work as if it were planned upfront, with all tasks pre-marked `[x]` since the implementation already shipped.

**Rationale:**
- Keeps `openspec/specs/` an accurate canonical reference for future contributors and changes.
- Per the operator's request, project convention is spec-first; an un-spec'd ship is a debt that compounds.
- The validation pass (`openspec validate --strict`) still catches malformed deltas before they merge into main specs.

## Risks / Trade-offs

- **Risk: Heartbeat file gets stale across `db_path` changes** if operator points config to a different DB. *Mitigation:* heartbeat path tracks `db_path`, so moving the DB moves the heartbeat path; old heartbeat file is left orphaned (harmless).

- **Risk: Concurrent writes during a SIGTERM race could leave a `.tmp` file.** *Mitigation:* writes go through `os.replace` (atomic on both POSIX and Windows); orphan `.tmp` is harmless and overwritten on next tick.

- **Risk: Operator runs two daemon instances against the same DB.** *Mitigation:* last writer wins; the dashboard shows whichever PID is newer. Out of scope to detect this — operators running two daemons have bigger problems.

- **Trade-off: No way to distinguish "operator stopped daemon intentionally" from "daemon crashed".** *Mitigation:* shutdown handler writes `last_event: "shutdown"` before exit; dashboard shows that even after PID dies, so a graceful stop reads as `dead` with `last_event: shutdown` (distinguishable from `last_event: ingest` for an unexpected crash).

- **Trade-off: PID can be reused** by another process after daemon dies. *Mitigation:* heartbeat freshness check catches this in the common case — a reused PID belongs to some other process that isn't writing our heartbeat, so the heartbeat goes stale within one interval and the status flips to `stale`. Brief window of false `running` is acceptable for this severity level.

## Migration Plan

1. New deployments: nothing to do — heartbeat file created on first daemon start.
2. Existing deployments running the old daemon: status shows `never_started` until the daemon is restarted. Documentation (CLAUDE.md) will note this one-time restart requirement when this change lands.

**Rollback:** Revert the scheduler change to stop writing the heartbeat, and revert the admin route to drop `assess_health` call. Heartbeat file becomes a harmless orphan; can be deleted at leisure.
