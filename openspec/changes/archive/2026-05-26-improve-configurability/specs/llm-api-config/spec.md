## ADDED Requirements

### Requirement: API key configurable via config.yaml
`ScoringConfig` SHALL include an `api_key` field (`Optional[str]`, default `None`). When set, the value SHALL be passed to the Anthropic client constructor. When `None`, the client SHALL fall back to the `ANTHROPIC_API_KEY` environment variable (SDK default behavior). The field SHALL support `${ENV_VAR}` interpolation.

#### Scenario: API key set in config
- **WHEN** `config.yaml` contains `scoring.api_key: "sk-ant-..."` and the pipeline runs
- **THEN** the Anthropic client is constructed with `api_key="sk-ant-..."` and API calls use this key

#### Scenario: API key via env var interpolation
- **WHEN** `config.yaml` contains `scoring.api_key: "${MY_KEY}"` and `MY_KEY=sk-ant-xxx` is set in the environment
- **THEN** the Anthropic client is constructed with `api_key="sk-ant-xxx"`

#### Scenario: API key omitted falls back to env var
- **WHEN** `config.yaml` has no `scoring.api_key` field and `ANTHROPIC_API_KEY` is set in the environment
- **THEN** the Anthropic client reads the key from the environment variable (current behavior preserved)

### Requirement: Base URL configurable via config.yaml
`ScoringConfig` SHALL include a `base_url` field (`Optional[str]`, default `None`). When set, the value SHALL be passed to the Anthropic client constructor as `base_url`. When `None`, the SDK default endpoint is used.

#### Scenario: Custom base URL for API proxy
- **WHEN** `config.yaml` contains `scoring.base_url: "https://proxy.example.com/v1"`
- **THEN** all API calls are routed to `https://proxy.example.com/v1` instead of the default Anthropic endpoint

#### Scenario: Base URL omitted uses default endpoint
- **WHEN** `config.yaml` has no `scoring.base_url` field
- **THEN** the Anthropic client uses its default endpoint (current behavior preserved)

### Requirement: max_tokens configurable
`ScoringConfig` SHALL include a `max_tokens` field (`int`, default `4096`). This value SHALL be used as the `max_tokens` parameter in every `messages.create()` call.

#### Scenario: Custom max_tokens value
- **WHEN** `config.yaml` contains `scoring.max_tokens: 8192`
- **THEN** each API call to score papers uses `max_tokens=8192`

#### Scenario: Default max_tokens preserved
- **WHEN** `config.yaml` has no `scoring.max_tokens` field
- **THEN** each API call uses `max_tokens=4096` (current hardcoded value)

### Requirement: temperature configurable
`ScoringConfig` SHALL include a `temperature` field (`Optional[float]`, default `None`). When set, it SHALL be passed as the `temperature` parameter in `messages.create()`. When `None`, no temperature parameter is sent (SDK default).

#### Scenario: Custom temperature
- **WHEN** `config.yaml` contains `scoring.temperature: 0.3`
- **THEN** each API call includes `temperature=0.3`

#### Scenario: Temperature omitted
- **WHEN** `config.yaml` has no `scoring.temperature` field
- **THEN** no `temperature` parameter is passed to the API (SDK default behavior)

### Requirement: tool_choice configurable
`ScoringConfig` SHALL include a `tool_choice` field (`str`, default `"auto"`). The value SHALL be used as the `tool_choice` parameter in `messages.create()`.

#### Scenario: Force tool use
- **WHEN** `config.yaml` contains `scoring.tool_choice: "tool"`
- **THEN** each API call uses `tool_choice={"type": "tool", "name": "score_papers"}`

#### Scenario: Default tool_choice preserved
- **WHEN** `config.yaml` has no `scoring.tool_choice` field
- **THEN** each API call uses `tool_choice={"type": "auto"}` (current behavior)

### Requirement: abstract_max_length configurable
`ScoringConfig` SHALL include an `abstract_max_length` field (`int`, default `800`). The scorer SHALL truncate paper abstracts to this many characters when formatting prompts.

#### Scenario: Custom abstract length
- **WHEN** `config.yaml` contains `scoring.abstract_max_length: 1200`
- **THEN** each paper's abstract is truncated to 1200 characters in the prompt

#### Scenario: Default abstract length preserved
- **WHEN** `config.yaml` has no `scoring.abstract_max_length` field
- **THEN** abstracts are truncated to 800 characters (current hardcoded value)

### Requirement: Pipeline wires config to scorer
`Pipeline.__init__` SHALL pass the full `ScoringConfig` object to `ClaudeScorer`, not just `model` and `batch_size`.

#### Scenario: All scoring config fields reach the scorer
- **WHEN** a pipeline is constructed with a config that sets `api_key`, `base_url`, `max_tokens`, `temperature`, `tool_choice`, and `abstract_max_length`
- **THEN** the `ClaudeScorer` instance uses all of these values when making API calls
