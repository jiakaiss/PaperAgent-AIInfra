## Requirements

### Requirement: Score weights configurable
`ScoringConfig` SHALL include `relevance_weight` (`float`, default `0.6`) and `quality_weight` (`float`, default `0.4`) fields. These weights SHALL be used when computing total scores for sorting and filtering.

#### Scenario: Default weights preserved
- **WHEN** `config.yaml` has no weight fields
- **THEN** total score is computed as `relevance * 0.6 + quality * 0.4` (current behavior)

#### Scenario: Custom weights
- **WHEN** `config.yaml` contains `scoring.relevance_weight: 0.8` and `scoring.quality_weight: 0.2`
- **THEN** total score is computed as `relevance * 0.8 + quality * 0.2`

### Requirement: ScoreWeights dataclass
A `ScoreWeights` dataclass SHALL be defined with `relevance: float` and `quality: float` fields. It SHALL be constructable from `ScoringConfig`.

#### Scenario: Construct from config
- **WHEN** `ScoreWeights` is constructed from a `ScoringConfig` with `relevance_weight=0.7, quality_weight=0.3`
- **THEN** the resulting `ScoreWeights` has `relevance=0.7, quality=0.3`

### Requirement: Weighted total score function
A module-level function `compute_total_score(paper: ScoredPaper, weights: ScoreWeights) -> float` SHALL compute the weighted total score. The existing `ScoredPaper.total_score` property SHALL remain and use default weights (`0.6, 0.4`) for backward compatibility.

#### Scenario: Function with custom weights
- **WHEN** `compute_total_score(paper, ScoreWeights(0.8, 0.2))` is called on a paper with `relevance=8, quality=6`
- **THEN** the result is `8 * 0.8 + 6 * 0.2 = 7.6`

#### Scenario: Property uses default weights
- **WHEN** `paper.total_score` is accessed on a paper with `relevance=8, quality=6`
- **THEN** the result is `8 * 0.6 + 6 * 0.4 = 7.2` (unchanged from current behavior)

### Requirement: sort_by_score accepts weights
The `sort_by_score` function SHALL accept an optional `weights: ScoreWeights` parameter. When provided, sorting uses `compute_total_score` with those weights. When `None`, it uses the default `total_score` property.

#### Scenario: Sort with custom weights
- **WHEN** `sort_by_score(papers, ScoreWeights(1.0, 0.0))` is called
- **THEN** papers are sorted by `relevance_score` only (quality ignored)

#### Scenario: Sort without weights uses defaults
- **WHEN** `sort_by_score(papers)` is called without weights
- **THEN** papers are sorted by the default `total_score` property (current behavior)

### Requirement: Pipeline passes weights to sort
The pipeline's `_run_for_user` method SHALL construct `ScoreWeights` from `config.scoring` and pass it to `sort_by_score` when sorting papers for each user.

#### Scenario: Pipeline uses configured weights for sorting
- **WHEN** the pipeline runs with `scoring.relevance_weight: 0.9` and `scoring.quality_weight: 0.1`
- **THEN** per-user paper sorting uses `0.9/0.1` weighting

### Requirement: Weight validation warning
`ScoringConfig` SHALL emit a warning (not an error) via Pydantic validator when `relevance_weight + quality_weight` is not approximately equal to `1.0` (tolerance `0.01`).

#### Scenario: Weights don't sum to 1
- **WHEN** `config.yaml` sets `relevance_weight: 0.8` and `quality_weight: 0.8`
- **THEN** a warning is logged but the config is accepted

#### Scenario: Weights sum to 1
- **WHEN** `config.yaml` sets `relevance_weight: 0.7` and `quality_weight: 0.3`
- **THEN** no warning is emitted
