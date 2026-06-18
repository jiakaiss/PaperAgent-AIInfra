## ADDED Requirements

### Requirement: Citation coverage stats panel

When `citations.enabled` is `true`, the `GET /admin/_papers` fragment SHALL additionally render a citation-coverage sub-section containing: the count and percentage of cached papers with a non-null `citations_updated_at` (i.e., ever refreshed), the count with `citation_count > 0`, the most recent `citations_updated_at` timestamp across the cache (last refresh), and a one-line summary of the `citations` config (provider, refresh interval, enabled state). When `citations.enabled` is `false`, the sub-section SHALL render a single line stating "引用数采集未启用 (citations.enabled=false)" and no coverage numbers.

#### Scenario: Coverage shown when enabled
- **WHEN** `citations.enabled=true` and the cache has 200 papers, 150 of which have non-null `citations_updated_at` and 80 have `citation_count > 0`
- **THEN** the panel renders "150 / 200 (75%) 已采集引用数", "80 篇有引用", the most recent refresh timestamp, and the provider/interval summary

#### Scenario: Disabled state message
- **WHEN** `citations.enabled=false`
- **THEN** the citation sub-section renders only "引用数采集未启用 (citations.enabled=false)" and no coverage counts

#### Scenario: Never refreshed
- **WHEN** `citations.enabled=true` but no paper has ever been refreshed (`citations_updated_at` all NULL)
- **THEN** the panel renders "0 / N (0%) 已采集引用数" and a last-refresh placeholder of `—`
