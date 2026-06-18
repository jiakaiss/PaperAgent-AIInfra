## 1. Configuration & models

- [x] 1.1 Add `CitationsConfig` to `config.py` with every operator-tunable knob (no magic numbers in code). Fields: `enabled` default false, `provider` default `"semantic_scholar"`, `api_key` with `${ENV_VAR}` interpolation, `base_url`, `refresh_interval_hours` default 24, `refresh_candidate_limit` default 500, `request_timeout` default 15.0, `batch_size` default 50, `requests_per_second` default 1.0, `normalization_ceiling` default 1000, `rescore_min_delta` default 50, `rescore_min_ratio` default 0.2, `rescore_max_per_run` default 20, `rescore_min_interval_days` default 7, `older_works_min_age_years` default 2, `older_works_max_new_per_ingest` default 20. Validate `refresh_interval_hours > 0`, `normalization_ceiling > 0`, `older_works_min_age_years >= 0`, all `rescore_*` non-negative.
- [x] 1.2 Add `citations: CitationsConfig` to `AppConfig`.
- [x] 1.3 Add `citation_weight: float = 0.0` to `ScoringConfig`; extend the weight-sum validator to warn when `relevance_weight + quality_weight + citation_weight` ≠ 1.0 (±0.01).
- [x] 1.4 Extend `ScoreWeights` dataclass with `citation: float = 0.0`; update `ScoreWeights.from_scoring_config()` to read `citation_weight`.
- [x] 1.5 Add `older_works_per_digest: int = 0` and `min_citations_for_older_works: int = 100` to `ThresholdsConfig`; thread them through `UserThresholdsConfig` inheritance (match existing `min_tier` pattern).
- [x] 1.6 Add `citation_count`, `influential_citation_count`, `citations_updated_at`, `paper_kind` fields to `ScoredPaper` in `models.py` with defaults (`0`, `0`, `None`, `"fresh"`). Add a `PaperKind` Literal type.
- [x] 1.7 Update `config.example.yaml` with commented-out `citations:` block (including the four `rescore_*` knobs), `scoring.citation_weight`, and the two new `thresholds` fields.

## 2. Storage migration & queries

- [x] 2.1 In `storage/database.py`, add idempotent `ALTER TABLE papers ADD COLUMN` for `citation_count INTEGER`, `influential_citation_count INTEGER`, `citations_updated_at TEXT`, `paper_kind TEXT DEFAULT 'fresh'`, and `citation_count_at_score INTEGER` (snapshot for growth detection), guarded by `PRAGMA table_info` (mirror the structured-insights migration).
- [x] 2.2 Update `cache_papers()` to write the 4 new columns; update the row-read mapping so NULL citation columns → `0`/`0`/`None` and NULL `paper_kind` → `"fresh"`.
- [x] 2.3 Add `get_stale_citations(limit, stale_after_hours) -> list[tuple[arxiv_id, ...]]` and `update_citations(updates: list[(arxiv_id, citation_count, influential_count, updated_at)])` to `PaperDatabase`.
- [x] 2.4 Add `get_rescore_candidates(min_delta, min_ratio, min_interval_days, limit) -> list[ScoredPaper]` selecting papers whose citation growth since `scored_at` meets the delta OR ratio threshold AND whose last score is older than `min_interval_days`, ordered by absolute citation growth DESC. Also add `get_citation_at_score(arxiv_id)` or carry the prior citation count so growth is computable (store last-scored citation count, or compute from a snapshot column — confirm approach during impl).
- [x] 2.5 Add `list_papers_missing_citations(limit, offset)` / `count_papers_missing_citations()` for the CLI backfill path.
- [x] 2.6 Extend `list_papers()` / `count_papers()` to accept `paper_kind: Literal["fresh","older"]|None` and `older: str|None` (only/include/exclude) filter; update the SQL `WHERE` clause accordingly. Keep default behavior (both kinds returned) so existing callers/tests pass.
- [x] 2.7 Add `get_citation_coverage()` aggregate: returns `(total, refreshed_count, with_citations_count, last_refresh_at)` for the admin panel.

## 3. Citation provider

- [x] 3.1 Create `scorer/citation_provider.py` with a `CitationProvider` Protocol (`get_citations(arxiv_ids) -> dict[str, CitationInfo]`) and a `CitationInfo` dataclass (`citation_count`, `influential_citation_count`).
- [x] 3.2 Implement `SemanticScholarCitationProvider`: use the batch endpoint `POST /graph/v1/paper/batch` (or per-`ArXivID:{id}` lookups) with `fields=citationCount,influentialCitationCount`; send `x-api-key` header when `api_key` set; honor `request_timeout` and `requests_per_second` (sleep between batches); raise/return gracefully on HTTP errors (log + skip, never crash caller).
- [x] 3.3 Add a factory `create_citation_provider(config: CitationsConfig) -> CitationProvider | None` returning `None` when `enabled=false`.
- [x] 3.4 Unit-test the provider against a stubbed HTTP layer (mock `requests`): verify citation parse, missing-paper handling, rate-limit sleep, and api-key header injection.

## 4. Citation refresh job & CLI

- [x] 4.1 Create a `refresh_citations(db, provider, config) -> RefreshResult` function (in `pipeline.py` or a new `citation_refresh.py`) that selects up to `citations.refresh_candidate_limit` stale papers, batches them through the provider, and calls `db.update_citations()`. Safe to interrupt/resume (only stale rows selected). The candidate limit MUST come from config — no hardcoded literal.
- [x] 4.2 Register the refresh as an `apscheduler` job in `scheduler.py` / daemon setup at `citations.refresh_interval_hours` cadence, only when `citations.enabled`. Log start/finish and counts.
- [x] 4.3 Add `paper-agent refresh-citations [--all|--stale-days N] -c <config>` subcommand in `cli.py`. Reject with a clear error when `citations.enabled=false`. Default (no flag) uses `refresh_interval_hours`.
- [x] 4.4 Test: refresh updates only stale rows, skips fresh ones, resumable after interruption.

## 4b. Dynamic re-scoring on citation growth

- [x] 4b.1 Add a `citation_count_at_score` snapshot column (or equivalent) to the `papers` table migration so citation growth since last score is computable; write it in `cache_papers()` and update it on each re-score. (Confirm: store snapshot column vs. recompute from `citations_updated_at` history — snapshot column is simplest.)
- [x] 4b.2 Add `PaperDatabase.get_rescore_candidates(min_delta, min_ratio, min_interval_days, limit) -> list[ScoredPaper]`: SELECT papers where `(citation_count - citation_count_at_score) >= min_delta` OR `(citation_count - citation_count_at_score) / max(1, citation_count_at_score) >= min_ratio`, AND `scored_at < now - min_interval_days`, ORDER BY `(citation_count - citation_count_at_score)` DESC, LIMIT `limit`.
- [x] 4b.3 Extend the scorer's user-message rendering to accept optional per-paper citation context (`citation_count`, `influential_citation_count`); render a context line only when the values are present and `> 0`. Keep the `SCORE_TOOL` output schema unchanged. First-score path passes no context (identical to pre-change message).
- [x] 4b.4 After `refresh_citations()` writes fresh counts, run `rescore_dynamic(db, scorer, config)`: fetch up to `rescore_max_per_run` candidates, re-score each via `score_papers()` with citation context, write back all scored fields + `scored_at` + `citation_count_at_score=citation_count_now` in place. Log count re-scored.
- [x] 4b.5 Gate: skip re-scoring entirely when `rescore_max_per_run == 0` or `citations.enabled == false`.
- [x] 4b.6 Wire `rescore_dynamic` into the refresh job (runs right after `update_citations`) and into the `refresh-citations` CLI (after the refresh step).
- [x] 4b.7 Tests: growth-past-threshold triggers re-score and updates tier/score/scored_at; small growth skipped; per-run cap respected (largest-growth first); min-interval skips recently scored; `rescore_max_per_run=0` disables; `citations.enabled=false` skips; total_score recomputed from refreshed relevance/quality (formula unchanged); re-score message includes citation context, first-score message does not.

## 5. Citation-aware ranking

- [x] 5.1 Keep `compute_total_score()` as `relevance*w_r + quality*w_q` (citation NOT folded in) — verify the spec's "citation weight does not inflate total_score" scenario holds.
- [x] 5.2 Add `citation_component(paper, ceiling) -> float` = `10 * log10(1+citation_count) / log10(1+ceiling)`; monotonic, 0 for 0 citations, equal for equal counts. The `ceiling` argument MUST be sourced from `citations.normalization_ceiling` (no hardcoded literal in the function body or its callers).
- [x] 5.3 Update `sort_by_score()` to sort by `(tier_rank ASC, total_score DESC, citation_component DESC)` when `weights.citation > 0` and citations enabled; otherwise current `(tier_rank, total_score)`.
- [x] 5.4 Wire the pipeline's per-user sort to pass `ScoreWeights` (already does) and the `citations.enabled` flag so the citation key activates only when both `enabled` and `citation_weight>0`.
- [x] 5.5 Tests: zero-weight preserves old order; higher citations win equal-tier/equal-score ties; tier still dominates; brand-new paper not penalized below an equal-citation peer; disabled-citations skips integration.

## 6. Older-works discovery

- [x] 6.1 Create `fetcher/older_works_fetcher.py` with `discover_older_works(provider, sub_domains, config) -> list[ArXivPaper-ish]` querying `GET /graph/v1/paper/search` (fieldsOfStudy=CS, sub-domain keyword, `citationCount >= min_citations_for_older_works`, year `< current_year - citations.older_works_min_age_years`). Skip results without an `arxiv_id`. The age cutoff and citation threshold MUST come from config — no hardcoded literals.
- [x] 6.2 In the pipeline ingest phase, when `older_works_per_digest > 0` and `citations.enabled`, run the older-works track: dedup discovered papers against the cache (skip cached; optionally flip `paper_kind` to `"older"`), score the new ones via the existing `score_papers()` path, and `cache_papers()` with `paper_kind="older"`. Cap new older scores per ingest at `citations.older_works_max_new_per_ingest`.
- [x] 6.3 Tests: discovers + caches older paper; skips non-arXiv; skips cached; respects min_citations; respects `older_works_min_age_years` cutoff; respects `older_works_max_new_per_ingest` cap; verify both knobs are wired through config (changing the config value changes behavior, not a hardcoded literal).

## 7. Digest delivery of older works

- [x] 7.1 In the per-user digest path, when `older_works_per_digest > 0`, select up to N older papers (`paper_kind="older"`) matching the user's sub-domains and global `min_tier`, deduped against `sent_papers` for that user, ranked (tier-then-score-then-citation).
- [x] 7.2 Deliver older works in a distinct "重要老作 / Important Older Works" section, additive to `top_n` (do not subtract from the fresh budget).
- [x] 7.3 `mark_sent()` the delivered older works for the user so they aren't re-sent.
- [x] 7.4 Update email HTML template (`formatter/templates.py`) to render the older-works section with a distinct heading and per-paper citation count; keep the dual-font (`Times New Roman` / `Microsoft YaHei`) styling.
- [x] 7.5 Tests: older section included with correct count; not double-sent across runs; additive to top_n; disabled when count is 0.

## 8. Web UI

- [x] 8.1 Accept `?older=only|include|exclude` on `/` and `/_paper_list` in `web/routes.py`; pass through to `list_papers(paper_kind=...)`. Default `include`. Invalid values treated as `include`.
- [x] 8.2 Render a citation badge ("📈 N citations") on the paper card in `_paper_list.html` when `citation_count > 0`; render "🔖 重要老作" badge when `paper_kind == "older"`. Hide both when not applicable.
- [x] 8.3 Add an "older works" filter toggle to the preferences UI (`preferences.js` + panel) syncing to `localStorage` and the `?older=` param (mirror the existing chip-filter pattern).
- [x] 8.4 Tests: `?older=only` returns only older; `exclude` returns only fresh; default returns both; invalid value ignored; card renders citation/older badges correctly; legacy 0-citation fresh paper shows neither badge.

## 9. Admin dashboard

- [x] 9.1 Add a citation-coverage sub-section to `GET /admin/_papers` using `db.get_citation_coverage()`: render "X / Y (Z%) 已采集引用数", count with `citation_count>0`, last refresh timestamp, and provider/interval summary. When disabled, render the single "引用数采集未启用" line.
- [x] 9.2 Add `citations.api_key` to the sentinel-secret list in `test_admin.py::TestSecrets` so the existing parameterized test covers the new secret; verify it never renders on any admin route.
- [x] 9.3 Tests: coverage shown when enabled; disabled-state message; never-refreshed placeholder renders `—`.

## 10. Docs & cross-cutting

- [x] 10.1 Update `CLAUDE.md`: new `citations` config block, `paper_kind`/citation columns in the storage section, the citation-as-tiebreaker ranking note (tier still dominates), and the older-works track in the pipeline flow description.
- [x] 10.2 Update `README.md` feature list and config docs with `citations`, `citation_weight`, `older_works_per_digest`, `min_citations_for_older_works`, and the `refresh-citations` CLI.
- [x] 10.3 Update `docs/user-guide.md` with operator guidance for enabling citations and the older-works section.
- [x] 10.4 Run `ruff check src/ tests/` and `ruff format src/ tests/`; run `pytest tests/ -v` and ensure all existing + new tests pass.

## 11. Older-works discovery quality (post-deploy follow-ups)

Surfaced after the first real-world ingest run revealed gaps in the v1
discovery path: candidates were sparse, citations could be silently lost,
and some classics couldn't surface because they were already cached as
fresh. This section closes those gaps.

- [x] 11.1 Sort S2 search results by `citationCount:desc` so the citation floor doesn't waste a page on low-citation noise. Without this, S2's default relevance sort returned mostly low-citation recent work that got filtered out, leaving 1-2 results per sub-domain.
- [x] 11.2 Promote `older_works_search_page_size` (was hardcoded `20`) to `CitationsConfig` so operators can widen the funnel when they raise the citation floor.
- [x] 11.3 Add `older_works_keywords_per_sub_domain` (default `3`) and query S2 once per keyword variant from `models.SUB_DOMAINS[sd]` so synonyms (e.g. "speculative decoding" / "draft model" / "assisted generation") all contribute candidates. Fall back to the bare sub-domain name when the dict has no entry.
- [x] 11.4 Carry `(citation_count, influential_citation_count)` forward from the S2 search response through `discover_older_works` (return signature is now `(papers, source_map, citation_map)`); use it directly as `citation_context` for the scorer instead of issuing a second S2 batch call. The redundant call was racy under rate-limit and silently produced 0-citation older works in production.
- [x] 11.5 Stamp the originating sub-domain in a `source_map` during discovery, then merge it into `sub_domain_tags` after scoring. Without this, a paper found via the "quantization" search but tagged "compiler" by the LLM would be invisible to quantization subscribers.
- [x] 11.6 Add `older_works_promote_min_citations` (default `500`, intentionally above the discovery floor) and `_promote_cached_to_older` SQL UPDATE path: when S2 surfaces a paper that's already in the cache as `paper_kind="fresh"` and meets the threshold, flip its `paper_kind` to `"older"` in place — preserving every other column. Without this, the long-running deployments would have their best classics stuck in fresh and invisible.
- [x] 11.7 In `rescore_dynamic`, also auto-promote: when re-scoring a `paper_kind="fresh"` paper whose `citation_count >= older_works_promote_min_citations` AND whose published date is at least `older_works_min_age_years` old, flip `paper_kind="older"` in the same write. Recent viral hits stay fresh because the age check fails.
- [x] 11.8 Tests: search uses `citationCount:desc`; page size is config-driven; multiple keyword variants per sub-domain (with fallback for unknown sub-domains); `citation_map` is non-empty when search returns data; source sub-domain ends up in `sub_domain_tags`; cached fresh paper above promote threshold is flipped; rescore-driven auto-promotion respects citation AND age thresholds; already-`older` papers are idempotent through both paths.
