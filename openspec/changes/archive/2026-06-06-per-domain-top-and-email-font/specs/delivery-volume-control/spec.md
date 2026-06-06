## ADDED Requirements

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