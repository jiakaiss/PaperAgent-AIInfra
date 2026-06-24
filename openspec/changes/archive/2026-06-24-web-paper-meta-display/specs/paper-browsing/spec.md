## MODIFIED Requirements

### Requirement: Paper card content
Each paper in the list SHALL render: title (linked to `abs_url`), first 3 authors + "et al." if more, the paper's publication date formatted as `YYYY-MM-DD` and displayed next to the authors line, Chinese summary (`summary_zh`), sub-domain tag chips, relevance score, quality score, total score, an impact-tier badge, a citation-count badge (ALWAYS rendered, including when `citation_count == 0`), an "older works" badge (when `paper_kind="older"`), a bulleted list of `key_contributions` (omitted if empty), and short `problem_statement_zh` and `methods_zh` blocks (omitted if empty).

The header SHALL group the tier badge, older-works badge (when present), and citation badge into a single right-aligned cluster with consistent inter-badge spacing. The cluster SHALL pin to the right edge of the card header regardless of title length, and the per-badge spacing SHALL be governed by the cluster's gap (not by per-badge margins) so the layout is identical whether or not the older-works badge is present.

The card visual treatment SHALL vary by `impact_tier`:
- `breakthrough` — highlighted border and prominent tier badge
- `solid` — standard styling with a neutral tier badge
- `incremental` — dimmed (reduced opacity) styling with a muted tier badge

#### Scenario: Full breakthrough card
- **WHEN** a paper with 6 authors, tags `(quantization, sparsity)`, relevance=8.5, quality=7.0, `impact_tier="breakthrough"`, `citation_count=120`, `published=2026-03-14`, 2 key contributions, and non-empty zh problem/methods is rendered
- **THEN** the card shows: clickable title, "Author1, Author2, Author3 et al." followed by "2026-03-14", the Chinese summary, two tag chips, "R: 8.5", "Q: 7.0", "Total: 7.9", a "Breakthrough" badge, a "📈 120 citations" badge, a highlighted border, a bulleted list of the 2 contributions, and the problem and methods blocks. The tier badge and citation badge sit in a single right-aligned cluster in the header.

#### Scenario: Legacy paper with empty new fields
- **WHEN** a paper has empty `key_contributions`, empty `problem_statement_zh`, empty `methods_zh`, `citation_count=0`, `paper_kind="fresh"`, and `impact_tier="solid"` (default for legacy rows)
- **THEN** the card renders standard styling with a "Solid" badge, a "📈 0 citations" badge, no older-works badge, no contributions list, and no problem/methods blocks (all empty sections are hidden, not rendered with empty containers)

#### Scenario: Incremental card is dimmed
- **WHEN** a paper has `impact_tier="incremental"` and is shown because the user opted into incremental tier
- **THEN** the card renders with reduced opacity and a muted "Incremental" badge; all content remains readable without interaction

#### Scenario: Paper with no tags
- **WHEN** a paper has empty `sub_domain_tags`
- **THEN** the tag area shows "general" (matching `ScoredPaper.sub_domain_display`)

#### Scenario: Published date is rendered as YYYY-MM-DD
- **WHEN** a paper with `published=2025-11-02T14:30:00Z` is rendered
- **THEN** the card shows `2025-11-02` next to the authors line (date only, no time, no timezone)

#### Scenario: Header badge cluster pins right regardless of present badges
- **WHEN** two cards are rendered side by side — one with just a tier badge and citation badge (no older-works badge), one with all three badges
- **THEN** both cards' badge clusters are right-aligned to the same edge, with identical gap spacing between adjacent badges, and the title fills the remaining left-side space

### Requirement: Citation count display

Each paper card SHALL ALWAYS render the paper's `citation_count` as a "📈 N citations" badge positioned inside the right-aligned header badge cluster, including the case where `N == 0`. Older-works papers (`paper_kind="older"`) SHALL additionally render a distinct "🔖 重要老作" badge so users can visually distinguish surfaced classics from fresh papers in the mixed list.

#### Scenario: Card shows citation badge
- **WHEN** a paper with `citation_count=320` is rendered
- **THEN** the card shows a "📈 320 citations" badge

#### Scenario: Zero-citation paper still shows a badge
- **WHEN** a brand-new paper with `citation_count=0` is rendered
- **THEN** the card shows a "📈 0 citations" badge (the badge is NOT suppressed at zero)

#### Scenario: Older-works paper shows both badges
- **WHEN** a paper with `paper_kind="older"` and `citation_count=1500` is rendered
- **THEN** the card shows both the "🔖 重要老作" badge and the "📈 1500 citations" badge, both inside the right-aligned header badge cluster
