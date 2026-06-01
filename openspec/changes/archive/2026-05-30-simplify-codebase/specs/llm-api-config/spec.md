## MODIFIED Requirements

### Requirement: Pipeline wires config to scorer
`Pipeline.__init__` SHALL pass the full `ScoringConfig` object to `ClaudeScorer`. Internally, `ClaudeScorer` SHALL resolve parameters by merging explicit kwargs over config values using a dict-merge pattern rather than per-field ternary chains. The constructor body SHALL NOT exceed 20 lines of resolution logic.

#### Scenario: All scoring config fields reach the scorer
- **WHEN** a pipeline is constructed with a config that sets `api_key`, `base_url`, `max_tokens`, `temperature`, `tool_choice`, and `abstract_max_length`
- **THEN** the `ClaudeScorer` instance uses all of these values when making API calls

#### Scenario: Constructor uses merge-based resolution
- **WHEN** `ClaudeScorer.__init__` is called with a `ScoringConfig` and optional kwargs
- **THEN** parameters are resolved by overlaying non-None kwargs onto config values, not by repeating `x if x is not None else config.x` for each field
