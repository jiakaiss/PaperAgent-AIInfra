## ADDED Requirements

### Requirement: Citation count display

Each paper card SHALL render the paper's `citation_count` when it is greater than zero, formatted as a "📈 N citations" badge positioned near the impact-tier badge. Papers with `citation_count=0` (including legacy rows) SHALL render no citation badge. Older-works papers (`paper_kind="older"`) SHALL additionally render a distinct "🔖 重要老作" badge so users can visually distinguish surfaced classics from fresh papers in the mixed list.

#### Scenario: Card shows citation badge
- **WHEN** a paper with `citation_count=320` is rendered
- **THEN** the card shows a "📈 320 citations" badge

#### Scenario: Zero-citation paper shows no badge
- **WHEN** a brand-new paper with `citation_count=0` is rendered
- **THEN** no citation badge is shown

#### Scenario: Older-works paper shows both badges
- **WHEN** a paper with `paper_kind="older"` and `citation_count=1500` is rendered
- **THEN** the card shows both the "🔖 重要老作" badge and the "📈 1500 citations" badge

## MODIFIED Requirements

### Requirement: Paper card content

Each paper in the list SHALL render: title (linked to `abs_url`), first 3 authors + "et al." if more, Chinese summary (`summary_zh`), sub-domain tag chips, relevance score, quality score, total score, an impact-tier badge, a citation-count badge (when `citation_count > 0`), an "older works" badge (when `paper_kind="older"`), a bulleted list of `key_contributions` (omitted if empty), and short `problem_statement_zh` and `methods_zh` blocks (omitted if empty). The card visual treatment SHALL vary by `impact_tier`:
- `breakthrough` — highlighted border and prominent tier badge
- `solid` — standard styling with a neutral tier badge
- `incremental` — dimmed (reduced opacity) styling with a muted tier badge

#### Scenario: Full breakthrough card
- **WHEN** a paper with 6 authors, tags `(quantization, sparsity)`, relevance=8.5, quality=7.0, `impact_tier="breakthrough"`, `citation_count=120`, 2 key contributions, and non-empty zh problem/methods is rendered
- **THEN** the card shows: clickable title, "Author1, Author2, Author3 et al.", the Chinese summary, two tag chips, "R: 8.5", "Q: 7.0", "Total: 7.9", a "Breakthrough" badge, a "📈 120 citations" badge, a highlighted border, a bulleted list of the 2 contributions, and the problem and methods blocks

#### Scenario: Legacy paper with empty new fields
- **WHEN** a paper has empty `key_contributions`, empty `problem_statement_zh`, empty `methods_zh`, `citation_count=0`, `paper_kind="fresh"`, and `impact_tier="solid"` (default for legacy rows)
- **THEN** the card renders standard styling with a "Solid" badge, no citation badge, no older-works badge, no contributions list, and no problem/methods blocks (all empty sections are hidden, not rendered with empty containers)

#### Scenario: Incremental card is dimmed
- **WHEN** a paper has `impact_tier="incremental"` and is shown because the user opted into incremental tier
- **THEN** the card renders with reduced opacity and a muted "Incremental" badge; all content remains readable without interaction

#### Scenario: Paper with no tags
- **WHEN** a paper has empty `sub_domain_tags`
- **THEN** the tag area shows "general" (matching `ScoredPaper.sub_domain_display`)
