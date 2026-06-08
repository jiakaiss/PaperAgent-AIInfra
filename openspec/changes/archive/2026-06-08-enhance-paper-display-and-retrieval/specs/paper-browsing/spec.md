## MODIFIED Requirements

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
