# important-older-works Specification

## Purpose

Surface highly-cited "classic" papers from prior years (2–10 years old by default) into per-user digests as a distinct "Important Older Works" section, so subscribers see canonical foundations of their sub-domains alongside fresh arXiv output. Older works are discovered via a dedicated Semantic Scholar search track, scored once with Claude, marked `paper_kind="older"`, and delivered additively to the normal `top_n` fresh-paper budget. The track is opt-in (gated by `thresholds.older_works_per_digest > 0` and `citations.enabled=true`).

## Requirements

### Requirement: Older-works discovery

When `citations.enabled` is `true` and `thresholds.older_works_per_digest` is greater than `0`, the pipeline SHALL run an additional fetch track that discovers highly-cited papers in the year window `[current_year - older_works_max_age_years, current_year - older_works_min_age_years]` (inclusive on both ends, defaults `[current_year - 10, current_year - 2]`). Each subscribed sub-domain queries the Semantic Scholar search endpoint `GET /graph/v1/paper/search` once per keyword variant, drawing the variants from `models.SUB_DOMAINS[sub_domain]` and capping at `citations.older_works_keywords_per_sub_domain` (default `3`); a sub-domain not present in `SUB_DOMAINS` falls back to a single query using the underscore-stripped sub-domain name. Each search SHALL pass `fieldsOfStudy=Computer Science`, the year range as `year=YYYY-YYYY`, `sort=citationCount:desc`, and `limit=citations.older_works_search_page_size` (default `20`). Sorting by citation count is required because S2's default relevance ranking interleaves low-citation recent work that subsequent filtering removes, leaving sparse results.

For each returned paper the system SHALL: (a) drop entries whose `citationCount < thresholds.min_citations_for_older_works`; (b) skip entries with no arXiv ID (the cache is arXiv-keyed) or with a missing title or abstract; (c) deduplicate by `arxiv_id` across keyword variants and across sub-domains. Discovery SHALL return three values together: the deduped `Paper` list, a `source_map` mapping each surviving `arxiv_id` to the FIRST sub-domain whose search surfaced it, and a `citation_map` mapping each surviving `arxiv_id` to its `(citation_count, influential_citation_count)` from the search response. The pipeline SHALL feed `citation_map` directly into the scorer's `citation_context` rather than issuing a second S2 round-trip — the redundant lookup was racy under rate-limit and silently wrote `citation_count=0` rows in production.

Among deduped candidates, the system SHALL split into two paths:

- **Already-cached candidates** SHALL trigger an in-place `paper_kind="fresh" → "older"` flip via SQL UPDATE for any row whose stored `citation_count >= citations.older_works_promote_min_citations` (default `500`, intentionally above the discovery floor because promotion is a stronger claim). Existing scores, summaries, and the `citation_count_at_score` snapshot SHALL be preserved — only `paper_kind` is touched.

- **Brand-new candidates** SHALL be capped at `citations.older_works_max_new_per_ingest`, scored by Claude with `citation_context` populated from `citation_map` (so the LLM judges with real-world impact evidence visible in the prompt), then cached with `paper_kind="older"`. After scoring, each paper's `sub_domain_tags` SHALL be merged with `{source_map[arxiv_id]}` so the originating sub-domain is force-tagged — without this merge, a paper found via the "quantization" search but tagged "compiler" by the LLM would be invisible to quantization subscribers.

#### Scenario: Discovers older highly-cited paper
- **WHEN** the older-works track runs for the `quantization` sub-domain with `min_citations_for_older_works=100` and `older_works_min_age_years=2`
- **THEN** a 3-year-old quantization paper with 350 citations that is not yet cached is scored and inserted with `paper_kind="older"`

#### Scenario: Skips papers within the age cutoff
- **WHEN** a discovered paper is only 1 year old and `older_works_min_age_years=2`
- **THEN** that paper is not selected by the older-works track (it remains eligible for the normal fresh-paper fetch via arXiv)

#### Scenario: Skips papers older than the upper bound
- **WHEN** a 15-year-old highly-cited paper appears in S2 results and `older_works_max_age_years=10`
- **THEN** the year-range filter on the S2 query excludes it before it ever reaches the scorer — so 1990s/2000s classics that aren't relevant to today's AI Infra audience never enter the digest

#### Scenario: Per-ingest score cap respected
- **WHEN** discovery returns 60 new (uncached) older papers and `older_works_max_new_per_ingest=20`
- **THEN** at most 20 are sent to the Claude scorer this ingest; the remaining 40 are not lost — they will be re-discovered and considered on the next ingest tick

#### Scenario: Skips papers without arXiv ID
- **WHEN** the Semantic Scholar search returns a highly-cited paper with no arXiv ID
- **THEN** that paper is skipped and not inserted into the cache

#### Scenario: Already-cached classic gets promoted
- **WHEN** S2 search returns FlashAttention (already in the cache as `paper_kind="fresh"` with `citation_count=4500`) and `older_works_promote_min_citations=500`
- **THEN** that paper's `paper_kind` is flipped to `"older"` via UPDATE; its existing scores, summary, and `citation_count_at_score` snapshot are preserved (no rescore, no Claude API call)

#### Scenario: Already-cached but below promote threshold
- **WHEN** an already-cached `paper_kind="fresh"` paper with `citation_count=200` is surfaced by S2 search and `older_works_promote_min_citations=500`
- **THEN** the paper is left as-is (no flip) — promotion is reserved for clear classics, not borderline cases

#### Scenario: Respects min_citations threshold
- **WHEN** `min_citations_for_older_works=100` and a discovered paper has `citationCount=42`
- **THEN** that paper is not inserted

#### Scenario: Multiple keyword variants per sub-domain
- **WHEN** the older-works track runs for `quantization` with `older_works_keywords_per_sub_domain=4`
- **THEN** S2 search is called four times, once per variant from `SUB_DOMAINS["quantization"][:4]` (e.g. `quantization`, `PTQ`, `QAT`, `INT8`); results are deduped by `arxiv_id` across all four

#### Scenario: Source sub-domain force-tagged after scoring
- **WHEN** S2's `quantization` query surfaces a paper that Claude tags `compiler` after scoring
- **THEN** the cached `sub_domain_tags` includes BOTH `compiler` (from Claude) AND `quantization` (the originating sub-domain), so quantization subscribers see it in their digest

#### Scenario: Citation count carried forward from search
- **WHEN** a paper is surfaced with `citationCount=320` in the S2 search response
- **THEN** that count is stored as the cached row's `citation_count` and passed into the scorer as `citation_context` — the system does NOT issue a second S2 batch lookup for the same data

### Requirement: Older-works delivery in digest

When `thresholds.older_works_per_digest > 0`, each per-user digest SHALL include up to `older_works_per_digest` older-works papers (`paper_kind="older"`) in a visually distinct "重要老作 / Important Older Works" section, separate from the fresh-papers section. Older-works papers SHALL be deduplicated against the user's `sent_papers` (a user receives an older work at most once), filtered by the user's subscribed sub-domains and global `min_tier`, and selected by ranking within the older pool (tier-then-score-then-citation). Older-works papers SHALL NOT count against the user's `top_n` fresh-paper budget — they are additive up to `older_works_per_digest`.

#### Scenario: Older section included
- **WHEN** a digest is built for a user with `older_works_per_digest=2` and 5 unsent older papers match the user's sub-domains and tier
- **THEN** the digest contains a distinct older-works section with the top 2 older papers by rank

#### Scenario: Older works not double-sent
- **WHEN** an older work was sent to a user in a previous digest
- **THEN** it is excluded from that user's future older-works selections

#### Scenario: Older works additive to top_n
- **WHEN** a user has `top_n=10` and `older_works_per_digest=2`
- **THEN** the digest contains up to 10 fresh papers PLUS up to 2 older papers (not 10 total)

#### Scenario: Disabled when count is zero
- **WHEN** `older_works_per_digest=0`
- **THEN** no older-works track runs, no older section appears in any digest, and behavior matches pre-change

### Requirement: Older-works web filter

`GET /` and `GET /_paper_list` SHALL accept an optional `?older=<value>` query parameter where `<value>` is one of: `only`, `include`, `exclude`. When `?older=only`, only papers with `paper_kind="older"` are returned. When `?older=include`, both fresh and older papers are returned (default behavior when the param is omitted, so existing bookmarks keep working). When `?older=exclude`, only `paper_kind="fresh"` papers are returned. Invalid values SHALL be ignored (treated as `include`).

#### Scenario: Filter to older only
- **WHEN** user visits `/?older=only`
- **THEN** only papers with `paper_kind="older"` are shown

#### Scenario: Exclude older
- **WHEN** user visits `/?older=exclude`
- **THEN** only papers with `paper_kind="fresh"` are shown

#### Scenario: Default includes both
- **WHEN** user visits `/` without the `?older` param
- **THEN** both fresh and older papers are shown (matching pre-change behavior where all cached papers were visible)

#### Scenario: Invalid value ignored
- **WHEN** user visits `/?older=banana`
- **THEN** the filter is treated as `include` and both kinds are shown
