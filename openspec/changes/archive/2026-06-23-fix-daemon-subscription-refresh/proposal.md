## Why

Users who subscribe via `/subscribe` after the daemon process has already started never receive digest emails, because the daemon loads subscriptions from the `subscriptions` table only once at startup (`cli.py:97` → `load_subscriptions_into_config`) and caches them in `Pipeline.user_notifiers` (`pipeline.py:60`). The web server's runtime-add path (per `subscription-storage` spec, "Runtime subscription addition") only mutates the web process's in-memory `AppConfig.users`; the separately-running daemon never sees the new row until it is restarted. This silently breaks the documented invariant that "pipeline processes papers for the new subscriber without requiring restart" whenever web and daemon run as distinct processes (the standard deployment shape).

## What Changes

- Daemon SHALL re-load active subscriptions from the `subscriptions` table at the start of every scheduled digest run (and every scheduled ingest run that subsequently filters per-user), so newly-added rows are picked up without process restart.
- `Pipeline.user_notifiers` SHALL be rebuilt to match the current `config.users` immediately before each digest dispatch, so per-user notifier construction stays consistent with the refreshed user list. Notifiers for users that disappear (unsubscribed since the previous tick) SHALL be dropped.
- Subscription refresh SHALL be idempotent and tolerate database read errors: a failure to refresh logs a warning and proceeds with the previously-loaded user list rather than aborting the digest run.
- `paper-agent run` (one-shot CLI) keeps its current behavior — it loads subscriptions once at startup, runs, and exits, so it does not need the per-run refresh logic.

## Capabilities

### New Capabilities
<!-- None — this change tightens an existing behavior. -->

### Modified Capabilities
- `subscription-storage`: Strengthen the "Runtime subscription addition" requirement so it holds across the daemon process (not just the web process). The existing scenario "pipeline processes papers for the new subscriber without requiring restart" SHALL hold even when the daemon is a separate process from the web server, by making the daemon re-read the subscriptions table each scheduled tick.

## Impact

- Code: `src/paper_agent/scheduler.py` (digest/ingest job wrappers), `src/paper_agent/pipeline.py` (expose a `refresh_users()` / notifier rebuild method that the scheduler calls), possibly `src/paper_agent/subscriptions.py` (helper to load + replace, not just append).
- Tests: `tests/test_pipeline.py` (new test: add a subscription row between two `run_cached_digest` invocations and assert the second one emits to the new user). Possibly a scheduler-level test using a fake clock.
- No DB schema changes. No config schema changes. No new dependencies.
- Performance: one extra `SELECT * FROM subscriptions WHERE status='active'` per scheduled job (small table, indexed by email). Negligible.
- Operations: removes the documented "restart the app to update existing subscription users" caveat from `CLAUDE.md` for the *user-set* dimension. SMTP credentials and thresholds still require restart (those are sourced from `config.yaml`, not the DB).
