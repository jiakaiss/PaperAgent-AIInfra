## Why

Current paper volume is low because paper discovery only happens when the notification pipeline runs. Operators need the system to query and score papers more frequently while keeping user-facing email delivery on a predictable daily 9:00 schedule.

## What Changes

- Split scheduled daemon work into two independent jobs:
  - frequent ingest job: fetch arXiv, deduplicate, score new papers, and cache them without sending notifications
  - daily digest job: at 09:00, filter cached papers per user and send notifications
- Keep subscription signup/update immediate digests cache-only, so they do not trigger arXiv/Claude calls.
- Preserve shared paper cache and per-user sent-paper deduplication.
- Update deployment config and examples to configure `ingest_interval_minutes` separately from daily digest time.

## Capabilities

### New Capabilities

### Modified Capabilities
- `delivery-volume-control`: Separate high-frequency ingestion from daily digest delivery and define their schedules independently.

## Impact

- Affected code: `Pipeline` gains cache-only digest and ingest-only methods; scheduler creates separate ingest and digest jobs.
- Affected config: `schedule` gains separate ingest interval and digest time settings; active `config.yaml` uses frequent ingest with 09:00 digest.
- Affected tests: scheduler/pipeline tests for ingest-without-notify and daily cache digest behavior.
- No database schema changes expected.
