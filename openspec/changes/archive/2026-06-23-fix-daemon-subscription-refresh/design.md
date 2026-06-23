## Context

`paper-agent` ships as two long-running processes that share one SQLite database:

- **Web server** (`paper-agent web`) — accepts `/subscribe` POSTs, inserts rows into `subscriptions`, and per the `subscription-storage` spec also appends a new `UserConfig` to its own in-process `AppConfig.users`.
- **Daemon** (`paper-agent daemon`) — runs the scheduled ingest and digest jobs. It calls `load_subscriptions_into_config(cfg)` exactly once before `Pipeline(cfg)` is constructed, and `Pipeline.__init__` then materializes `self.user_notifiers` from that snapshot.

Because each process holds its own `AppConfig` instance, the web process's "append at runtime" mutation never reaches the daemon's `AppConfig.users`. The daemon's `run_cached_digest` iterates `self.config.users`, which is the startup snapshot. Result: users who subscribe after the daemon starts are silently ignored until somebody restarts the daemon.

The fix lives entirely in the daemon: it must re-read the `subscriptions` table on each scheduled tick and reconcile against `Pipeline.user_notifiers`. The web-side runtime-add stays in place — it's a no-op for the daemon now, but it remains useful for unit tests and for any same-process invocations (e.g. `paper-agent run --user ...` after the user just subscribed).

## Goals / Non-Goals

**Goals:**
- Newly-subscribed users receive the next scheduled digest without anyone restarting the daemon.
- The change is a localized, low-risk refactor: no DB schema changes, no config schema changes, no new dependencies, and no observable behavior change for already-loaded users.
- Failure to refresh subscriptions (e.g. transient DB lock) MUST NOT abort the digest run — fall back to the previously-loaded user list and log a warning.

**Non-Goals:**
- Hot-reloading `config.email` SMTP credentials, `config.thresholds`, or any other `config.yaml`-sourced settings. Those still require a daemon restart, as documented in `CLAUDE.md`. (Out of scope because they aren't the reported bug, and live-reloading file-based config introduces its own race-condition surface.)
- Cross-process IPC or filesystem watcher to push subscription events from web → daemon. Pull-on-tick is sufficient, simpler, and matches the existing "daemon owns its own DB connection" pattern.
- Changing the per-user filter loop (`_run_for_user`) or notifier construction internals. Only the *set of users* iterated needs to refresh.

## Decisions

### Decision 1: Refresh on tick, not on every DB write

We refresh subscriptions at the top of each scheduled job in `scheduler.py` (`run_ingest`, `run_digest`), rather than building a cross-process change-notification channel.

**Rationale:** The daemon's smallest unit of observable action is a scheduled tick. Anything between ticks is invisible to users. A `SELECT * FROM subscriptions WHERE status='active'` against a small, indexed table costs microseconds and runs at most once per tick (digest is daily; ingest is configurable but typically hourly). The simpler alternative — make the web process write a "reload" sentinel file and the daemon poll it — adds two failure modes (sentinel cleanup, clock skew) for no measurable benefit.

**Alternatives considered:**
- *SIGHUP handler in the daemon, sent by the web process via PID file.* Rejected: introduces a second cross-process protocol, and the daemon's PID file is already used by the duplicate-daemon guard — multiplexing it for reload signaling muddies that contract. A SIGHUP can still be added later if we ever need sub-tick latency, and it would call the same refresh function.
- *SQLite triggers or `data_version` polling between ticks.* Rejected: requires either a background thread or a busy-loop in the BlockingScheduler. Both are heavier than the chosen approach.

### Decision 2: Refresh lives in `Pipeline`, called from scheduler

We add `Pipeline.refresh_users()` which (a) re-reads active subscriptions into `self.config.users`, (b) rebuilds `self.user_notifiers` to match. The scheduler's `run_ingest` and `run_digest` wrappers call it before invoking `pipeline.ingest()` / `pipeline.run_cached_digest()`.

**Rationale:** `Pipeline` already owns `config.users` and `user_notifiers` — keeping the mutation co-located with the structures it touches avoids a circular import (scheduler → subscriptions → pipeline) and makes the unit test trivial: construct a `Pipeline`, insert a subscription row, call `refresh_users()`, assert the new user appears in `user_notifiers`.

**Alternatives considered:**
- *Scheduler-level refresh that calls `load_subscriptions_into_config` directly and reconstructs the whole `Pipeline`.* Rejected: throws away the fetcher, scorer, and DB connection state — including in-flight WAL handles — every tick. Wasteful and ripe for resource leaks.
- *Make `Pipeline.config.users` a `property` backed by a fresh DB read.* Rejected: surprising aliasing semantics (every read returns a different list), and `_run_digest` iterates `self.config.users` multiple times per call — we'd need to materialize anyway. Explicit refresh is clearer.

### Decision 3: Reconciliation semantics

`refresh_users()` performs a full reconcile, not just an append:

- Users present in the DB and not in `config.users` → append a fresh `UserConfig`, build notifiers, add to `user_notifiers`.
- Users present in `config.users` and not in the DB (e.g. unsubscribed since last tick) → remove from `config.users`, drop their entry from `user_notifiers`.
- Users present in both → leave untouched. We do NOT rebuild notifiers for already-loaded users on every tick — that would mean reconstructing SMTP clients and re-applying the "SMTP creds frozen at process start" caveat would no longer hold. Keeping existing entries stable preserves the documented "restart to update SMTP creds" semantics.

**Rationale:** The bug report is about *new* subscribers not receiving emails; the reconcile also handles the symmetric "unsubscribed user got one extra email after toggling status" defect for free. Not rebuilding entries for already-loaded users is a deliberate stability choice — it limits the blast radius of the refresh to the smallest set that fixes the bug.

### Decision 4: Failure handling

If the DB read raises (locked DB, corrupt schema migration in flight), `refresh_users()` logs `WARNING` and returns without mutating state. The job then runs against the previous user list. This matches `scheduler.py`'s existing exception-handling pattern: every scheduled callable is already wrapped in `try/except` that logs and continues, so an unhandled exception inside `refresh_users()` would also be survivable — but degrading to "previous list" rather than "empty list" is a strictly better failure mode for users.

## Risks / Trade-offs

- **[Risk]** A subscription whose `notify` config can't be built (e.g. `is_email_configured(config.email)` flips to false between startup and tick) gets appended with `notify.email.enabled=false`, producing a no-op notifier. → **Mitigation:** `create_notifiers_for_user` already returns an empty list for disabled email config, and `Pipeline.__init__` already logs a warning when that happens. We reuse the same logging path in `refresh_users()` so operators see the same signal.
- **[Risk]** Two web processes (e.g. behind a reverse-proxy doing zero-downtime restarts) could both write the same subscription row; the daemon would see whichever survived the UNIQUE constraint. → **Mitigation:** Already handled by the existing UNIQUE constraint on `subscriptions.email`. No change needed.
- **[Trade-off]** SMTP credential changes still require a daemon restart. Users may expect "refresh on tick" to cover the global email block too. → Documented explicitly in `CLAUDE.md` ("Important: Changes to `config.email` … require app restart"). Out of scope here.
- **[Risk]** Test flake: the new pipeline test must avoid relying on `Pipeline` constructor caching state that depends on `config.users` ordering. → **Mitigation:** assert on `set(pipeline.user_notifiers.keys())`, not list order.

## Migration Plan

1. Land the code change behind no feature flag — the new code path runs unconditionally because the bug is silent and the old behavior has no users intentionally depending on it.
2. Update `CLAUDE.md`: change the line "Changes to `config.email`, `config.web.public_base_url`, or `config.thresholds` in `config.yaml` require app restart to affect existing subscription users. New subscriptions will use the updated config immediately." to clarify that *new subscriptions are now picked up by the running daemon without restart*, while *config.yaml changes still require restart*.
3. No data migration. No config migration. Restart the daemon once after deploy to pick up the new code; from that restart forward, subsequent subscription additions need no further restarts.

**Rollback:** Pure code revert. The `subscriptions` table is unchanged, so reverting only re-introduces the original silent bug; no data is at risk.

## Open Questions

- Should we also refresh per-user thresholds from the global `config.thresholds` on each tick? Currently they're frozen at conversion time (per `subscription-storage` spec). Decision deferred: out of scope for this change. Filed mentally as a follow-up if anyone complains.
