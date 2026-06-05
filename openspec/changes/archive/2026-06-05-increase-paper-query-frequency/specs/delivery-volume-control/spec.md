## MODIFIED Requirements

### Requirement: Configurable daemon query frequency
The system SHALL allow operators to configure paper ingestion frequency independently from user-facing digest delivery. For low paper-volume deployments, the daemon SHALL support a frequent ingest interval that fetches, scores, and caches papers without sending notifications, while daily digest delivery remains scheduled at the configured digest time.

#### Scenario: Frequent ingest configured
- **WHEN** schedule configuration sets `ingest_interval_minutes=360`
- **THEN** the daemon runs the ingest job approximately every 6 hours

#### Scenario: Ingest does not notify users
- **WHEN** the ingest job discovers and caches new scored papers
- **THEN** the job does not call notifiers and does not mark papers as sent

#### Scenario: Daily digest time configured
- **WHEN** schedule configuration sets `digest_hour=9` and `digest_minute=0`
- **THEN** the daemon sends the user-facing digest once per day at 09:00 in the configured timezone

#### Scenario: Invalid ingest interval rejected
- **WHEN** schedule configuration sets `ingest_interval_minutes` to a non-positive value
- **THEN** configuration validation rejects the setting with a clear error

### Requirement: Fetch deduplication protects frequent runs
The pipeline SHALL continue using the shared paper score cache and per-user sent-paper deduplication when daemon frequency is increased.

#### Scenario: Frequent run sees cached papers
- **WHEN** the daemon ingest job runs multiple times per day and arXiv returns a paper already present in the `papers` cache
- **THEN** the pipeline loads the cached score instead of scoring that paper again

#### Scenario: Frequent run discovers new paper
- **WHEN** a frequent ingest job returns an arXiv paper that is not present in the `papers` cache
- **THEN** the pipeline scores and caches that paper without sending it immediately

#### Scenario: Daily digest sees already-sent paper
- **WHEN** a paper was already sent to a user in an earlier digest
- **THEN** later daily digest runs do not send that same paper to the same user again
