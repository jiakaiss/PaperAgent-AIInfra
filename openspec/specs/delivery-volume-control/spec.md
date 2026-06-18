# delivery-volume-control Specification

## Purpose
TBD - created by archiving change improve-subscription-delivery-controls. Update Purpose after archive.
## Requirements
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

### Requirement: Per-sub-domain per-user paper limit
The system SHALL limit the number of papers selected per subscribed sub-domain per delivery cycle to a configurable maximum, independently of the user's overall delivery limit (`top_n`). Papers matching multiple subscribed sub-domains SHALL be deduplicated so that each unique paper is delivered at most once per cycle. When the user's subscriptions include `"all"`, the per-sub-domain limit SHALL NOT apply and the user's overall `top_n` SHALL be used directly.

#### Scenario: Per-domain split with dedup
- **WHEN** a user subscribes to sub-domains `quantization` and `distillation` with `per_sub_domain_top_n=20` and `top_n=200`
- **THEN** the daily digest includes up to 20 papers from each sub-domain (up to 40 before dedup, 20-40 after dedup), sorted by combined score

#### Scenario: Lower overall cap overrides per-domain total
- **WHEN** a user subscribes to 10 sub-domains with `per_sub_domain_top_n=20` and `top_n=50`
- **THEN** the daily digest includes at most 50 unique papers (because `top_n=50` caps the merged result)

#### Scenario: "All" subscription ignores per-domain limit
- **WHEN** a user subscribes to `["all"]` sub-domains
- **THEN** the per-sub-domain limit is not applied and the user receives at most `top_n` papers from the full pool

#### Scenario: Per-domain limit configurable
- **WHEN** a user's `thresholds.per_sub_domain_top_n` is set to a positive integer
- **THEN** the pipeline uses that value as the per-domain limit for that user

### Requirement: Email digest uses readable serif font
The email digest HTML SHALL use `Times New Roman` for English text content (paper titles, author names, URLs) and `Microsoft YaHei` for Chinese text content (Chinese summaries, interface labels). The `font-family` declaration SHALL provide fallbacks so that the rendering degrades gracefully on systems lacking these specific fonts.

#### Scenario: Email body uses dual-font fallback
- **WHEN** the email digest HTML is rendered
- **THEN** the `<body>` element SHALL include a `font-family` value of `'Times New Roman', 'Microsoft YaHei', '微软雅黑', serif` so that English text renders in Times New Roman and Chinese text renders in Microsoft YaHei

#### Scenario: Font change does not affect non-email notifiers
- **WHEN** a digest is sent via WeCom, Feishu, or DingTalk notifier
- **THEN** the message body SHALL NOT contain any HTML `font-family` markup related to the email font change

### Requirement: Older-works delivery thresholds

`ThresholdsConfig` SHALL include `older_works_per_digest` (int, default `0`) and `min_citations_for_older_works` (int, default `100`) fields. These thresholds SHALL be shared by all subscription users (inherited from the global `ThresholdsConfig` at subscription-load time, matching the existing pattern). When `older_works_per_digest` is `0`, the older-works track is fully disabled and no older section appears in any digest (pre-change behavior).

#### Scenario: Default disables older works
- **WHEN** `config.yaml` omits the new threshold fields
- **THEN** `older_works_per_digest=0` and `min_citations_for_older_works=100`, and no older-works section appears in digests

#### Scenario: Configured older-works count
- **WHEN** configuration sets `older_works_per_digest=3`
- **THEN** each subscription user's digest includes up to 3 older works in a dedicated section

#### Scenario: Thresholds inherited at load time
- **WHEN** the app starts and loads subscriptions into `AppConfig.users`
- **THEN** each user's `UserThresholdsConfig` carries the global `older_works_per_digest` and `min_citations_for_older_works` values (consistent with the existing `min_tier` inheritance pattern)

