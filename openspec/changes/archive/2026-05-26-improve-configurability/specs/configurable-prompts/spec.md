## ADDED Requirements

### Requirement: PromptsConfig model
A new `PromptsConfig` Pydantic model SHALL be defined with two fields:
- `system_prompt: Optional[str]` (default `None`)
- `user_message_template: Optional[str]` (default `None`)

`ScoringConfig` SHALL include a `prompts` field of type `PromptsConfig`.

#### Scenario: PromptsConfig with all fields omitted
- **WHEN** `config.yaml` has no `scoring.prompts` section
- **THEN** `PromptsConfig` is constructed with both fields as `None`, and the scorer uses its built-in default prompts

#### Scenario: PromptsConfig with partial override
- **WHEN** `config.yaml` sets only `scoring.prompts.system_prompt` and omits `user_message_template`
- **THEN** the custom system prompt is used, and the default user message template is used

### Requirement: Custom system prompt
When `prompts.system_prompt` is set to a non-empty string, the scorer SHALL use it as the `system` parameter in `messages.create()` instead of the hardcoded `SYSTEM_PROMPT`.

#### Scenario: Custom system prompt used
- **WHEN** `config.yaml` contains `scoring.prompts.system_prompt: "You are a paper reviewer. Score relevance 0-10."`
- **THEN** the API call's `system` parameter is set to `"You are a paper reviewer. Score relevance 0-10."`

#### Scenario: Empty system prompt falls back to default
- **WHEN** `config.yaml` contains `scoring.prompts.system_prompt: ""`
- **THEN** the scorer uses the hardcoded default `SYSTEM_PROMPT`

### Requirement: Custom user message template
When `prompts.user_message_template` is set to a non-empty string, the scorer SHALL use it to construct the user message for each batch. The template SHALL support `{paper_count}` and `{papers}` placeholders via `str.format()`.

#### Scenario: Custom user message template
- **WHEN** `config.yaml` contains a `user_message_template` with `{paper_count}` and `{papers}` placeholders
- **THEN** for each batch, the scorer formats the template with the actual paper count and formatted paper text

#### Scenario: User message template missing placeholders
- **WHEN** the template is set but does not contain `{paper_count}` or `{papers}`
- **THEN** the scorer SHALL still use the template (no error), just without substitution of the missing placeholder

#### Scenario: Default user message preserved
- **WHEN** `config.yaml` has no `scoring.prompts.user_message_template`
- **THEN** the user message matches the current hardcoded format: `"Please score the following N papers..."`

### Requirement: Default prompts preserved as module constants
The current hardcoded `SYSTEM_PROMPT` and user message format SHALL remain as module-level constants in `claude_scorer.py` and be used as defaults when config fields are `None` or empty.

#### Scenario: Defaults unchanged when config omitted
- **WHEN** a `ClaudeScorer` is constructed without any prompt configuration
- **THEN** it uses the exact same `SYSTEM_PROMPT` and user message format as before this change

### Requirement: Sub-domain descriptions included in default system prompt
The default `SYSTEM_PROMPT` SHALL continue to include the `SUB_DOMAIN_DESCRIPTIONS` text. When a custom system prompt is provided, sub-domain descriptions are NOT automatically injected — the user is responsible for including them if desired.

#### Scenario: Custom prompt without sub-domain descriptions
- **WHEN** a custom `system_prompt` is set that does not mention sub-domains
- **THEN** the API call uses the custom prompt as-is, without injecting `SUB_DOMAIN_DESCRIPTIONS`

#### Scenario: Default prompt includes sub-domain descriptions
- **WHEN** no custom system prompt is configured
- **THEN** the default system prompt includes the full sub-domain taxonomy description
