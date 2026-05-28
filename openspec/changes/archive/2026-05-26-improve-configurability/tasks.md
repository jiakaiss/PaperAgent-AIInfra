## 1. Config Model Updates

- [x] 1.1 Add `PromptsConfig` Pydantic model with `system_prompt: Optional[str] = None` and `user_message_template: Optional[str] = None` fields
- [x] 1.2 Extend `ScoringConfig` with new fields: `api_key`, `base_url`, `max_tokens`, `temperature`, `tool_choice`, `abstract_max_length`, `relevance_weight`, `quality_weight`, `prompts`
- [x] 1.3 Add Pydantic validator on `ScoringConfig` that emits a warning when `relevance_weight + quality_weight` is not approximately 1.0
- [x] 1.4 Add tests for new `ScoringConfig` fields: defaults, custom values, env-var interpolation for `api_key`, weight validation warning

## 2. Score Weights Model

- [x] 2.1 Add `ScoreWeights` dataclass in `models.py` with `relevance: float` and `quality: float` fields, and a `from_scoring_config(config)` classmethod
- [x] 2.2 Add `compute_total_score(paper: ScoredPaper, weights: ScoreWeights) -> float` function in `models.py`
- [x] 2.3 Update `sort_by_score` to accept optional `weights: ScoreWeights` parameter, using `compute_total_score` when provided
- [x] 2.4 Keep `ScoredPaper.total_score` property unchanged (uses default 0.6/0.4 weights for backward compat)
- [x] 2.5 Add tests for `ScoreWeights`, `compute_total_score`, and `sort_by_score` with custom weights

## 3. Scorer Updates

- [x] 3.1 Update `ClaudeScorer.__init__` to accept a `ScoringConfig` object and extract all new fields (`api_key`, `base_url`, `max_tokens`, `temperature`, `tool_choice`, `abstract_max_length`, `prompts`)
- [x] 3.2 Pass `api_key` and `base_url` to `anthropic.Anthropic()` constructor
- [x] 3.3 Use configurable `max_tokens` and `temperature` in `messages.create()` calls (omit `temperature` when `None`)
- [x] 3.4 Build `tool_choice` parameter from config string: `"auto"` → `{"type": "auto"}`, `"tool"` → `{"type": "tool", "name": "score_papers"}`
- [x] 3.5 Use configurable `abstract_max_length` in `_format_papers` instead of hardcoded `800`
- [x] 3.6 Use `prompts.system_prompt` if set (non-empty), otherwise fall back to module-level `SYSTEM_PROMPT` constant
- [x] 3.7 Use `prompts.user_message_template` if set (non-empty), formatting with `{paper_count}` and `{papers}` placeholders; otherwise fall back to current hardcoded user message
- [x] 3.8 Keep module-level `SYSTEM_PROMPT` and `SUB_DOMAIN_DESCRIPTIONS` constants unchanged as defaults
- [x] 3.9 Add tests for `ClaudeScorer` with custom config: custom api_key/base_url passed to client, custom max_tokens/temperature in API call, custom prompts used, defaults preserved when config omitted

## 4. Pipeline Wiring

- [x] 4.1 Update `Pipeline.__init__` to pass `config.scoring` to `ClaudeScorer` constructor
- [x] 4.2 Update `Pipeline._run_for_user` to construct `ScoreWeights` from `config.scoring` and pass to `sort_by_score`
- [x] 4.3 Add integration test: pipeline with custom scoring config produces correctly weighted results

## 5. Documentation & Config Example

- [x] 5.1 Update `config.example.yaml` to include all new `ScoringConfig` fields with explanatory comments
- [x] 5.2 Update `CLAUDE.md` to document the new configurable fields and their defaults
- [x] 5.3 Add inline docstrings to `PromptsConfig` and new `ScoringConfig` fields explaining usage and defaults

## 6. Verification

- [x] 6.1 Run full test suite (`pytest tests/ -v`) and fix any failures — **65/65 passed**
- [x] 6.2 Run linter (`ruff check src/ tests/`) and fix any issues — fixed 23 auto-fixable issues in changed files; 7 pre-existing E501 issues remain in prompt string literals (unchanged content)
- [x] 6.3 Run formatter (`ruff format src/ tests/`) — 6 files reformatted
- [ ] 6.4 Manual verification: run `paper-agent run --dry-run -c config.yaml` with a config that uses custom prompts and weights, confirm output matches expectations — requires `ANTHROPIC_API_KEY` and network; left for the user
