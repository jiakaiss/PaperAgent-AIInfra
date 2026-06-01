## Requirements

### Requirement: ClaudeScorer constructor uses merge-based parameter resolution
`ClaudeScorer.__init__` SHALL resolve its parameters by merging explicit kwargs over config values, rather than using per-field ternary expressions. The external interface (config + optional kwargs) SHALL remain unchanged.

#### Scenario: Config-only construction
- **WHEN** `ClaudeScorer(config=scoring_config)` is called with no kwargs
- **THEN** all attributes (model, batch_size, api_key, etc.) are taken from `scoring_config`

#### Scenario: Kwargs override config values
- **WHEN** `ClaudeScorer(config=scoring_config, api_key="custom-key")` is called
- **THEN** `api_key` is `"custom-key"` and all other attributes come from `scoring_config`

#### Scenario: No config, only kwargs
- **WHEN** `ClaudeScorer(api_key="key", model="claude-haiku-4-5")` is called with no config
- **THEN** provided kwargs are used and unspecified attributes fall back to hardcoded defaults

### Requirement: SafeFormatter defined at module level
The `_SafeFormatter` class used for partial template substitution SHALL be defined at module level, not inline inside a method.

#### Scenario: SafeFormatter accessible for testing
- **WHEN** test code imports `_SafeFormatter` from `paper_agent.scorer.claude_scorer`
- **THEN** the class is available and can be instantiated directly

#### Scenario: _build_user_message uses module-level SafeFormatter
- **WHEN** `_build_user_message` encounters a template with unknown placeholders
- **THEN** it uses the module-level `_SafeFormatter` class (not an inline definition) to perform substitution
