## MODIFIED Requirements

### Requirement: Subscription to UserConfig conversion
The system SHALL convert database subscriptions into UserConfig objects for pipeline processing, inheriting SMTP credentials from global email configuration. This conversion SHALL be implemented by a single reusable helper used by app startup, CLI startup, and runtime subscription creation.

#### Scenario: Subscription converted to UserConfig
- **WHEN** subscription is loaded from database
- **THEN** system creates UserConfig with: user_id=email, display_name=email, subscriptions.sub_domains=sub_domains array, notify.email.enabled=true, notify.email.recipients=[email], and SMTP credentials (smtp_host, smtp_port, smtp_user, smtp_password, sender, use_tls) copied from AppConfig.email

#### Scenario: Multiple subscriptions converted
- **WHEN** 5 active subscriptions exist in database
- **THEN** system creates 5 UserConfig objects, each with SMTP credentials from global config

#### Scenario: Global email config missing
- **WHEN** subscription is loaded but AppConfig.email has enabled=false or missing credentials
- **THEN** system creates UserConfig with notify.email.enabled=false and logs warning "Global email config not configured, subscription user will not receive emails"

#### Scenario: Startup and runtime conversion are consistent
- **WHEN** a subscription is loaded at startup and another subscription is added at runtime with the same global email config
- **THEN** both resulting UserConfig objects use the same conversion logic and equivalent email notifier fields

### Requirement: Runtime subscription addition
The system SHALL add new subscriptions to both database and in-memory configuration without requiring restart, using global email config for SMTP credentials. Runtime creation SHALL use the same subscription-to-UserConfig helper as startup loading.

#### Scenario: New subscription added at runtime
- **WHEN** subscription form is submitted while application is running
- **THEN** system saves to database AND adds corresponding UserConfig to current AppConfig.users list with SMTP credentials from AppConfig.email

#### Scenario: Pipeline uses new subscription immediately
- **WHEN** new subscription is added and pipeline runs
- **THEN** pipeline processes papers for the new subscriber without requiring restart

#### Scenario: Global email config missing during runtime addition
- **WHEN** subscription is added via web form but AppConfig.email is not configured
- **THEN** system saves subscription to database, creates UserConfig with notify.email.enabled=false, and returns error message "系统未配置邮件发送功能，请联系管理员"
