## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: PaperDatabase list_papers method

`PaperDatabase` SHALL expose `list_papers(sub_domains=None, search=None, published_after=None, limit=25, offset=0) -> list[ScoredPaper]` and `count_papers(sub_domains=None, search=None, published_after=None) -> int`. When `sub_domains` is provided, only papers whose `sub_domain_tags` intersect the set are returned. When `published_after` is provided, only papers with `published >= published_after` are returned. When `search` is provided, only papers whose title contains the search text (case-insensitive) are returned. All filters combine with AND logic.

#### Scenario: No filter
- **WHEN** `list_papers(limit=10)` is called
- **THEN** the 10 highest-scoring papers are returned

#### Scenario: Sub-domain filter
- **WHEN** `list_papers(sub_domains={"moe"}, limit=10)` is called
- **THEN** only papers tagged with `moe` are returned, sorted by total score

#### Scenario: Search filter
- **WHEN** `list_papers(search="kv cache", limit=10)` is called
- **THEN** only papers whose title contains "kv cache" (case-insensitive) are returned

#### Scenario: Time range filter
- **WHEN** `list_papers(published_after=date(2024, 6, 1), limit=10)` is called
- **THEN** only papers published on or after 2024-06-01 are returned, sorted by total score

#### Scenario: Combined filters
- **WHEN** `list_papers(sub_domains={"quantization"}, search="llm", published_after=date(2024, 1, 1), limit=10)` is called
- **THEN** only papers tagged with `quantization` AND whose title contains "llm" AND published on or after 2024-01-01 are returned

#### Scenario: count_papers matches list_papers
- **WHEN** `count_papers(sub_domains={"moe"})` returns 42
- **THEN** paginating `list_papers(sub_domains={"moe"})` across all offsets yields exactly 42 papers in total

#### Scenario: count_papers with time range
- **WHEN** `count_papers(published_after=date(2024, 6, 1))` returns 25
- **THEN** paginating `list_papers(published_after=date(2024, 6, 1))` across all offsets yields exactly 25 papers in total
