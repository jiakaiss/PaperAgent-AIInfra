## 1. Pipeline Split

- [x] 1.1 Add an ingest-only pipeline method that fetches, deduplicates, scores, and caches papers without notifying users.
- [x] 1.2 Add a scheduled cached-digest method that sends daily user digests from cached papers only.

## 2. Scheduler and Config

- [x] 2.1 Add schedule config fields for `ingest_interval_minutes`, `digest_hour`, and `digest_minute` with validation.
- [x] 2.2 Update daemon scheduler to register separate interval ingest and daily digest jobs.
- [x] 2.3 Update `config.yaml` for frequent ingest and 09:00 digest delivery.
- [x] 2.4 Update `config.example.yaml` comments/defaults to explain separate ingest and digest schedules.

## 3. Tests and Verification

- [x] 3.1 Add tests that verify ingest caches papers without notifying or marking sent.
- [x] 3.2 Add tests that verify daily digest sends from cached papers without fetching arXiv.
- [x] 3.3 Add tests that verify schedule config loads separate ingest/digest settings and remains backward compatible.
- [x] 3.4 Run `ruff check src/ tests/` and fix lint issues.
- [x] 3.5 Run `pytest tests/ -v` and fix failing tests.
- [x] 3.6 Restart the local web/daemon process so the updated configuration is active.
