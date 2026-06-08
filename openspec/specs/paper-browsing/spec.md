## Purpose

Define the web paper browsing experience, including paper listing, filtering, search, pagination, and display behavior.
## Requirements
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

### Requirement: URL mode override
`GET /` SHALL accept an optional `?mode=custom|all` query parameter. The server SHALL use it for this request only. The client JS, upon seeing `?mode=`, SHALL overwrite `localStorage.mode` with the new value.

#### Scenario: Override to all
- **WHEN** a visitor with `localStorage.mode = "custom"` visits `/?mode=all`
- **THEN** the client writes `mode = "all"` to `localStorage` and requests the unfiltered paper list

#### Scenario: Invalid mode value ignored
- **WHEN** user visits `/?mode=banana`
- **THEN** the server ignores the value and the client keeps the existing `localStorage.mode`

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
Each paper in the list SHALL render: title (linked to `abs_url`), first 3 authors + "et al." if more, Chinese summary (`summary_zh`), sub-domain tag chips, relevance score, quality score, total score, an impact-tier badge, a bulleted list of `key_contributions` (omitted if empty), and short `problem_statement_zh` and `methods_zh` blocks (omitted if empty). The card visual treatment SHALL vary by `impact_tier`:
- `breakthrough` — highlighted border and prominent tier badge
- `solid` — standard styling with a neutral tier badge
- `incremental` — dimmed (reduced opacity) styling with a muted tier badge

#### Scenario: Full breakthrough card
- **WHEN** a paper with 6 authors, tags `(quantization, sparsity)`, relevance=8.5, quality=7.0, `impact_tier="breakthrough"`, 2 key contributions, and non-empty zh problem/methods is rendered
- **THEN** the card shows: clickable title, "Author1, Author2, Author3 et al.", the Chinese summary, two tag chips, "R: 8.5", "Q: 7.0", "Total: 7.9", a "Breakthrough" badge, a highlighted border, a bulleted list of the 2 contributions, and the problem and methods blocks

#### Scenario: Legacy paper with empty new fields
- **WHEN** a paper has empty `key_contributions`, empty `problem_statement_zh`, empty `methods_zh`, and `impact_tier="solid"` (default for legacy rows)
- **THEN** the card renders standard styling with a "Solid" badge, no contributions list, and no problem/methods blocks (all empty sections are hidden, not rendered with empty containers)

#### Scenario: Incremental card is dimmed
- **WHEN** a paper has `impact_tier="incremental"` and is shown because the user opted into incremental tier
- **THEN** the card renders with reduced opacity and a muted "Incremental" badge; all content remains readable without interaction

#### Scenario: Paper with no tags
- **WHEN** a paper has empty `sub_domain_tags`
- **THEN** the tag area shows "general" (matching `ScoredPaper.sub_domain_display`)

### Requirement: PaperDatabase list_papers method

`PaperDatabase` SHALL expose `list_papers(sub_domains=None, search=None, published_after=None, tiers=None, limit=25, offset=0) -> list[ScoredPaper]` and `count_papers(sub_domains=None, search=None, published_after=None, tiers=None) -> int`. When `sub_domains` is provided, only papers whose `sub_domain_tags` intersect the set are returned. When `published_after` is provided, only papers with `published >= published_after` are returned. When `search` is provided, only papers whose title contains the search text (case-insensitive) are returned. When `tiers` is provided, only papers whose `impact_tier` is in the set are returned (NULL `impact_tier` is treated as `"solid"`). All filters combine with AND logic. The returned list SHALL be ordered by `impact_tier` rank (breakthrough < solid < incremental) and then `total_score` descending.

#### Scenario: No filter
- **WHEN** `list_papers(limit=10)` is called
- **THEN** the 10 highest-priority papers (tier-then-score) are returned

#### Scenario: Sub-domain filter
- **WHEN** `list_papers(sub_domains={"moe"}, limit=10)` is called
- **THEN** only papers whose `sub_domain_tags` contain `moe` are returned, ordered by tier-then-score

#### Scenario: Tier filter
- **WHEN** `list_papers(tiers={"breakthrough"}, limit=10)` is called
- **THEN** only `breakthrough` papers are returned

#### Scenario: Legacy paper treated as solid
- **WHEN** `list_papers(tiers={"solid"}, limit=10)` is called and a paper with NULL `impact_tier` exists
- **THEN** that paper IS included in the results

#### Scenario: Search filter
- **WHEN** `list_papers(search="kv cache", limit=10)` is called
- **THEN** only papers whose title contains "kv cache" (case-insensitive) are returned

#### Scenario: Time range filter
- **WHEN** `list_papers(published_after=date(2024, 6, 1), limit=10)` is called
- **THEN** only papers published on or after 2024-06-01 are returned, sorted by tier-then-score

#### Scenario: Combined filters
- **WHEN** `list_papers(sub_domains={"quantization"}, search="llm", published_after=date(2024, 1, 1), limit=10)` is called
- **THEN** only papers tagged with `quantization` AND whose title contains "llm" AND published on or after 2024-01-01 are returned

#### Scenario: count_papers matches list_papers
- **WHEN** `count_papers(sub_domains={"moe"})` returns 42
- **THEN** paginating `list_papers(sub_domains={"moe"})` across all offsets yields exactly 42 papers in total

#### Scenario: count_papers with time range
- **WHEN** `count_papers(published_after=date(2024, 6, 1))` returns 25
- **THEN** paginating `list_papers(published_after=date(2024, 6, 1))` across all offsets yields exactly 25 papers in total

### Requirement: Empty state
When no papers match the current filters (or the database is empty), the page SHALL show an explanatory message and a call-to-action (e.g. "Run `paper-agent run` first" or "Try clearing filters").

#### Scenario: Empty database
- **WHEN** user visits `/` with zero papers in the database
- **THEN** an empty-state panel is shown with guidance to run the pipeline

#### Scenario: Filter returns nothing
- **WHEN** user applies a filter combination with zero matches
- **THEN** a "No papers match. Try clearing filters." message is shown with a "Clear filters" link

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

### Requirement: Time range filter URL parameter

`GET /` and `GET /_paper_list` SHALL accept an optional `?since=<value>` query parameter where `<value>` is one of: `1w`, `1m`, `3m`, `6m`, `1y`, `3y`. When provided, only papers with `published` date within the specified relative range (from today) SHALL be returned. Invalid or unknown values SHALL be ignored (no filter applied).

#### Scenario: Filter to past month
- **WHEN** user visits `/?since=1m`
- **THEN** only papers published within the past month are shown

#### Scenario: Filter to past 3 months
- **WHEN** user visits `/?since=3m`
- **THEN** only papers published within the past 3 months are shown

#### Scenario: Combined with sub-domain filter
- **WHEN** user visits `/?since=6m&sub_domain=quantization`
- **THEN** only papers tagged with `quantization` AND published within the past 6 months are shown (AND logic)

#### Scenario: Combined with search
- **WHEN** user visits `/?since=1y&q=flashattention`
- **THEN** only papers whose title contains `flashattention` AND published within the past year are shown (AND logic)

#### Scenario: Invalid since value ignored
- **WHEN** user visits `/?since=invalid`
- **THEN** the filter is ignored and all (other-filtered) papers are shown

### Requirement: Time range selector UI

The main page SHALL render a time range selector (chip group) with options: "All time", "1 week", "1 month", "3 months", "6 months", "1 year", "3 years". Clicking a chip SHALL update the URL with the corresponding `?since=` value (or remove it for "All time"), then re-fetch the paper list via HTMX. The currently active chip SHALL have the `chip-active` CSS class.

#### Scenario: Click "1 month" chip
- **WHEN** user clicks the "1 month" chip
- **THEN** the URL updates to `?since=1m`, the "1 month" chip gains the `chip-active` class, and the paper list re-fetches showing only papers from the past month

#### Scenario: Click "All time" chip
- **WHEN** user has `?since=3m` active and clicks "All time"
- **THEN** the `?since=` param is removed from the URL, all time range chips lose the `chip-active` class (or "All time" gains it), and the paper list re-fetches showing all papers

#### Scenario: Time range chip state survives page reload
- **WHEN** user visits `/?since=6m` and reloads the page
- **THEN** the "6 months" chip is rendered with the `chip-active` class and the paper list shows only papers from the past 6 months

#### Scenario: Time range selector on mobile
- **WHEN** the page is viewed on a narrow screen (< 768px)
- **THEN** the time range chips wrap to multiple lines (CSS `flex-wrap: wrap`)

### Requirement: PaperDatabase time range filter

`PaperDatabase` SHALL accept a `published_after: date | None = None` parameter in `list_papers()` and `count_papers()`. When provided, only papers with `published >= published_after` SHALL be returned. The filter SHALL combine with `sub_domains` and `search` using AND logic.

#### Scenario: Time range filter alone
- **WHEN** `list_papers(published_after=date(2024, 6, 1), limit=10)` is called
- **THEN** only papers with `published >= 2024-06-01` are returned, sorted by total score

#### Scenario: Time range combined with sub-domain
- **WHEN** `list_papers(published_after=date(2024, 1, 1), sub_domains={"moe"}, limit=10)` is called
- **THEN** only papers tagged with `moe` AND published on or after 2024-01-01 are returned

#### Scenario: count_papers matches list_papers with time range
- **WHEN** `count_papers(published_after=date(2024, 6, 1))` returns 25
- **THEN** paginating `list_papers(published_after=date(2024, 6, 1))` across all offsets yields exactly 25 papers in total

