## MODIFIED Requirements

### Requirement: Subscription to UserConfig conversion
The system SHALL convert database subscriptions into UserConfig objects for pipeline processing, inheriting SMTP credentials from global email configuration and applying global thresholds. This conversion SHALL be implemented by a single reusable helper used by app startup, CLI startup, and runtime subscription creation. Since the static `users` list in config.yaml is removed, subscription-derived UserConfigs are the SOLE source of pipeline users.

#### Scenario: Subscription converted to UserConfig
- **WHEN** subscription is loaded from database
- **THEN** system creates UserConfig with: user_id=email, display_name=email, subscriptions.sub_domains=sub_domains array, notify.email.enabled=true, notify.email.recipients=[email], SMTP credentials (smtp_host, smtp_port, smtp_user, smtp_password, sender, use_tls) copied from AppConfig.email, and thresholds copied from global AppConfig.thresholds

#### Scenario: Multiple subscriptions converted
- **WHEN** 5 active subscriptions exist in database
- **THEN** system creates 5 UserConfig objects, each with SMTP credentials from global config and global thresholds

#### Scenario: Global email config missing
- **WHEN** subscription is loaded but AppConfig.email has enabled=false or missing credentials
- **THEN** system creates UserConfig with notify.email.enabled=false and logs warning "Global email config not configured, subscription user will not receive emails"

#### Scenario: Startup and runtime conversion are consistent
- **WHEN** a subscription is loaded at startup and another subscription is added at runtime with the same global email config and thresholds
- **THEN** both resulting UserConfig objects use the same conversion logic and equivalent email notifier fields and thresholds

#### Scenario: UserConfig has only email notifier
- **WHEN** subscription is converted to UserConfig
- **THEN** the resulting `UserConfig.notify` object SHALL contain only an `email` field; no wecom/feishu/dingtalk fields exist on the model

## ADDED Requirements

### Requirement: Global thresholds config replaces per-user thresholds
The system SHALL provide a top-level `thresholds` configuration section in `AppConfig` that defines `min_relevance`, `min_quality`, `top_n`, `min_tier`, and `per_sub_domain_top_n` shared by all subscription-derived users.

#### Scenario: Default thresholds
- **WHEN** `config.yaml` does not contain a `thresholds:` section
- **THEN** `AppConfig.thresholds` uses sensible defaults (min_relevance=6.0, min_quality=5.0, top_n=10, min_tier=solid)

#### Scenario: Configured thresholds applied to all subscribers
- **WHEN** `config.yaml` defines `thresholds.min_tier=breakthrough` and 3 active subscriptions exist
- **THEN** all 3 resulting UserConfig objects receive `min_tier=breakthrough`