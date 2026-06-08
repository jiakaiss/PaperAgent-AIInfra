## ADDED Requirements

### Requirement: Per-keyword fetch cap

The arXiv fetcher SHALL cap the number of results returned per individual keyword query to prevent a single noisy keyword from starving others. The cap SHALL be computed as `max(min_per_keyword, fetch.max_results // max(1, num_keywords))` where `min_per_keyword` is a configurable lower bound (default 10).

#### Scenario: Many keywords share the budget
- **WHEN** `fetch.max_results=200` and the superset has 20 keywords
- **THEN** each keyword query returns at most `max(10, 200//20)=10` results, and the combined deduped fetch is at most 200 papers (modulo overlap)

#### Scenario: Few keywords keep larger share
- **WHEN** `fetch.max_results=200` and the superset has 2 keywords
- **THEN** each keyword query returns at most `max(10, 200//2)=100` results

### Requirement: Cross-list recency fetch

In addition to keyword queries, the fetcher SHALL issue a second-pass query against arXiv listings for papers cross-listed in categories configured under `fetch.cross_list_categories` (default `["cs.LG", "cs.DC"]`) and published within `fetch.days_back`. Results from the cross-list pass SHALL be deduped against the keyword-pass results by `arxiv_id`. When the same paper appears in both passes, the keyword-pass record SHALL be kept (to preserve provenance for debugging).

#### Scenario: Cross-list picks up missed paper
- **WHEN** a new cs.LG paper about attention variants does not contain any configured keyword in its title or abstract, but was published 2 days ago
- **THEN** the keyword pass misses it, the cross-list pass returns it, and the deduped output includes it exactly once

#### Scenario: Overlap deduplication
- **WHEN** paper `2406.12345` appears in both the keyword-pass (matched on `"quantization"`) and the cross-list pass (cs.LG)
- **THEN** the deduped fetch contains exactly one record for `2406.12345` and that record carries the keyword-pass provenance metadata

#### Scenario: Empty cross-list config disables second pass
- **WHEN** `fetch.cross_list_categories=[]`
- **THEN** the fetcher runs only the keyword pass and the behavior is identical to the legacy single-pass fetcher

### Requirement: Quality floor strategy config

`FetchConfig` SHALL accept an optional `quality_floor_strategy` field with values `none` (legacy behavior) or `per_keyword_cap` (default for new installs). Existing configs without this field SHALL default to `none` to preserve fetch behavior until the operator opts in.

#### Scenario: Default for new installs uses per_keyword_cap
- **WHEN** a fresh `config.example.yaml` is rendered
- **THEN** `fetch.quality_floor_strategy: per_keyword_cap` is present

#### Scenario: Legacy config preserves old behavior
- **WHEN** an existing `config.yaml` without `quality_floor_strategy` is loaded
- **THEN** `FetchConfig.quality_floor_strategy` is `"none"` and the per-keyword cap is not applied

#### Scenario: per_keyword_cap enables the cap
- **WHEN** `fetch.quality_floor_strategy="per_keyword_cap"`
- **THEN** the per-keyword cap and cross-list pass are both active
