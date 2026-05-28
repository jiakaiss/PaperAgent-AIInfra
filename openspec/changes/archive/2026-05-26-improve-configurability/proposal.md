## Why

The project has too many hardcoded values scattered across source files. Users cannot switch LLM providers (e.g., use a self-hosted proxy or non-Anthropic endpoint), tune API parameters, or customize scoring prompts without editing Python source code. This makes the tool inflexible for teams that want to experiment with different models, adjust scoring criteria, or deploy behind an API gateway — all common needs for an AI Infra paper recommendation tool.

## What Changes

- Add `api_key`, `base_url`, `max_tokens`, `temperature` fields to `ScoringConfig` so LLM API connection and generation parameters are configurable via `config.yaml` (with env-var interpolation for secrets).
- Add a `PromptsConfig` section to `ScoringConfig` that exposes the system prompt, user message template, and scoring rubric as configurable strings, with sensible defaults matching the current hardcoded values.
- Wire the new config fields through `Pipeline` → `ClaudeScorer` so they actually take effect at runtime.
- Make `tool_choice` and `abstract_max_length` (currently `800`) configurable in `ScoringConfig`.
- Add `score_weights` (`relevance_weight`, `quality_weight`) to `ScoringConfig` so the `0.6/0.4` formula in `ScoredPaper.total_score` is no longer hardcoded in `models.py`.
- Update `config.example.yaml` to document every new field with comments.

## Capabilities

### New Capabilities
- `llm-api-config`: Configurable LLM API connection (api_key, base_url) and generation parameters (max_tokens, temperature, tool_choice) via `ScoringConfig`.
- `configurable-prompts`: Configurable system prompt, user message template, and scoring rubric via `PromptsConfig` nested under `ScoringConfig`, with defaults preserved from current hardcoded values.
- `configurable-scoring-weights`: Configurable relevance/quality weight ratio for `ScoredPaper.total_score`.

### Modified Capabilities

## Impact

- **`src/paper_agent/config.py`**: New fields on `ScoringConfig`, new `PromptsConfig` model.
- **`src/paper_agent/scorer/claude_scorer.py`**: Accept and use all new config fields; move hardcoded constants to defaults that are overridden by config.
- **`src/paper_agent/pipeline.py`**: Pass new config fields to `ClaudeScorer` constructor.
- **`src/paper_agent/models.py`**: `ScoredPaper.total_score` must accept weights instead of using hardcoded `0.6/0.4`.
- **`config.example.yaml`**: Document all new fields.
- **`tests/`**: New tests for config validation and scorer behavior with custom prompts/weights.
- **Backward compatible**: All new fields have defaults matching current hardcoded values — existing `config.yaml` files work unchanged.
