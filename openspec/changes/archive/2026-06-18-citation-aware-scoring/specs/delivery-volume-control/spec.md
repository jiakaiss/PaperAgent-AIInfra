## ADDED Requirements

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
