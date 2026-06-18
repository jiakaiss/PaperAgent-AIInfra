## Why

The current scorer judges papers from abstract text alone, which biases against work whose value only becomes visible through community uptake. As a result, two failure modes show up in digests:

1. **Hyped-but-shallow papers** with strong abstracts get high `total_score` and crowd out genuinely impactful work.
2. **Older landmark papers and "slow burn" classics** are invisible to subscribers — the pipeline only ever surfaces papers from the last `days_back` window, so a 2023 paper that just hit 2,000 citations and is reshaping practice never lands in anyone's inbox.

Adding citation count as a first-class signal — fetched from a real bibliographic source rather than guessed by the LLM — fixes both. It corrects scoring on recent papers as evidence accrues, and unlocks a new digest mode that occasionally surfaces high-impact older work users almost certainly missed.

## What Changes

- Introduce a `CitationProvider` abstraction with a Semantic Scholar implementation as the default backend.
- Extend the `papers` table with `citation_count`, `influential_citation_count`, and `citations_updated_at` columns; add idempotent migration.
- Periodically refresh citation counts for cached papers (configurable cadence, default daily) so old cache rows can re-rank as evidence accrues.
- **Dynamically re-score papers whose citations have grown significantly**: when a cached paper's citation count rises past a configurable delta/ratio since its last Claude score, the pipeline re-runs the Claude scorer with the current citation counts supplied as context, updating `relevance_score`, `quality_score`, `impact_tier`, and the derived `total_score`. This corrects the LLM's initial judgment as real-world impact evidence accrues — the core of the "评分动态化" requirement. Re-scoring is rate-limited (max N per refresh run, min interval per paper) to bound Claude API cost.
- Incorporate citation signal into per-user ranking via a new `citation_weight` knob in `ScoringConfig` and a normalization scheme that doesn't crush brand-new (0-citation) papers; citation also serves as a same-tier tiebreaker after dynamic re-scoring.
- Add an "Important Older Works" track to the pipeline: a separate fetch path that pulls highly-cited older papers (older than `days_back`) by sub-domain, stores them in the same `papers` table with provenance, and includes 1–2 of them per digest.
- Add a `min_citations_for_older_works` threshold and `older_works_per_digest` count to `ThresholdsConfig`.
- Render citation count + an "📈 Important older work" badge in email digests and the web UI; add a `?older=true` filter on `/_paper_list`.
- Extend admin dashboard with citation-coverage stats (papers with vs without citation data, last refresh timestamp).
- New CLI: `paper-agent refresh-citations [--all | --stale-days N]` for manual backfills.

## Capabilities

### New Capabilities
- `citation-signal`: Citation-count fetching, caching, refresh cadence, and integration into ranking.
- `important-older-works`: Discovery, ingestion, and digest delivery of highly-cited papers older than `days_back`.

### Modified Capabilities
- `structured-paper-insights`: `ScoredPaper` carries citation fields; the scorer's user-message template accepts citation context for dynamic re-scoring; web UI and email templates render citation fields.
- `configurable-scoring-weights`: `ScoringConfig` exposes `citation_weight` alongside `relevance_weight` / `quality_weight`.
- `delivery-volume-control`: `ThresholdsConfig` gains `older_works_per_digest` and `min_citations_for_older_works`; per-user digest splits into "fresh" + "older" sections.
- `paper-browsing`: Web list supports `?older=true` filter and a citation-count column / sort.
- `admin-dashboard`: New panel surfaces citation coverage and last refresh time.

## Impact

- **Code**: `scorer/` (new `citation_provider.py`), `models.py` (ScoredPaper fields, new `paper_kind` enum: `fresh` / `older`), `storage/database.py` (3 new columns + 2 new aggregate methods), `pipeline.py` (older-works track), `fetcher/` (new `older_works_fetcher.py`), `web/routes.py` + admin, `notifier/email_notifier.py` + templates, `cli.py` (new subcommand).
- **External dependencies**: Semantic Scholar Graph API (free, 100 req/min unauthenticated, 1 req/s recommended). No new Python dependency — use `requests` (already pinned).
- **Configuration**: `config.yaml` gains a `citations:` block exposing every operator-tunable knob (provider connection: `provider`, `api_key`, `base_url`, `request_timeout`, `batch_size`, `requests_per_second`; refresh cadence: `refresh_interval_hours`, `refresh_candidate_limit`; tiebreaker shape: `normalization_ceiling`; dynamic re-scoring: `rescore_min_delta`, `rescore_min_ratio`, `rescore_max_per_run`, `rescore_min_interval_days`; older-works track: `older_works_min_age_years`, `older_works_max_age_years`, `older_works_max_new_per_ingest`, `older_works_search_page_size`, `older_works_keywords_per_sub_domain`, `older_works_promote_min_citations`); plus `scoring.citation_weight`; plus `thresholds.older_works_per_digest`, `thresholds.min_citations_for_older_works`. No magic numbers buried in code — every threshold and cap is a config field.
- **Database migration**: Idempotent `ALTER TABLE ADD COLUMN`. Legacy rows: `citation_count = NULL` reads back as `0` for ranking, `citations_updated_at = NULL` means "never fetched, eligible for next refresh batch".
- **API cost**: Citation fetch is free (Semantic Scholar). Unlike the earlier design, dynamic re-scoring DOES trigger Claude API calls — but only for papers whose citations grew past a delta/ratio threshold, capped at N per refresh run with a per-paper min interval, so cost stays bounded. Papers with stable or zero citations are not re-scored.
- **Backward compatibility**: Default `citation_weight = 0.0` and `older_works_per_digest = 0` preserve current behavior bit-for-bit until the operator opts in. **No BREAKING changes** to existing configs.
