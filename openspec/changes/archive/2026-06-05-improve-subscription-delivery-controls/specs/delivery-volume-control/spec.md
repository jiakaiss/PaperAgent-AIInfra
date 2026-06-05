## ADDED Requirements

### Requirement: Configurable subscription delivery count
The system SHALL allow operators to configure the default maximum number of papers delivered per digest for subscription-created users. The default value for subscription-created users SHALL be 10 papers when not explicitly configured.

#### Scenario: Default subscription top_n
- **WHEN** a web subscription is converted into a runtime `UserConfig` without an explicit configured delivery count
- **THEN** the resulting user's `thresholds.top_n` is 10

#### Scenario: Configured subscription top_n
- **WHEN** configuration sets a subscription default delivery count to 15
- **THEN** web subscription users created from database rows use `thresholds.top_n=15`

#### Scenario: Config-file user override preserved
- **WHEN** a user is explicitly defined in config with `thresholds.top_n=5`
- **THEN** pipeline delivery for that user remains limited to 5 papers regardless of subscription default delivery count

### Requirement: Configurable daemon query frequency
The system SHALL allow operators to configure daemon pipeline frequency using either existing cron-style daily scheduling or a new interval-based schedule.

#### Scenario: Existing cron schedule preserved
- **WHEN** schedule configuration uses cron hour and minute without interval mode
- **THEN** the daemon runs with the same daily cron behavior as before

#### Scenario: Interval schedule configured
- **WHEN** schedule configuration sets interval mode with an interval of 6 hours
- **THEN** the daemon runs the paper pipeline approximately every 6 hours

#### Scenario: Invalid interval rejected
- **WHEN** schedule configuration sets interval mode with a non-positive interval
- **THEN** configuration validation rejects the setting with a clear error

### Requirement: Fetch deduplication protects frequent runs
The pipeline SHALL continue using the shared paper score cache and per-user sent-paper deduplication when daemon frequency is increased.

#### Scenario: Frequent run sees cached papers
- **WHEN** the daemon runs multiple times per day and arXiv returns a paper already present in the `papers` cache
- **THEN** the pipeline loads the cached score instead of scoring that paper again

#### Scenario: Frequent run sees already-sent paper
- **WHEN** a paper was already sent to a user in an earlier run
- **THEN** later runs do not send that same paper to the same user again
