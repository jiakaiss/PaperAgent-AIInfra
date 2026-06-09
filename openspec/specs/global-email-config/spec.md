## Purpose

Define how global email configuration is managed in AppConfig as the sole notification channel.
## Requirements
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

### Requirement: Email config environment variable interpolation
The system SHALL support `${ENV_VAR}` interpolation for sensitive email configuration fields. Docker deployment SHALL inject these variables from `.env` at runtime and SHALL NOT bake SMTP secrets into the Docker image.

#### Scenario: SMTP password from environment
- **WHEN** `config.yaml` contains `smtp_password: ${SMTP_PASSWORD}` and `SMTP_PASSWORD` environment variable is set
- **THEN** the interpolated value is used for SMTP authentication

#### Scenario: Missing environment variable
- **WHEN** `config.yaml` references a non-existent environment variable
- **THEN** the field is set to an empty string (non-strict mode)

#### Scenario: Docker runtime injection
- **WHEN** Docker Compose starts services with `.env` containing SMTP variables
- **THEN** the container receives those variables and `config.yaml` interpolation resolves them at runtime

#### Scenario: Secrets excluded from image
- **WHEN** the Docker image is built
- **THEN** `.env` and deployment config files containing secrets are excluded from the image

### Requirement: Email config validation
The system SHALL validate global email configuration on startup and SHALL expose a single reusable check for whether global email configuration is usable for subscription delivery.

#### Scenario: Invalid SMTP port
- **WHEN** `smtp_port` is set to a value outside the valid range (1-65535)
- **THEN** configuration validation fails with a clear error message

#### Scenario: Missing required fields for enabled email
- **WHEN** `enabled=true` but `smtp_host`, `smtp_user`, or `smtp_password` is empty
- **THEN** a warning is logged indicating incomplete email configuration

#### Scenario: Subscription readiness check reused
- **WHEN** web routes, app startup, or CLI startup need to know whether subscription email delivery is configured
- **THEN** they use the same helper/check instead of duplicating required-field logic

