## ADDED Requirements

### Requirement: Paper list endpoint
The app SHALL serve `GET /` which renders a paginated list of scored papers from the `papers` table. The server reads filters purely from query parameters — it has no notion of a current user or a stored preference. The client JS is responsible for translating `localStorage` preferences into query params on each request.

#### Scenario: Default visit (mode=all in localStorage)
- **WHEN** a visitor with `localStorage.mode = "all"` opens `/`
- **THEN** the client requests `/` with no sub-domain params and the page lists all scored papers, sorted by `total_score` descending

#### Scenario: Custom mode with selected tags
- **WHEN** a visitor with `localStorage.mode = "custom"` and `subDomains = ["quantization", "sparsity"]` opens `/`
- **THEN** the client issues a request equivalent to `/?sub_domain=quantization&sub_domain=sparsity` and the page lists only papers whose `sub_domain_tags` intersect that set

#### Scenario: Server-side statelessness
- **WHEN** two different browsers request `/` at the same time
- **THEN** both receive the same unfiltered paper list; each browser applies its own `localStorage` filters client-side before re-fetching

### Requirement: URL mode override
`GET /` SHALL accept an optional `?mode=custom|all` query parameter. The server SHALL use it for this request only. The client JS, upon seeing `?mode=`, SHALL overwrite `localStorage.mode` with the new value.

#### Scenario: Override to all
- **WHEN** a visitor with `localStorage.mode = "custom"` visits `/?mode=all`
- **THEN** the client writes `mode = "all"` to `localStorage` and requests the unfiltered paper list

#### Scenario: Invalid mode value ignored
- **WHEN** user visits `/?mode=banana`
- **THEN** the server ignores the value and the client keeps the existing `localStorage.mode`

### Requirement: Sub-domain filter chip
`GET /` SHALL accept an optional `?sub_domain=<key>` query parameter that further filters to a single sub-domain (applied on top of the user's mode).

#### Scenario: Filter to moe
- **WHEN** user `alice` visits `/?sub_domain=moe`
- **THEN** only papers tagged with `moe` are shown, regardless of her mode

#### Scenario: Unknown sub-domain
- **WHEN** user visits `/?sub_domain=not_a_real_tag`
- **THEN** the filter is ignored and all (mode-filtered) papers are shown

### Requirement: Title search
`GET /` SHALL accept an optional `?q=<text>` query parameter that filters papers whose title (case-insensitive) contains the text.

#### Scenario: Search matches
- **WHEN** user searches `?q=quantization`
- **THEN** only papers whose title contains `quantization` (any case) are shown

#### Scenario: Combined with sub-domain
- **WHEN** user visits `/?sub_domain=compiler&q=flashattention`
- **THEN** results match both filters (AND logic)

### Requirement: Pagination
`GET /` SHALL paginate results with a default page size of 25 and accept `?page=N` (1-indexed). The page SHALL include Previous / Next controls and total count.

#### Scenario: First page
- **WHEN** the database has 120 papers matching the current filters and the user visits `/`
- **THEN** 25 papers are shown, "Next" is enabled, "Previous" is disabled, and "Total: 120" is displayed

#### Scenario: Middle page
- **WHEN** user visits `/?page=3`
- **THEN** papers 51–75 are shown, both Previous and Next are enabled

#### Scenario: Past last page
- **WHEN** user visits `/?page=999`
- **THEN** the last page of results is shown (clamped to the maximum valid page)

### Requirement: Paper card content
Each paper in the list SHALL render: title (linked to `abs_url`), first 3 authors + "et al." if more, Chinese summary (`summary_zh`), sub-domain tag chips, relevance score, quality score, and total score.

#### Scenario: Full card
- **WHEN** a paper with 6 authors, tags `(quantization, sparsity)`, relevance=8.5, quality=7.0 is rendered
- **THEN** the card shows: clickable title, "Author1, Author2, Author3 et al.", the Chinese summary, two tag chips, "R: 8.5", "Q: 7.0", "Total: 7.9"

#### Scenario: Paper with no tags
- **WHEN** a paper has empty `sub_domain_tags`
- **THEN** the tag area shows "general" (matching `ScoredPaper.sub_domain_display`)

### Requirement: PaperDatabase list_papers method
`PaperDatabase` SHALL expose `list_papers(sub_domains=None, search=None, limit=25, offset=0) -> list[ScoredPaper]` and `count_papers(sub_domains=None, search=None) -> int`. When `sub_domains` is provided, only papers whose `sub_domain_tags` intersect the set are returned.

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

### Requirement: Empty state
When no papers match the current filters (or the database is empty), the page SHALL show an explanatory message and a call-to-action (e.g. "Run `paper-agent run` first" or "Try clearing filters").

#### Scenario: Empty database
- **WHEN** user visits `/` with zero papers in the database
- **THEN** an empty-state panel is shown with guidance to run the pipeline

#### Scenario: Filter returns nothing
- **WHEN** user applies a filter combination with zero matches
- **THEN** a "No papers match. Try clearing filters." message is shown with a "Clear filters" link
