## 1. Pipeline refresh primitive

- [x] 1.1 Add `Pipeline.refresh_users()` to `src/paper_agent/pipeline.py` that re-reads active subscriptions via `load_subscriptions_into_config`-style logic and reconciles `self.config.users` and `self.user_notifiers` against the database. New users → append + build notifiers. Departed users → drop from both. Existing users → leave untouched (do NOT rebuild notifiers).
- [x] 1.2 Wrap the DB read in `refresh_users()` in `try/except`; on failure, log a `WARNING` (`"Subscription refresh failed; using previous user list (N users): <err>"`) and return without mutating state.
- [x] 1.3 Factor the subscription-row → `UserConfig` construction in `subscriptions.py` so it can be reused by `refresh_users()` without re-running global-state warnings on every tick (the "email config missing" warning should still fire when a *new* user is appended, but not for already-loaded ones).

## 2. Scheduler integration

- [x] 2.1 In `src/paper_agent/scheduler.py`, call `pipeline.refresh_users()` at the top of `run_digest()` (before `pipeline.run_cached_digest(...)`).
- [x] 2.2 Also call `pipeline.refresh_users()` at the top of `run_ingest()`, so the per-user post-ingest digest path (`pipeline.run`) sees fresh users too. Refresh happens BEFORE the existing `try/except` around the pipeline call so a refresh failure still gets caught by the outer handler if it ever raises.
- [x] 2.3 Also call `pipeline.refresh_users()` once during the initial-ingest path at the bottom of `start_daemon()` (`run_ingest()` call before `scheduler.start()`), so the first tick after startup is consistent with subsequent ticks.

## 3. Tests

- [x] 3.1 Add `tests/test_pipeline.py::test_pipeline_refresh_users_appends_new_subscription`: construct a `Pipeline` with one subscription, then insert a second subscription row directly into the DB, then call `pipeline.refresh_users()`, then assert both user_ids are in `pipeline.user_notifiers`.
- [x] 3.2 Add `test_pipeline_refresh_users_drops_inactive`: start with two subscriptions, mark one inactive via the existing subscription-storage helper, call `refresh_users()`, assert the dropped user is gone from `pipeline.user_notifiers` and the remaining user's notifier instance is the SAME object as before (identity check, to enforce Decision 3's "don't rebuild existing notifiers").
- [x] 3.3 Add `test_pipeline_refresh_users_survives_db_error`: monkey-patch the DB call inside `refresh_users()` to raise, assert no mutation, assert a warning was logged, assert the previous user list is intact.
- [x] 3.4 Add an end-to-end test that calls `pipeline.run_cached_digest(dry_run=True)` twice with a subscription inserted between the two calls, and asserts the second invocation's result dict contains the new user_id.

## 4. Docs

- [x] 4.1 Update `CLAUDE.md` "Web Subscriptions" → "Important" paragraph: clarify that new subscriptions are picked up by the running daemon at the next scheduled tick without restart, while `config.email`, `config.web.public_base_url`, and `config.thresholds` changes still require restart.
- [x] 4.2 Update `CLAUDE.md` "Troubleshooting" → "Subscription users not receiving emails" to drop the "daemon must be restarted after subscribe" implication if any remains, and add a new bullet: "If a user subscribed less than `schedule.ingest_interval_minutes` ago, the daemon may not have ticked yet — wait for the next digest hour."

## 5. Verification

- [x] 5.1 Run `pytest tests/ -v` — all green, including the four new tests above.
- [x] 5.2 Run `ruff check src/ tests/` and `ruff format --check src/ tests/`.
- [ ] 5.3 Manual smoke test (Windows): `paper-agent daemon -c config.yaml` in one shell; in another shell, POST to `/subscribe` with a new email; force a digest tick (or set `schedule.digest_hour` to one minute from now and wait); confirm the new email receives a digest without restarting the daemon. Capture daemon log line showing `"refresh_users: +1 added"`-style output.
