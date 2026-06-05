## Context

The current pipeline couples ingestion and notification: a scheduled run fetches arXiv, scores new papers, filters per user, and sends notifications. Increasing that schedule frequency would discover more papers sooner, but it would also email users more frequently, which is not desired. The desired behavior is high-frequency backend ingestion with a single daily user-facing digest at 09:00.

## Goals / Non-Goals

**Goals:**
- Run arXiv fetch/scoring/cache multiple times per day.
- Send user notifications only once per day at the configured digest time.
- Reuse the existing `papers` cache and `sent_papers` deduplication.
- Keep subscription immediate send cache-only and separate from ingestion.

**Non-Goals:**
- Changing arXiv query construction, scoring prompts, or sub-domain taxonomy.
- Adding a separate process/service for ingestion.
- Adding adaptive frequency based on paper volume.
- Sending multiple daily digest emails by default.

## Decisions

### Split Pipeline into ingest-only and cached-digest paths

Add an ingest-only method that performs the shared phase: fetch arXiv, filter uncached IDs, score only new papers, and cache results. It returns cached/scored papers for observability but does not call notifiers and does not mark sent.

Add a cached digest method for scheduled delivery that loads all cached scored papers from the database and reuses existing per-user filtering/threshold/top_n/sent dedup/notify behavior.

Rationale: this keeps the existing scoring and notification logic, but makes scheduling semantics explicit.

### Scheduler runs two jobs

The daemon will create:
- `paper_ingest`: interval trigger, default every 360 minutes
- `paper_digest`: cron trigger at `digest_hour:digest_minute`, default 09:00

On daemon startup, run ingest once to populate cache. Do not automatically send a digest on startup unless the digest cron fires.

Alternatives considered:
- Use interval mode for full pipeline: rejected because it sends too often.
- Use cron only: keeps email schedule stable but does not increase discovery frequency.
- Create separate daemons: operationally more complex.

### Config keeps backward-compatible names where possible

Retain existing `cron_hour` and `cron_minute` as aliases/default sources for digest time, while adding explicit `ingest_interval_minutes`, `digest_hour`, and `digest_minute` for clarity.

## Risks / Trade-offs

- More frequent ingestion can trigger arXiv rate limits → keep a conservative default interval and existing backoff.
- New papers can increase Claude API usage → cache deduplication ensures known papers are not rescored.
- Startup no longer sends digest automatically → operators can still run `paper-agent run` manually for one-off full send, while daemon startup focuses on ingestion.
- Loading all cached papers for daily digest can grow over time → existing filters and top_n limit final delivery; future work can add cache-window filtering if needed.

## Migration Plan

1. Add `Pipeline.ingest()` and `Pipeline.run_cached_digest()` methods.
2. Update daemon scheduler to register separate ingest interval and daily digest cron jobs.
3. Update active `config.yaml` and `config.example.yaml` with separate ingest/digest settings.
4. Add tests for ingest not notifying, cached digest notifying from cache, and scheduler job setup.
5. Restart the running web/daemon process as needed.
