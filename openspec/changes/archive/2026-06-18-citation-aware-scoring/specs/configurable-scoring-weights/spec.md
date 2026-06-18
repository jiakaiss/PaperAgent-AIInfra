## ADDED Requirements

### Requirement: Citation weight configurable

`ScoringConfig` SHALL include a `citation_weight` field (`float`, default `0.0`). When `citations.enabled` is `true` and `citation_weight > 0.0`, per-user ranking SHALL incorporate the citation signal as specified in the `citation-signal` capability. A warning SHALL be logged (not an error) when `relevance_weight + quality_weight + citation_weight` is not approximately `1.0` (tolerance `0.01`). When `citation_weight` is `0.0` (the default), ranking SHALL be identical to pre-change behavior regardless of the `citations.enabled` flag — citation integration is opt-in.

#### Scenario: Default weight preserves old ranking
- **WHEN** `config.yaml` has no `citation_weight` field
- **THEN** `ScoringConfig.citation_weight` is `0.0` and ranking uses only `relevance_weight` and `quality_weight` (current behavior)

#### Scenario: Custom citation weight
- **WHEN** `config.yaml` contains `scoring.citation_weight: 0.3` and `citations.enabled: true`
- **THEN** per-user sorting incorporates the citation signal with weight `0.3`

#### Scenario: Weights don't sum to 1 warns
- **WHEN** `config.yaml` sets `relevance_weight: 0.6`, `quality_weight: 0.4`, `citation_weight: 0.3`
- **THEN** a warning is logged but the config is accepted

### Requirement: ScoreWeights dataclass carries citation

The `ScoreWeights` dataclass SHALL include a `citation: float` field (default `0.0`) alongside the existing `relevance` and `quality` fields. It SHALL be constructable from `ScoringConfig`, reading `citation_weight` into `citation`.

#### Scenario: Construct from config with citation weight
- **WHEN** `ScoreWeights` is constructed from a `ScoringConfig` with `relevance_weight=0.5, quality_weight=0.3, citation_weight=0.2`
- **THEN** the resulting `ScoreWeights` has `relevance=0.5, quality=0.3, citation=0.2`

## MODIFIED Requirements

### Requirement: Weighted total score function

A module-level function `compute_total_score(paper: ScoredPaper, weights: ScoreWeights) -> float` SHALL compute the weighted total score as `relevance * weights.relevance + quality * weights.quality`. The citation signal SHALL NOT be folded into `compute_total_score` — it is applied as a separate sort key after `total_score` (tier first, then `total_score`, then citation component), so that `total_score` retains its documented meaning and existing display behavior. The existing `ScoredPaper.total_score` property SHALL remain and use default weights (`0.6, 0.4`) for backward compatibility.

#### Scenario: Function with custom weights
- **WHEN** `compute_total_score(paper, ScoreWeights(relevance=0.8, quality=0.2, citation=0.0))` is called on a paper with `relevance=8, quality=6`
- **THEN** the result is `8 * 0.8 + 6 * 0.2 = 7.6`

#### Scenario: Property uses default weights
- **WHEN** `paper.total_score` is accessed on a paper with `relevance=8, quality=6`
- **THEN** the result is `8 * 0.6 + 6 * 0.4 = 7.2` (unchanged from current behavior)

#### Scenario: Citation weight does not inflate total_score
- **WHEN** `compute_total_score(paper, ScoreWeights(relevance=0.5, quality=0.3, citation=0.2))` is called on a paper with `relevance=8, quality=6, citation_count=200`
- **THEN** the result equals `8 * 0.5 + 6 * 0.3 = 5.8` (citation is not added; it sorts separately)
