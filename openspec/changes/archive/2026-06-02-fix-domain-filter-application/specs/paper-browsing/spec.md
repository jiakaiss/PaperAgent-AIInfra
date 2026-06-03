## MODIFIED Requirements

### Requirement: Paper list endpoint
The app SHALL serve `GET /` which renders a paginated list of scored papers from the `papers` table. The server reads filters purely from query parameters — it has no notion of a current user or a stored preference. The client JS is responsible for translating `localStorage` preferences into query params on each request. When query parameters include one or more `sub_domain` values, the returned list SHALL include only papers whose `sub_domain_tags` intersect that set.

#### Scenario: Default visit (mode=all in localStorage)
- **WHEN** a visitor with `localStorage.mode = "all"` opens `/`
- **THEN** the client requests `/` with no sub-domain params and the page lists all scored papers, sorted by `total_score` descending

#### Scenario: Custom mode with selected tags
- **WHEN** a visitor with `localStorage.mode = "custom"` and `subDomains = ["quantization", "sparsity"]` opens `/`
- **THEN** the client issues a request equivalent to `/?sub_domain=quantization&sub_domain=sparsity` and the page lists only papers whose `sub_domain_tags` intersect that set

#### Scenario: Server-side statelessness
- **WHEN** two different browsers request `/` at the same time
- **THEN** both receive the same unfiltered paper list; each browser applies its own `localStorage` filters client-side before re-fetching

#### Scenario: HTMX fragment respects sub-domain filters
- **WHEN** the client requests `/_paper_list?sub_domain=quantization`
- **THEN** the fragment contains only papers tagged with `quantization` and excludes papers that do not have that tag

#### Scenario: Multiple sub-domain filters use OR semantics
- **WHEN** the client requests `/_paper_list?sub_domain=quantization&sub_domain=moe`
- **THEN** the fragment contains papers tagged with either `quantization` or `moe`, and excludes papers tagged only with unrelated domains

### Requirement: Sub-domain filter chip
`GET /` and `GET /_paper_list` SHALL accept optional repeated `?sub_domain=<key>` query parameters that filter papers to any matching sub-domain. Unknown sub-domain values SHALL be ignored. When all provided sub-domain values are unknown, the server SHALL treat the request as unfiltered unless the client intentionally renders an empty custom-mode state.

#### Scenario: Filter to moe
- **WHEN** user visits `/?sub_domain=moe`
- **THEN** only papers tagged with `moe` are shown, regardless of her mode

#### Scenario: Unknown sub-domain
- **WHEN** user visits `/?sub_domain=not_a_real_tag`
- **THEN** the filter is ignored and all (mode-filtered) papers are shown

#### Scenario: Repeated sub-domain params
- **WHEN** user visits `/?sub_domain=moe&sub_domain=quantization`
- **THEN** papers tagged with `moe` or `quantization` are shown and papers without either tag are excluded

### Requirement: PaperDatabase list_papers method
`PaperDatabase` SHALL expose `list_papers(sub_domains=None, search=None, limit=25, offset=0) -> list[ScoredPaper]` and `count_papers(sub_domains=None, search=None) -> int`. When `sub_domains` is provided, only papers whose `sub_domain_tags` intersect the set are returned. An empty or `None` `sub_domains` argument means no sub-domain filter.

#### Scenario: No filter
- **WHEN** `list_papers(limit=10)` is called
- **THEN** the 10 highest-scoring papers are returned

#### Scenario: Sub-domain filter
- **WHEN** `list_papers(sub_domains={"moe"}, limit=10)` is called
- **THEN** only papers tagged with `moe` are returned, sorted by total score

#### Scenario: Search filter
- **WHEN** `list_papers(search="kv cache", limit=10)` is called
- **THEN** only papers whose title contains "kv cache" (case-insensitive) are returned

#### Scenario: count_papers matches list_papers
- **WHEN** `count_papers(sub_domains={"moe"})` returns 42
- **THEN** paginating `list_papers(sub_domains={"moe"})` across all offsets yields exactly 42 papers in total

#### Scenario: Combined sub-domain and search filter
- **WHEN** `list_papers(sub_domains={"quantization"}, search="llm")` is called
- **THEN** only papers whose title contains "llm" and whose tags include `quantization` are returned
