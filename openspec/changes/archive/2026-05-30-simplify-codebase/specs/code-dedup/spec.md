## ADDED Requirements

### Requirement: Database row-to-ScoredPaper conversion unified
`PaperDatabase` SHALL have exactly one method for converting a `papers` table row into a `ScoredPaper` instance. All other methods that need this conversion SHALL delegate to this single method.

#### Scenario: load_cached_papers delegates to _row_to_scored_paper
- **WHEN** `load_cached_papers` is called with a list of arxiv IDs
- **THEN** each row returned from the database is converted to `ScoredPaper` via `_row_to_scored_paper`, not via inline conversion logic

#### Scenario: list_papers uses _row_to_scored_paper
- **WHEN** `list_papers` is called with filters
- **THEN** each row is converted via `_row_to_scored_paper`

### Requirement: Notifier factory uses registry pattern
`create_notifiers_for_user` and `get_notifier_by_name` SHALL share a single registry mapping notifier names to their classes and config attributes. Adding a new notifier type SHALL require only a single entry in the registry, not modifications to both functions.

#### Scenario: Adding a new notifier type
- **WHEN** a developer adds a new notifier (e.g., Slack) to the registry
- **THEN** both `create_notifiers_for_user` and `get_notifier_by_name` automatically support it without additional code changes

#### Scenario: Enabled notifiers created via registry iteration
- **WHEN** `create_notifiers_for_user` is called with a `UserNotifyConfig`
- **THEN** the function iterates over the registry and instantiates each notifier whose sub-config has `enabled=True`

#### Scenario: get_notifier_by_name uses registry lookup
- **WHEN** `get_notifier_by_name("feishu", config)` is called
- **THEN** the function looks up `"feishu"` in the registry and returns the corresponding notifier instance
