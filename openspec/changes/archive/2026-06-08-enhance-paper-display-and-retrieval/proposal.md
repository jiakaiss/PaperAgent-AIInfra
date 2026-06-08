## Why

The current paper agent surfaces papers with only a Chinese summary, two numeric scores, and sub-domain tag chips. Users cannot quickly distinguish high-impact work from incremental papers, and the rendered abstract lacks the structured signal (key contributions, problem framed, methods) that readers actually scan for. On the retrieval side, the superset fetch is a flat union of arXiv keywords with no quality tier or recency boost, so noisy keyword matches crowd out higher-signal results before scoring ever runs. We need both a richer paper presentation and a smarter retrieval/ranking layer so that the digest reflects "what's worth reading" rather than "what matched a keyword."

## What Changes

- **Scoring schema extension**: Add structured fields to `SCORE_TOOL` and `ScoredPaper` — `key_contributions: list[str]` (1–3 bullets), `problem_statement_zh: str`, `methods_zh: str`, and a coarse `impact_tier` enum (`breakthrough` / `solid` / `incremental`). The scorer prompt is updated to extract these explicitly.
- **Web card redesign**: Render the new fields on each paper card with a tiered visual treatment — `breakthrough` papers get a highlighted border + badge, `solid` get standard styling, `incremental` are dimmed/collapsible. Key contributions render as a bulleted list under the summary.
- **Tier-aware filtering**: `/` and `/_paper_list` accept `?tier=<breakthrough|solid|incremental>` (repeatable). Preferences panel gains a "minimum tier" selector synced to `localStorage`. Default view excludes `incremental` so the front page reads as a curated digest.
- **Smarter retrieval (dual-track fetch)**: Today the fetcher runs one path — union the keywords, query each, share one budget — which lets one noisy keyword (e.g. `"serving"`) eat the budget and starve precise keywords, AND misses good papers that simply use different terminology than the subscribed words. Fix it with two parallel paths in the same fetch: (1) the existing keyword search, but with a per-keyword cap so no single keyword can dominate; (2) a recency pass that pulls recent papers from related arXiv categories (default `cs.LG`, `cs.DC`) regardless of keyword match. Results from both paths are merged and deduped by `arxiv_id` before scoring. Gated by `fetch.quality_floor_strategy` — existing configs keep today's behavior until the operator opts in.
- **Card-level sorting**: Sort first by `impact_tier` (breakthrough → solid → incremental), then by `total_score`, so the highest-impact work always appears first regardless of pure score arithmetic.
- **Email digest**: Email template renders the new structured fields and groups papers by tier with a section header for each.
- **Backfill path**: Existing cached papers without the new fields render gracefully (badge omitted, contributions section hidden) and a one-shot `paper-agent rescore --missing-fields` CLI re-scores them.
- **BREAKING**: `ScoredPaper` gains required fields; old DB rows are migrated on read (NULL → empty defaults). The `SCORE_TOOL` JSON schema changes — any external consumer of the scoring output must accept the new keys.

## Capabilities

### New Capabilities
- `structured-paper-insights`: Defines the extended scoring schema (`key_contributions`, `problem_statement_zh`, `methods_zh`, `impact_tier`), how the scorer prompts for and validates them, and how legacy papers without these fields are handled.
- `impact-tier-filtering`: Defines the tier query parameter, preferences-panel selector, and default-excluded tier behavior for both `/` and `/_paper_list`.
- `retrieval-quality-floor`: Defines the two-stage arXiv fetch (keyword + recency-prioritized cross-list pull), dedup ordering, and the `fetch.quality_floor_strategy` config knob.

### Modified Capabilities
- `paper-browsing`: Paper card content requirement is extended to render `key_contributions`, `problem_statement_zh`, `methods_zh`, and a tier badge; sort order changes to tier-then-score; tier query parameter is added alongside `sub_domain` and `q`.

## Impact

- **Code**:
  - `src/paper_agent/models.py` — `ScoredPaper` fields, `IMPACT_TIERS` constant, sort helper update
  - `src/paper_agent/scorer/claude_scorer.py` — `SCORE_TOOL` schema, prompts, response validation
  - `src/paper_agent/storage/database.py` — schema migration (add columns, on-read defaults), `list_papers` accepts `tier`/`tiers` filter
  - `src/paper_agent/fetcher/arxiv_fetcher.py` (or equivalent) — two-stage fetch implementation
  - `src/paper_agent/config.py` — `FetchConfig.quality_floor_strategy`
  - `src/paper_agent/pipeline.py` — wire tier into per-user filtering and sort
  - `src/paper_agent/web/routes.py` + `templates/_paper_list.html` + `static/style.css` + `static/preferences.js` — tier UI
  - `src/paper_agent/notifier/email_notifier.py` (template) — tier sections + new fields
  - `src/paper_agent/cli.py` — `rescore --missing-fields` subcommand
- **Database**: `papers` table gains `key_contributions` (JSON text), `problem_statement_zh`, `methods_zh`, `impact_tier` columns. Migration runs on first start (idempotent `ALTER TABLE ... IF NOT EXISTS`-equivalent for SQLite via PRAGMA check).
- **API/Tools**: `SCORE_TOOL` schema gains 4 new required output keys → first scoring run after upgrade will use more tokens per paper (estimate ~30%).
- **Config**: `config.yaml` gains optional `fetch.quality_floor_strategy` and `users[].thresholds.min_tier` keys (both backward-compatible defaults).
- **No breaking change** to webhook payload structure for non-email notifiers — they continue to receive markdown digests, just with richer content.
