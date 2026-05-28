## Context

The `paper_agent` project currently hardcodes LLM API connection details (API key source, base URL), generation parameters (`max_tokens`, `temperature`, `tool_choice`), all scoring prompts (system prompt, user message template, scoring rubric, sub-domain descriptions), and the score weighting formula (`0.6 * relevance + 0.4 * quality`). These are scattered across `claude_scorer.py`, `models.py`, and `pipeline.py` as module-level constants and magic numbers.

The config system (`config.py`) already supports env-var interpolation (`${ENV_VAR}`), which provides a secure way to handle API keys in config files.

Constraints:
- Must remain fully backward compatible — existing `config.yaml` files must work unchanged.
- The `ScoredPaper` dataclass is `frozen=True`, so weights cannot be stored as instance fields without changing its construction site.
- The `anthropic` Python SDK accepts `api_key` and `base_url` as constructor args, and `max_tokens`/`temperature`/`tool_choice` per-request.

## Goals / Non-Goals

**Goals:**
- Make API connection (`api_key`, `base_url`) configurable via `config.yaml` with env-var interpolation for secrets.
- Make generation parameters (`max_tokens`, `temperature`, `tool_choice`, `abstract_max_length`) configurable.
- Make all prompts (system prompt, user message template) configurable with defaults matching current hardcoded values.
- Make score weighting (`relevance_weight`, `quality_weight`) configurable.
- Keep the codebase clean and readable — no sprawl of config objects.

**Non-Goals:**
- Multi-provider support (OpenAI, Gemini, etc.) — this change is Anthropic-only. The config fields are provider-agnostic in naming but only the `ClaudeScorer` is wired.
- Custom sub-domain taxonomy or tool schema via config — the 14 sub-domains and `SCORE_TOOL` JSON schema remain in source code. These are structural, not user-tunable.
- Per-user prompt overrides — prompts are global (shared with the scorer across all users).
- Hot-reloading config changes at runtime.

## Decisions

### 1. Prompt storage: inline strings in config.yaml with defaults from source

**Decision**: Prompts are configured as string fields in `config.yaml` under `scoring.prompts`. Default values are defined as module-level constants in `claude_scorer.py` (same as today) and used when the config field is `None` or empty.

**Alternatives considered:**
- External `.txt`/`.md` files referenced by path — more flexible for long prompts, but adds file management complexity and makes config non-self-contained.
- Jinja2 templating for user message — overkill for the single `{paper_count}` and `{papers}` substitution needed.

**Rationale**: The system prompt is ~30 lines — small enough to inline in YAML. Using `None` as default means omitting the field uses the hardcoded default, preserving backward compatibility. The user message template uses simple `str.format()` with `{paper_count}` and `{papers}` placeholders.

### 2. `ScoredPaper.total_score` becomes a function, not a property

**Decision**: Replace the `total_score` property with a module-level function `compute_total_score(paper, weights)` that takes a `ScoreWeights` dataclass. The `sort_by_score` function also accepts optional weights. `ScoredPaper.total_score` remains as a property using default weights for backward compat.

**Alternatives considered:**
- Store weights on `ScoredPaper` — would require changing every construction site (scorer, database load) to pass weights, which is noise.
- Global/module-level mutable weights — fragile, breaks under testing.

**Rationale**: Weights are a pipeline-level concern, not a per-paper concern. Passing them explicitly at sort/filter time keeps `ScoredPaper` clean. The property fallback avoids breaking any code that reads `.total_score` without weights.

### 3. New `ScoringConfig` fields are all optional with current-behavior defaults

**Decision**: Every new field defaults to the current hardcoded value:
- `api_key: Optional[str] = None` (falls back to `ANTHROPIC_API_KEY` env var via SDK)
- `base_url: Optional[str] = None` (falls back to SDK default endpoint)
- `max_tokens: int = 4096`
- `temperature: Optional[float] = None` (SDK default — no temperature set)
- `tool_choice: str = "auto"`
- `abstract_max_length: int = 800`
- `relevance_weight: float = 0.6`
- `quality_weight: float = 0.4`
- `prompts: PromptsConfig` (all fields `Optional[str] = None`)

**Rationale**: Existing configs with only `model` and `batch_size` work identically. Users opt into new fields incrementally.

### 4. Pipeline passes a `ScoringConfig` object to scorer, not individual kwargs

**Decision**: `ClaudeScorer.__init__` accepts a `ScoringConfig` object directly (in addition to the existing individual kwargs for backward compat). Pipeline passes `config.scoring`.

**Alternatives considered:**
- Explode all fields as kwargs — creates a 10-parameter constructor, hard to maintain.

**Rationale**: The scorer is tightly coupled to scoring config anyway. Accepting the object keeps the constructor clean and makes adding future fields a non-event.

## Risks / Trade-offs

- **[Prompt misconfiguration]** A broken system prompt silently produces bad scores. → Mitigation: validate that `system_prompt` is non-empty if provided; log a warning if prompts are customized.
- **[Weight validation]** Weights that don't sum to 1.0 could confuse users. → Mitigation: add a Pydantic validator warning (not error) when `relevance_weight + quality_weight != 1.0`. Don't enforce — some users may want raw sums.
- **[API key in config file]** Storing API keys in YAML is less secure than env vars. → Mitigation: document that `${ANTHROPIC_API_KEY}` interpolation is preferred; never log the resolved `api_key` value.
- **[Backward compat on `total_score`]** Code that reads `.total_score` as a property still works with default weights, but the property cannot reflect pipeline-configured weights. → Mitigation: `sort_by_score` accepts weights; callers who need weighted sort use the function form.
