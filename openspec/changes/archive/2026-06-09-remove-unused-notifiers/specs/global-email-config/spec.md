## Purpose

Define how global email configuration is managed in AppConfig, now as the sole notification channel (wecom/feishu/dingtalk removed).

## MODIFIED Requirements

### Requirement: Global email configuration in AppConfig
The system SHALL support a top-level `email` configuration section in `AppConfig` for centralized SMTP credentials management. Email is now the ONLY supported notification channel; wecom, feishu, and dingtalk notifier configs are removed.

#### Scenario: Email config defined in config.yaml
- **WHEN** `config.yaml` contains an `email:` section with SMTP settings
- **THEN** `AppConfig.email` is populated with the provided values

#### Scenario: Email config omitted from config.yaml
- **WHEN** `config.yaml` does not contain an `email:` section
- **THEN** `AppConfig.email` uses default values (enabled=false, empty credentials)

#### Scenario: Email config structure
- **WHEN** global email config is defined
- **THEN** it SHALL include: smtp_host, smtp_port, smtp_user, smtp_password, sender, use_tls fields

#### Scenario: No other notifier config types exist
- **WHEN** `UserNotifyConfig` is instantiated
- **THEN** it SHALL contain only an `email` field; wecom, feishu, and dingtalk fields SHALL NOT exist
