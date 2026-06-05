## Context

The paper browsing web UI (shipped in `web-frontend` change) currently supports filtering by sub-domain tags, title search, and pagination. Papers are sorted by total score (relevance × 0.6 + quality × 0.4) descending. There is no time-based filtering — users see all scored papers regardless of publication date.

The `papers` table has a `published` column (ISO 8601 date string from arXiv) that is currently unused for filtering. The storage layer's `list_papers()` and `count_papers()` methods accept `sub_domains` and `search` parameters but no date filter.

Constraints:
- The web server is a stateless reader over the existing `papers` cache — no schema changes to the `papers` table.
- Time range is a transient filter (like search query `q`), not a user preference — no localStorage persistence needed.
- The UI should match the existing aesthetic (chip group for sub-domains, search box, pagination).

## Goals / Non-Goals

**Goals:**
- Users can filter papers by publication date range (past week, month, 3 months, 6 months, 1 year, 3 years).
- The time range is encoded in the URL (`?since=1m`) so filtered views are shareable and bookmarkable.
- The storage layer's `list_papers()` and `count_papers()` methods gain a `published_after` parameter.
- The UI includes a time range selector (chip group or dropdown) that updates the paper list via HTMX.

**Non-Goals:**
- Absolute date picker (e.g., "from 2024-01-01 to 2024-06-30") — only relative ranges for now.
- Persisting the time range in localStorage — it's URL-only.
- Sorting by publication date (current sort is by total score).
- Time range filtering in the CLI or notifier — web UI only.

## Decisions

### 1. Relative time range encoding in URL

**Decision:** Use relative values `1w`, `1m`, `3m`, `6m`, `1y`, `3y` in the `?since=` URL parameter. The backend converts these to an absolute `published_after` date using `datetime.now() - timedelta(...)`.

**Alternatives considered:**
- *Absolute dates* (`?from=2024-01-01`): harder to bookmark (dates become stale), more complex UI (date picker), requires timezone handling.
- *Preset names* (`?range=recent`): less precise, harder to extend later.

**Rationale:** Relative values are bookmark-friendly (a link to `?since=1m` always means "past month"), easy to parse, and match the user's mental model ("show me recent papers").

### 2. Storage layer: extend existing methods

**Decision:** Add a `published_after: date | None = None` parameter to the existing `list_papers()` and `count_papers()` methods. The parameter is optional and defaults to `None` (no filter).

**Alternatives considered:**
- *New methods* (`list_papers_since()`, `count_papers_since()`): duplicates logic, harder to maintain.
- *Separate filter method*: overkill for a single new parameter.

**Rationale:** The existing `_build_filter_clause()` helper already constructs the WHERE clause from multiple filters. Adding `published_after` is a one-line extension: `WHERE published >= ? AND ...`.

### 3. UI component: chip group (not dropdown)

**Decision:** Render the time range selector as a chip group (matching the sub-domain chip filter aesthetic), with options: "All time", "1 week", "1 month", "3 months", "6 months", "1 year", "3 years".

**Alternatives considered:**
- *Dropdown select*: more compact but less visible, doesn't match the chip aesthetic.
- *Radio buttons*: takes up more vertical space.

**Rationale:** Chip groups are already used for sub-domain filtering, so this is consistent. The "All time" chip is the default (no `?since=` param).

### 4. Backend date conversion

**Decision:** The backend route handler converts `?since=1m` to a `published_after` date using a helper function `_parse_since(since: str) -> date | None`. The helper returns `None` for invalid or missing values (no filter applied).

**Rationale:** Centralizing the conversion in one helper keeps the route handler clean and makes the logic testable.

### 5. URL bar updates via replaceState

**Decision:** When the user clicks a time range chip, the client JS calls `history.replaceState()` to update the URL bar with the new `?since=` value, then re-fetches the paper list via HTMX.

**Rationale:** Matches the existing pattern for sub-domain chips and search. Users can copy the URL to share a filtered view.

## Risks / Trade-offs

- **[Date calculation drift]** The backend calculates `published_after` using `datetime.now()` at request time. If the server clock is wrong, the filter will be off. → Mitigation: acceptable for v1; server clock is assumed correct.
- **[No absolute dates]** Users who want "papers from January 2024" can't specify that. → Mitigation: out of scope for v1; can add absolute date picker later if needed.
- **[Chip group takes space]** 7 chips (All time + 6 ranges) may not fit on narrow screens. → Mitigation: wrap to multiple lines on mobile (CSS `flex-wrap: wrap`).
- **[No localStorage persistence]** Users who always want "past month" must click the chip every visit. → Mitigation: acceptable for v1; can add persistence later if users request it.
