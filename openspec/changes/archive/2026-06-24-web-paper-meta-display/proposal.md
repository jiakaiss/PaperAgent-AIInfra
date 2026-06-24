## Why

The current paper card hides two pieces of context that readers regularly want when triaging the list: the paper's publication date and a clean "no citations yet" signal (today the citation badge is suppressed entirely when `citation_count=0`, which makes a fresh paper visually indistinguishable from one whose citation data has never been refreshed). Additionally, the badges in the header (`重磅突破`, `重要老作`, citation count) currently float between the title and the right edge with loose spacing, which looks misaligned across cards with different title lengths.

## What Changes

- Render `paper.published` (date only, `YYYY-MM-DD`) on every paper card in the web list, in a muted style next to the authors line.
- Always render the citation badge — including when `citation_count == 0` (text becomes `📈 0 citations`). The "no badge when zero" rule is removed.
- Group the tier badge, older-works badge, and citation badge into a single right-aligned cluster in `.paper-card-header`, tightly spaced and pinned to the right edge regardless of title wrap.
- Refresh the affected scenarios in the `paper-browsing` spec so the "legacy paper with empty new fields" scenario no longer expects the citation badge to be absent at zero, and a new scenario codifies the published-date rendering.

No backend / database / config changes. The `Paper.published` field already exists on `ScoredPaper.paper`; `ScoredPaper.citation_count` already defaults to `0` for legacy rows.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `paper-browsing`: paper-card content rule gains a published-date element and changes the citation-badge visibility rule from "only when > 0" to "always rendered". Header layout requirement gets a right-aligned badge cluster.

## Impact

- Templates: `src/paper_agent/web/templates/_paper_list.html` (card header markup, authors/meta row).
- Styles: `src/paper_agent/web/static/style.css` (`.paper-card-header`, badge spacing, new `.paper-published` rule).
- Tests: `tests/test_web_routes.py` (or equivalent) — assertions about citation-badge presence at `citation_count=0` and published-date rendering.
- No DB migration, no API change, no config change.
