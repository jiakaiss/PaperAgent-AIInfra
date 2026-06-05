## MODIFIED Requirements

### Requirement: Paper list endpoint
The app SHALL serve `GET /` which renders a paginated list of scored papers from the `papers` table. The server reads filters from query parameters and configured defaults — it has no notion of a current user or a stored preference. The client JS is responsible for translating `localStorage` preferences into query params on each request. When query parameters include one or more `sub_domain` values, the returned list SHALL include only papers whose `sub_domain_tags` intersect that set. When a quality threshold is configured or requested, the returned list SHALL exclude papers below that threshold.

#### Scenario: Default visit (mode=all in localStorage)
- **WHEN** a visitor with `localStorage.mode = "all"` opens `/`
- **THEN** the client requests `/` with no sub-domain params and the page lists all scored papers meeting the configured quality threshold, sorted by `total_score` descending

#### Scenario: Custom mode with selected tags
- **WHEN** a visitor with `localStorage.mode = "custom"` and `subDomains = ["quantization", "sparsity"]` opens `/`
- **THEN** the client issues a request equivalent to `/?sub_domain=quantization&sub_domain=sparsity` and the page lists only papers whose `sub_domain_tags` intersect that set and whose quality meets the configured threshold

#### Scenario: Server-side statelessness
- **WHEN** two different browsers request `/` at the same time
- **THEN** both receive the same quality-filtered unfiltered paper list; each browser applies its own `localStorage` filters client-side before re-fetching

#### Scenario: HTMX fragment respects sub-domain filters
- **WHEN** the client requests `/_paper_list?sub_domain=quantization`
- **THEN** the fragment contains only papers tagged with `quantization` that meet the configured quality threshold and excludes papers that do not have that tag

#### Scenario: Multiple sub-domain filters use OR semantics
- **WHEN** the client requests `/_paper_list?sub_domain=quantization&sub_domain=moe`
- **THEN** the fragment contains papers tagged with either `quantization` or `moe` and meeting the configured quality threshold, and excludes papers tagged only with unrelated domains

### Requirement: PaperDatabase list_papers method
`PaperDatabase` SHALL expose `list_papers(sub_domains=None, search=None, published_after=None, min_quality=None, limit=25, offset=0) -> list[ScoredPaper]` and `count_papers(sub_domains=None, search=None, published_after=None, min_quality=None) -> int`. When `sub_domains` is provided, only papers whose `sub_domain_tags` intersect the set are returned. When `min_quality` is provided, only papers whose `quality_score` is greater than or equal to `min_quality` are returned. An empty or `None` `sub_domains` argument means no sub-domain filter.

#### Scenario: No filter
- **WHEN** `list_papers(limit=10)` is called
- **THEN** the 10 highest-scoring papers are returned

#### Scenario: Sub-domain filter
- **WHEN** `list_papers(sub_domains={"moe"}, limit=10)` is called
- **THEN** only papers tagged with `moe` are returned, sorted by total score

#### Scenario: Search filter
- **WHEN** `list_papers(search="kv cache", limit=10)` is called
- **THEN** only papers whose title contains "kv cache" (case-insensitive) are returned

#### Scenario: Quality filter
- **WHEN** `list_papers(min_quality=6.0, limit=10)` is called
- **THEN** only papers whose quality score is at least 6.0 are returned

#### Scenario: count_papers matches list_papers
- **WHEN** `count_papers(sub_domains={"moe"}, min_quality=6.0)` returns 42
- **THEN** paginating `list_papers(sub_domains={"moe"}, min_quality=6.0)` across all offsets yields exactly 42 papers in total

#### Scenario: Combined sub-domain search and quality filter
- **WHEN** `list_papers(sub_domains={"quantization"}, search="llm", min_quality=6.0)` is called
- **THEN** only papers whose title contains "llm", whose tags include `quantization`, and whose quality score is at least 6.0 are returned

## ADDED Requirements

### Requirement: Configurable low-quality browsing filter
The system SHALL allow operators to configure a default minimum quality score for web paper browsing. The filter SHALL apply consistently to full-page and HTMX paper-list requests unless disabled by configuration.

#### Scenario: Default minimum quality configured
- **WHEN** web browsing minimum quality is configured as 6.0 and user visits `/`
- **THEN** papers with `quality_score < 6.0` are not shown in the list or counted in pagination totals

#### Scenario: Minimum quality disabled
- **WHEN** web browsing minimum quality is disabled or set to zero
- **THEN** the web paper list can include papers regardless of quality score, subject to other filters

#### Scenario: Full page and fragment match
- **WHEN** a user loads `/` and then refreshes `/_paper_list` with the same filters
- **THEN** both responses apply the same configured minimum quality threshold
