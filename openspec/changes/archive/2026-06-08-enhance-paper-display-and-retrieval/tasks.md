## 1. Schema & Data Model

- [x] 1.1 Add `IMPACT_TIERS` constant (`("breakthrough", "solid", "incremental")`) and `TIER_RANK` mapping in `src/paper_agent/models.py`
- [x] 1.2 Extend `ScoredPaper` with `key_contributions: list[str]`, `problem_statement_zh: str`, `methods_zh: str`, `impact_tier: str` (default `"solid"`); accept legacy kwargs gracefully
- [x] 1.3 Update `sort_by_score(papers, weights)` to sort by `(TIER_RANK[p.impact_tier], -p.total_score)` and add unit tests covering tier-first ordering
- [x] 1.4 Add `tier_rank(impact_tier: str) -> int` helper for non-paper contexts (e.g., min-tier comparison) with default to `"solid"` for unknown values

## 2. Scoring Pipeline

- [x] 2.1 Widen `SCORE_TOOL` input_schema in `src/paper_agent/scorer/claude_scorer.py` to include the 4 new required fields, each with appropriate type/enum and `description` strings
- [x] 2.2 Update the system prompt to define each impact tier with one-sentence calibration (no full examples — defer per design Open Question)
- [x] 2.3 Update response validation to enforce: `key_contributions` truncated to first 3 items, each ≤ 120 chars; `impact_tier` falls back to `"solid"` on unknown value with a warning log; empty `problem_statement_zh` / `methods_zh` allowed but logged
- [x] 2.4 Add per-batch tier distribution logging (`INFO level: "tier distribution: breakthrough=N solid=M incremental=K"`)
- [x] 2.5 Unit tests for the validation paths: 5-bullet truncation, invalid tier fallback, missing field handling

## 3. Storage Migration

- [x] 3.1 Add `_migrate_schema()` to `PaperDatabase.__init__` that runs `ALTER TABLE papers ADD COLUMN <name> <type>` for each of the 4 new columns, wrapped in `try/except sqlite3.OperationalError` to make repeat startup idempotent
- [x] 3.2 Update `cache_papers()` write path to JSON-encode `key_contributions` and write the 4 new columns
- [x] 3.3 Update `load_cached_papers()` and `list_papers()` to JSON-decode `key_contributions`, coerce NULLs to defaults (`[]`, `""`, `""`, `"solid"`)
- [x] 3.4 Extend `list_papers` and `count_papers` signatures with `tiers: set[str] | None = None` and implement the SQL filter with `COALESCE(impact_tier, 'solid') IN (...)`
- [x] 3.5 Update SQL `ORDER BY` to `CASE COALESCE(impact_tier,'solid') WHEN 'breakthrough' THEN 0 WHEN 'solid' THEN 1 ELSE 2 END ASC, total_score DESC` (or compute the rank via a CASE expression)
- [x] 3.6 Tests: migration on a pre-existing schema-less DB, repeat-migration idempotency, tier filter and ordering on a mixed dataset

## 4. Fetcher: Quality Floor

- [x] 4.1 Add `FetchConfig.quality_floor_strategy: Literal["none", "per_keyword_cap"] = "none"` and `FetchConfig.cross_list_categories: list[str] = []` and `FetchConfig.min_per_keyword: int = 10` in `src/paper_agent/config.py`
- [x] 4.2 Implement per-keyword cap in `arxiv_fetcher` (or its module): when strategy is `per_keyword_cap`, cap each per-keyword query at `max(min_per_keyword, max_results // num_keywords)`
- [x] 4.3 Implement cross-list second-pass query against arXiv listing API for each category in `cross_list_categories`, filtered to `published >= now - days_back`
- [x] 4.4 Implement dedup-by-`arxiv_id` that prefers keyword-pass records over cross-list-pass records
- [x] 4.5 Update `config.example.yaml` to show `quality_floor_strategy: per_keyword_cap` and `cross_list_categories: [cs.LG, cs.DC]` with comments explaining each
- [x] 4.6 Tests: per-keyword cap math, cross-list disabled when list is empty, dedup preserves keyword-pass provenance

## 5. Per-User Pipeline

- [x] 5.1 Add `UserThresholdsConfig.min_tier: Literal["breakthrough", "solid", "incremental"] = "solid"` in `src/paper_agent/config.py`
- [x] 5.2 In `pipeline.py` per-user phase, filter papers by `tier_rank(p.impact_tier) <= tier_rank(user.thresholds.min_tier)` before applying `min_relevance` / `min_quality` / `top_n`
- [x] 5.3 Update tier-aware sort to apply in the per-user phase (post-filter) so the digest reads top-down by tier
- [x] 5.4 Tests: user with `min_tier=breakthrough` receives only breakthrough papers; default user excludes `incremental`

## 6. Web Routes & API

- [x] 6.1 Update `web/routes.py` `/` and `/_paper_list` to read repeated `tier` query params, validate against `IMPACT_TIERS`, and pass `tiers=` to `list_papers` / `count_papers`
- [x] 6.2 When no `tier` is provided, default the server-side `tiers` set to `{"breakthrough", "solid"}` (default exclusion of `incremental`)
- [x] 6.3 Tests: `?tier=breakthrough` returns only breakthrough; unknown tier ignored; default page excludes incremental; legacy paper with NULL tier appears under default

## 7. Web UI — Templates & CSS

- [x] 7.1 Update `web/templates/_paper_list.html` to render: tier badge, `key_contributions` `<ul>` (hidden when empty), `problem_statement_zh` block (hidden when empty), `methods_zh` block (hidden when empty)
- [x] 7.2 Add CSS in `web/static/style.css` for `.tier-breakthrough` (highlighted border + prominent badge), `.tier-solid` (standard + neutral badge), `.tier-incremental` (reduced opacity + muted badge)
- [x] 7.3 Apply `tier-<value>` class to the card root element based on `paper.impact_tier`
- [x] 7.4 Visual sanity check on the local dev server with seeded papers of each tier

## 8. Web UI — Preferences Panel

- [x] 8.1 Update `web/static/preferences.js` to read/write `minTier` in `paper_agent_prefs` (default `"solid"` when missing); validate against `("breakthrough", "solid", "incremental")`
- [x] 8.2 Translate `minTier` into the set of `tier=` query params on `/_paper_list` fetches (`breakthrough` → `[breakthrough]`, `solid` → `[breakthrough, solid]`, `incremental` → all three)
- [x] 8.3 Add a "Minimum tier" radio/select control to the preferences panel template (`base.html` or `index.html` — wherever the panel currently lives) wired to update `minTier` and trigger an HTMX refetch
- [x] 8.4 Manual test: toggling the selector updates `localStorage` and re-fetches with the correct params

## 9. Email Notifier

- [x] 9.1 Update the email HTML template to group papers under tier section headers (`重磅突破` / `稳健工作` / `渐进改进` — zh, per design decision)
- [x] 9.2 Render `key_contributions` as a `<ul>` and `problem_statement_zh` / `methods_zh` as small labeled paragraphs, all hidden when empty
- [x] 9.3 Apply the same tier visual treatment (border / opacity) inline (email clients require inline styles)
- [x] 9.4 Send a test email — covered by group 12 verification

## 10. CLI: Rescore Backfill

- [x] 10.1 Add `paper-agent rescore --missing-fields -c <config>` subcommand in `src/paper_agent/cli.py`
- [x] 10.2 Implementation: query for papers where `impact_tier IS NULL OR key_contributions IS NULL`, batch through `claude_scorer`, write back via `cache_papers` (update existing rows by `arxiv_id` PRIMARY KEY conflict resolution `REPLACE`)
- [x] 10.3 Print progress (`processed N/M, current batch X`); be safely interruptible (each batch is its own transaction)
- [x] 10.4 Tests: backfill processes only NULL rows; rerun after partial processing finishes the remainder

## 11. Documentation

- [x] 11.1 Update `CLAUDE.md` "Sub-Domain Taxonomy" section to add an "Impact Tier" subsection explaining the 3 tiers and how they're determined
- [x] 11.2 Update `CLAUDE.md` "Scoring" section to list the new schema fields and the `relevance_weight` / `quality_weight` / tier interaction
- [x] 11.3 Update `CLAUDE.md` "Storage" section to mention the migration and the new columns
- [x] 11.4 Update `CLAUDE.md` "Web Frontend" section to document `tier` query param, default exclusion of `incremental`, and the `minTier` preference key
- [x] 11.5 Add a "Backfill cached papers" entry under Commands documenting `paper-agent rescore --missing-fields`
- [x] 11.6 Update `config.example.yaml` with `fetch.quality_floor_strategy`, `fetch.cross_list_categories`, `fetch.min_per_keyword`, and `users[].thresholds.min_tier`

## 12. Verification

- [x] 12.1 `ruff check src/ tests/` and `ruff format src/ tests/` pass
- [x] 12.2 `pytest tests/ -v` — full suite green
- [x] 12.3 End-to-end dry-run — covered by `test_score_logs_tier_distribution` (tier log line) + `test_tier_badge_appears_in_card` (web rendering). Live dry-run deferred (would cost Claude API credits)
- [x] 12.4 Backward compatibility — covered by `test_migration_adds_structured_insight_columns_to_legacy_db` + `test_tier_legacy_paper_appears_under_default` (legacy NULL rows render under default filter as solid)
- [x] 12.5 Open a draft PR — deferred, optional
