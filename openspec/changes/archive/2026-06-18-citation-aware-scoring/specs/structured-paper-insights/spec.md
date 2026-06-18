## ADDED Requirements

The `ScoredPaper` model SHALL include `citation_count: int = 0`, `influential_citation_count: int = 0`, `citations_updated_at: str | None = None`, `citation_count_at_score: int | None = None`, and `paper_kind: Literal["fresh", "older"] = "fresh"` fields. These fields SHALL be populated from the `papers` table on read (not by the LLM scorer) and SHALL be persisted by `cache_papers`. The LLM `SCORE_TOOL` schema SHALL NOT be modified to request citation data — citations come exclusively from the `CitationProvider`, never from the model. `citation_count_at_score` SHALL be set to the then-current `citation_count` on every score write.

#### Scenario: Cached paper round-trips citation fields
- **WHEN** a paper with `citation_count=150`, `influential_citation_count=12`, `paper_kind="older"` is written via `cache_papers` and re-read via `load_cached_papers`
- **THEN** the re-read `ScoredPaper` has `citation_count=150`, `influential_citation_count=12`, `paper_kind="older"`, and a non-null `citations_updated_at`

#### Scenario: Legacy paper defaults
- **WHEN** a legacy row with NULL citation columns is loaded
- **THEN** the `ScoredPaper` has `citation_count=0`, `influential_citation_count=0`, `citations_updated_at=None`, `paper_kind="fresh"`

#### Scenario: Scorer schema unchanged
- **WHEN** the Claude scorer processes a batch of papers
- **THEN** the `SCORE_TOOL` JSON schema does not include any citation-related output field

### Requirement: Scorer accepts citation context for re-scoring

The scorer's user-message rendering SHALL accept an optional citation-context snippet per paper. When a paper is being dynamically re-scored (citation growth past threshold), the rendered user message SHALL include the paper's current `citation_count` and `influential_citation_count` as context (e.g. a line stating the paper has N citations, M influential), so the LLM can weigh real-world impact evidence when re-judging `relevance_score`, `quality_score`, and `impact_tier`. For first-time scoring (no citation data yet, or `citations.enabled=false`), no citation context SHALL be rendered — the message is identical to the pre-change first-score message. The `SCORE_TOOL` output schema SHALL remain unchanged in both cases.

#### Scenario: Re-score message includes citation context
- **WHEN** the scorer re-scores a paper with `citation_count=320, influential_citation_count=12`
- **THEN** the user message sent to Claude contains both numbers as context

#### Scenario: First-score message has no citation context
- **WHEN** the scorer scores a brand-new paper with `citation_count=0` (or citations disabled)
- **THEN** the user message contains no citation-context line, matching pre-change first-score behavior

#### Scenario: Output schema identical for both paths
- **WHEN** comparing the `SCORE_TOOL` JSON schema used for first-scoring vs re-scoring
- **THEN** the two schemas are byte-identical
