## Requirements

### Requirement: Subscriptions table in database
The system SHALL create a `subscriptions` table in the SQLite database to persist user subscription information.

#### Scenario: Table created on startup
- **WHEN** application starts and database is initialized
- **THEN** `subscriptions` table exists with columns: id, email, sub_domains, created_at, status

#### Scenario: Table schema
- **WHEN** `subscriptions` table is created
- **THEN** schema includes: id (INTEGER PRIMARY KEY), email (TEXT UNIQUE NOT NULL), sub_domains (TEXT NOT NULL, JSON array), created_at (TEXT NOT NULL, ISO timestamp), status (TEXT NOT NULL, default "active")

### Requirement: Subscription persistence
The system SHALL save new subscriptions to the database with email and selected sub-domains.

#### Scenario: New subscription saved
- **WHEN** user submits valid subscription form
- **THEN** system inserts new row into `subscriptions` table with email, sub_domains (as JSON array), current timestamp, and status="active"

#### Scenario: Duplicate email rejected at database level
- **WHEN** system attempts to insert subscription with email that already exists
- **THEN** database UNIQUE constraint on email column prevents duplicate insertion

### Requirement: Load subscriptions on startup
The system SHALL load all active subscriptions from the database during application startup.

#### Scenario: Active subscriptions loaded
- **WHEN** application starts
- **THEN** system queries `subscriptions` table for all rows where status="active" and loads them into memory

#### Scenario: No active subscriptions
- **WHEN** application starts with no active subscriptions
- **THEN** system continues normally with empty subscription list

### Requirement: Subscription to UserConfig conversion
The system SHALL convert database subscriptions into UserConfig objects for pipeline processing, inheriting SMTP credentials from global email configuration.

#### Scenario: Subscription converted to UserConfig
- **WHEN** subscription is loaded from database
- **THEN** system creates UserConfig with: user_id=email, display_name=email, subscriptions.sub_domains=sub_domains array, notify.email.enabled=true, notify.email.recipients=[email], and SMTP credentials (smtp_host, smtp_port, smtp_user, smtp_password, sender, use_tls) copied from AppConfig.email

#### Scenario: Multiple subscriptions converted
- **WHEN** 5 active subscriptions exist in database
- **THEN** system creates 5 UserConfig objects, each with SMTP credentials from global config

#### Scenario: Global email config missing
- **WHEN** subscription is loaded but AppConfig.email has enabled=false or missing credentials
- **THEN** system creates UserConfig with notify.email.enabled=false and logs warning "Global email config not configured, subscription user will not receive emails"

### Requirement: Runtime subscription addition
The system SHALL add new subscriptions to both database and in-memory configuration without requiring restart, using global email config for SMTP credentials.

#### Scenario: New subscription added at runtime
- **WHEN** subscription form is submitted while application is running
- **THEN** system saves to database AND adds corresponding UserConfig to current AppConfig.users list with SMTP credentials from AppConfig.email

#### Scenario: Pipeline uses new subscription immediately
- **WHEN** new subscription is added and pipeline runs
- **THEN** pipeline processes papers for the new subscriber without requiring restart

#### Scenario: Global email config missing during runtime addition
- **WHEN** subscription is added via web form but AppConfig.email is not configured
- **THEN** system saves subscription to database, creates UserConfig with notify.email.enabled=false, and returns error message "系统未配置邮件发送功能，请联系管理员"

### Requirement: Subscription query methods
The system SHALL provide methods to query and check subscription existence.

#### Scenario: Check if email subscribed
- **WHEN** system calls `is_email_subscribed(email)` method
- **THEN** returns True if email exists in subscriptions table with status="active", False otherwise

#### Scenario: Get subscription by email
- **WHEN** system calls `get_subscription(email)` method
- **THEN** returns subscription object with email, sub_domains, created_at, status if exists, None otherwise

### Requirement: Global email config validation for subscriptions
The system SHALL validate that global email configuration exists before allowing subscription creation.

#### Scenario: Subscription rejected when email not configured
- **WHEN** user submits subscription form and AppConfig.email.enabled=false or SMTP credentials are missing
- **THEN** system rejects subscription with error message "系统未配置邮件发送功能，请联系管理员" and does not save to database

#### Scenario: Subscription accepted when email configured
- **WHEN** user submits subscription form and AppConfig.email is properly configured with SMTP credentials
- **THEN** system accepts subscription and saves to database with SMTP credentials
