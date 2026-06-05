## MODIFIED Requirements

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
