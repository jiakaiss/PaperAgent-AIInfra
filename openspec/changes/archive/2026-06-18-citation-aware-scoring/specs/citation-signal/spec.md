## ADDED Requirements

### Requirement: Citation provider abstraction

The system SHALL define a `CitationProvider` protocol with a method `get_citations(arxiv_ids: list[str]) -> dict[str, CitationInfo]` where `CitationInfo` carries `citation_count: int` and `influential_citation_count: int`. The system SHALL ship a `SemanticScholarCitationProvider` implementation as the default backend. Lookup SHALL be performed by `ArXivId` using the Semantic Scholar Graph API endpoint `GET /graph/v1/paper/ArXivID:{id}` with fields `citationCount,influentialCitationCount`. Provider construction SHALL read connection settings from a new `CitationsConfig` block.

#### Scenario: Lookup returns citation counts
- **WHEN** the provider is queried with `["2401.12345"]`
- **THEN** the returned dict contains an entry whose `citation_count` and `influential_citation_count` match the live Semantic Scholar response for that arXiv ID

#### Scenario: Unknown paper returns no entry
- **WHEN** the provider is queried with an arXiv ID that Semantic Scholar has never indexed
- **THEN** the returned dict does not contain an entry for that ID (no exception is raised)

#### Scenario: Provider is swappable
- **WHEN** `citations.provider` is set to a non-default value
- **THEN** the system constructs the configured provider instead of `SemanticScholarCitationProvider`, with the default remaining `SemanticScholarCitationProvider` when unset

### Requirement: Citations configuration block

`AppConfig` SHALL accept a top-level `citations` section with fields: `enabled` (bool, default `false`), `provider` (string, default `"semantic_scholar"`), `api_key` (string|None, supports `${ENV_VAR}` interpolation), `base_url` (string, default the Semantic Scholar public endpoint), `refresh_interval_hours` (int, default `24`), `request_timeout` (float, default `15.0`), `batch_size` (int, default `50`), `requests_per_second` (float, default `1.0`), `refresh_candidate_limit` (int, default `500` — max stale papers selected per refresh tick before batching to the provider), `normalization_ceiling` (int, default `1000` — citation count that maps to the top of the 0–10 tiebreaker scale), `rescore_min_delta` (int, default `50`), `rescore_min_ratio` (float, default `0.2`), `rescore_max_per_run` (int, default `20`), `rescore_min_interval_days` (int, default `7`), `older_works_min_age_years` (int, default `2` — papers must be at least this many years old to be eligible for the older-works track), `older_works_max_age_years` (int, default `10` — papers older than this are excluded so 1990s/2000s academic classics don't dominate), `older_works_max_new_per_ingest` (int, default `20` — cap on newly-discovered older papers scored per ingest cycle, bounding one-time Claude cost on first enable), `older_works_search_page_size` (int, default `20` — how many candidates each per-keyword S2 search returns), `older_works_keywords_per_sub_domain` (int, default `3` — how many keyword variants from `models.SUB_DOMAINS` are queried per sub-domain), and `older_works_promote_min_citations` (int, default `500` — citation threshold above which an already-cached `paper_kind="fresh"` row is auto-promoted to `"older"`; held intentionally HIGHER than `min_citations_for_older_works` because promotion is a stronger claim than discovery). The validator SHALL reject configurations where `older_works_max_age_years < older_works_min_age_years` (an empty window). When `citations.enabled` is `false`, no citation fetching, dynamic re-scoring, ranking integration, or older-works discovery SHALL occur — the pipeline behaves exactly as before this change.

#### Scenario: Disabled by default
- **WHEN** `config.yaml` omits the `citations` section
- **THEN** `AppConfig.citations.enabled` is `false` and the pipeline performs no citation-related work

#### Scenario: API key from environment variable
- **WHEN** `citations.api_key` is set to `${S2_API_KEY}` and the env var holds a key
- **THEN** the provider sends that key as the `x-api-key` header on every request

#### Scenario: Invalid refresh interval rejected
- **WHEN** `citations.refresh_interval_hours` is set to a non-positive value
- **THEN** configuration validation rejects the setting with a clear error

#### Scenario: Rescore knobs default to bounded re-scoring
- **WHEN** `config.yaml` enables citations but omits the rescore fields
- **THEN** `rescore_min_delta=50`, `rescore_min_ratio=0.2`, `rescore_max_per_run=20`, `rescore_min_interval_days=7` apply

#### Scenario: Older-works knobs default to bounded discovery
- **WHEN** `config.yaml` enables citations but omits the older-works knobs
- **THEN** `older_works_min_age_years=2`, `older_works_max_age_years=10`, `older_works_max_new_per_ingest=20`, `older_works_search_page_size=20`, `older_works_keywords_per_sub_domain=3`, and `older_works_promote_min_citations=500` apply

#### Scenario: Empty age window rejected
- **WHEN** `config.yaml` sets `older_works_max_age_years` smaller than `older_works_min_age_years`
- **THEN** configuration validation rejects the setting with a clear error message naming the offending field

#### Scenario: Tiebreaker ceiling defaults to 1000
- **WHEN** `config.yaml` enables citations but omits `normalization_ceiling`
- **THEN** the citation tiebreaker maps `citation_count=1000` to the top of the 0–10 scale; raising or lowering the ceiling proportionally compresses or expands the citation effect on tied papers

#### Scenario: Refresh candidate limit caps work per tick
- **WHEN** 800 papers have stale citations and `refresh_candidate_limit=500`
- **THEN** at most 500 are queried this tick; the remaining 300 are picked up on the next tick

### Requirement: Citation columns migration

`PaperDatabase` SHALL add `citation_count` (INTEGER, nullable), `influential_citation_count` (INTEGER, nullable), `citations_updated_at` (TEXT, nullable ISO timestamp), `paper_kind` (TEXT, default `"fresh"`), and `citation_count_at_score` (INTEGER, nullable — snapshot of `citation_count` captured at the paper's last Claude score, used to detect growth for dynamic re-scoring) columns to the `papers` table on startup via idempotent `ALTER TABLE` statements guarded by `PRAGMA table_info`. Reads of legacy rows where citation columns are NULL SHALL return `citation_count=0`, `influential_citation_count=0`, `citations_updated_at=None`, and `citation_count_at_score=None` (treated as 0 for growth math). The `paper_kind` column SHALL hold `"fresh"` for papers fetched from the normal `days_back` window and `"older"` for papers surfaced by the older-works track. `citation_count_at_score` SHALL be written on every score (first-score and re-score) to the then-current `citation_count`.

#### Scenario: Upgrade preserves existing rows
- **WHEN** the daemon starts against a database with 500 papers scored before this change
- **THEN** the 5 new columns are added, no row is deleted or rewritten, and `list_papers()` returns the 500 papers with `citation_count=0`, `paper_kind="fresh"`, `citations_updated_at=None`, and `citation_count_at_score=None`

#### Scenario: Repeat startup is idempotent
- **WHEN** the daemon starts a second time after the migration ran
- **THEN** the `ALTER TABLE` calls produce no error and no schema change

### Requirement: Periodic citation refresh

When `citations.enabled` is `true`, the daemon SHALL register a scheduled job that refreshes citation counts for cached papers at `citations.refresh_interval_hours` cadence. The refresh job SHALL select papers whose `citations_updated_at` is NULL OR older than `citations.refresh_interval_hours`, fetch citations in batches of `citations.batch_size` respecting `citations.requests_per_second` rate limiting, and update `citation_count`, `influential_citation_count`, and `citations_updated_at` in place. After writing fresh counts, the job SHALL invoke the dynamic re-scoring step (see "Dynamic re-scoring on citation growth") for papers whose citation growth meets the re-score threshold. The citation-fetch step itself SHALL NOT call Claude — only the subsequent re-scoring step does, and only for eligible papers. A run SHALL be safe to interrupt and resume on the next tick (only un-refreshed-or-stale rows are selected for fetch; only growth-eligible rows are selected for re-score).

#### Scenario: Stale papers refreshed
- **WHEN** the refresh job runs and 30 cached papers have `citations_updated_at` older than `refresh_interval_hours` (or NULL)
- **THEN** exactly those 30 papers' citation columns are updated with fresh values and a current `citations_updated_at` timestamp

#### Scenario: Recently refreshed papers skipped
- **WHEN** the refresh job runs and 10 papers were refreshed 2 hours ago with `refresh_interval_hours=24`
- **THEN** those 10 papers are not re-queried for citations

#### Scenario: Resumable after interruption
- **WHEN** a refresh run is interrupted after updating 15 of 30 stale papers
- **THEN** the next run selects the 15 remaining stale papers (not all 30)

#### Scenario: Citation fetch does not call Claude
- **WHEN** the refresh job fetches citation counts for 30 papers and none meet the re-score growth threshold
- **THEN** no Claude API scoring call is made during this run

### Requirement: Citation refresh CLI command

The CLI SHALL expose `paper-agent refresh-citations -c <config>` accepting `--all` (refresh every cached paper regardless of staleness) or `--stale-days N` (refresh papers whose `citations_updated_at` is NULL or older than N days). When neither flag is given, the command SHALL refresh papers stale by `citations.refresh_interval_hours`. The command SHALL require `citations.enabled=true` and exit with a clear error otherwise.

#### Scenario: Refresh all
- **WHEN** the operator runs `paper-agent refresh-citations --all`
- **THEN** every cached paper's citation columns are re-queried and updated

#### Scenario: Disabled citations rejected
- **WHEN** the operator runs `paper-agent refresh-citations` with `citations.enabled=false`
- **THEN** the command exits non-zero with a message instructing the operator to enable citations in config

#### Scenario: Stale-days filter
- **WHEN** the operator runs `paper-agent refresh-citations --stale-days 7`
- **THEN** only papers with `citations_updated_at` NULL or older than 7 days are refreshed

### Requirement: Dynamic re-scoring on citation growth

When `citations.enabled` is `true`, the citation refresh job SHALL — after writing fresh citation counts — select cached papers whose citation count has grown past a re-scoring threshold and re-run the Claude scorer on them with the current citation counts supplied as input context. Re-scoring SHALL update `relevance_score`, `quality_score`, `summary_zh`, `sub_domain_tags`, `key_contributions`, `problem_statement_zh`, `methods_zh`, `impact_tier`, and `scored_at` in the existing `papers` row (in place, not a new row); `total_score` is recomputed from the refreshed `relevance`/`quality`. A paper SHALL be eligible for re-scoring only when ALL of:

- `citation_count_now - citation_count_at_last_score >= citations.rescore_min_delta` (default `50`) OR the relative growth `>= citations.rescore_min_ratio` (default `0.2`)
- the paper was last scored more than `citations.rescore_min_interval_days` (default `7`) ago

At most `citations.rescore_max_per_run` (default `20`) papers SHALL be re-scored per refresh tick, selected by largest absolute citation growth first. Papers not selected (over the cap) remain eligible for the next tick. When `rescore_max_per_run` is `0`, dynamic re-scoring is fully disabled (citation data is still fetched and stored, but no Claude re-score runs).

#### Scenario: Citation growth triggers re-score
- **WHEN** a paper was scored with `citation_count=10` and is now `citation_count=80` (delta 70 ≥ `rescore_min_delta=50`), last scored 10 days ago
- **THEN** the refresh job re-scores it with Claude, supplying `citation_count=80` as context, and updates its `impact_tier`, `relevance_score`, `quality_score`, and `scored_at`

#### Scenario: Small growth does not trigger re-score
- **WHEN** a paper's citations grew from 100 to 110 (delta 10 < 50, ratio 0.1 < 0.2)
- **THEN** the paper is NOT re-scored (its citation columns are still updated)

#### Scenario: Per-run cap respected
- **WHEN** 35 papers meet the growth threshold and `rescore_max_per_run=20`
- **THEN** only the 20 with the largest absolute citation growth are re-scored this tick; the other 15 are re-scored on subsequent ticks (assuming they remain eligible)

#### Scenario: Min interval prevents hot-paper churn
- **WHEN** a paper was re-scored 2 days ago and its citations grew again past the threshold, with `rescore_min_interval_days=7`
- **THEN** the paper is NOT re-scored again this tick

#### Scenario: Zero cap disables re-scoring
- **WHEN** `citations.rescore_max_per_run=0`
- **THEN** no Claude re-scoring runs, but citation counts are still fetched and written to the cache

#### Scenario: Re-score updates total_score indirectly
- **WHEN** a re-scored paper's Claude output changes `relevance` from 7 to 8 and `quality` from 6 to 7 (default weights 0.6/0.4)
- **THEN** its `total_score` changes from `7*0.6+6*0.4=6.6` to `8*0.6+7*0.4=7.6` without any change to the `total_score` formula

#### Scenario: Disabled citations skips re-scoring
- **WHEN** `citations.enabled=false`
- **THEN** no citation refresh and no dynamic re-scoring occurs; all scores are stable at their original Claude values

### Requirement: Auto-promote fresh papers to older on citation growth

When dynamic re-scoring runs, the system SHALL inspect each candidate's `citation_count` and `published` date and, in the same write that updates the scored fields, flip `paper_kind` from `"fresh"` to `"older"` if BOTH of the following hold:

- `citation_count >= citations.older_works_promote_min_citations` (default `500`)
- The paper was published at least `citations.older_works_min_age_years` (default `2`) years ago

This is the natural-emergence path for older works: a paper that was fetched fresh from arXiv and quietly accumulated citations becomes eligible for the older-works section without any manual seeding. Papers that already have `paper_kind="older"` SHALL be left as-is (idempotent). Papers that meet the citation threshold but are too young SHALL stay `"fresh"` — recent viral hits are not retroactively classified as classics.

#### Scenario: Aged high-citation paper auto-promoted
- **WHEN** a 3-year-old `paper_kind="fresh"` paper crosses `citation_count=500` and meets the rescore growth threshold
- **THEN** the rescore write flips its `paper_kind` to `"older"` and Claude's new tier judgment is also applied

#### Scenario: Too-young paper not auto-promoted
- **WHEN** a 6-month-old paper crosses `citation_count=1000` (well above promote threshold) and triggers a rescore
- **THEN** Claude's new tier is applied but `paper_kind` stays `"fresh"` because the age requirement is not met

#### Scenario: Already-older paper untouched
- **WHEN** a `paper_kind="older"` paper meets all promotion conditions
- **THEN** rescore proceeds normally and `paper_kind` remains `"older"` (no flip back to fresh, no double-marking)

### Requirement: Citation-aware ranking

When `citations.enabled` is `true` and `scoring.citation_weight` is greater than `0.0`, per-user paper sorting SHALL incorporate a citation signal so that papers with higher (normalized) citation counts rank higher within the same `impact_tier`. The citation signal SHALL be normalized to a 0–10 scale using a log transform that prevents a single 5000-citation paper from saturating the scale and that leaves a 0-citation (brand-new) paper at a neutral score rather than a penalizing zero. The normalization SHALL be monotonic non-decreasing in raw citation count. When `citation_weight` is `0.0` (the default), ranking SHALL be identical to pre-change behavior (tier-then-total_score), preserving backward compatibility bit-for-bit.

#### Scenario: Zero citation weight preserves old ranking
- **WHEN** `citations.enabled=true` but `scoring.citation_weight=0.0`
- **THEN** per-user sort order is identical to the pre-change tier-then-total_score ordering

#### Scenario: Higher citations rank higher within same tier
- **WHEN** two `solid`-tier papers have equal `total_score` but paper A has `citation_count=200` and paper B has `citation_count=5`, with `citation_weight > 0`
- **THEN** paper A appears before paper B in the sorted digest

#### Scenario: Tier still dominates citation
- **WHEN** paper A is `breakthrough` with 0 citations and paper B is `solid` with 5000 citations, with `citation_weight > 0`
- **THEN** paper A (breakthrough) still appears before paper B (solid)

#### Scenario: Brand-new paper not penalized to bottom
- **WHEN** a brand-new paper has `citation_count=0` and `citation_weight=0.3`, compared with a peer of equal `total_score` and 0 citations
- **THEN** both papers receive the same citation component (no zero-penalty gap between equal-citation papers)

#### Scenario: Disabled citations skips integration
- **WHEN** `citations.enabled=false`
- **THEN** the citation component is not computed and ranking is identical to pre-change behavior regardless of `citation_weight`
