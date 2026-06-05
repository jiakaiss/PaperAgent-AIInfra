## MODIFIED Requirements

### Requirement: Subscriptions table in database
The system SHALL create a `subscriptions` table in the SQLite database to persist user subscription information, including active/inactive status and unsubscribe metadata when supported by schema migrations.

#### Scenario: Table created on startup
- **WHEN** application starts and database is initialized
- **THEN** `subscriptions` table exists with columns: id, email, sub_domains, created_at, status

#### Scenario: Table schema
- **WHEN** `subscriptions` table is created
- **THEN** schema includes: id (INTEGER PRIMARY KEY), email (TEXT UNIQUE NOT NULL), sub_domains (TEXT NOT NULL, JSON array), created_at (TEXT NOT NULL, ISO timestamp), status (TEXT NOT NULL, default "active")

#### Scenario: Unsubscribe metadata migration
- **WHEN** application starts with an existing subscriptions table that lacks unsubscribe metadata columns
- **THEN** the system performs an idempotent migration so unsubscribe state can be recorded without losing existing rows

### Requirement: Subscription persistence
The system SHALL save new subscriptions to the database with email and selected sub-domains, and SHALL create them with active status.

#### Scenario: New subscription saved
- **WHEN** user submits valid subscription form
- **THEN** system inserts new row into `subscriptions` table with email, sub_domains (as JSON array), current timestamp, and status="active"

#### Scenario: Duplicate email rejected at database level
- **WHEN** system attempts to insert subscription with email that already exists
- **THEN** database UNIQUE constraint on email column prevents duplicate insertion

#### Scenario: New subscription starts active
- **WHEN** a new subscription row is created
- **THEN** its `status` is `active` until the user unsubscribes or an operator changes it

### Requirement: Load subscriptions on startup
The system SHALL load all active subscriptions from the database during application startup and SHALL exclude inactive subscriptions.

#### Scenario: Active subscriptions loaded
- **WHEN** application starts
- **THEN** system queries `subscriptions` table for all rows where status="active" and loads them into memory

#### Scenario: No active subscriptions
- **WHEN** application starts with no active subscriptions
- **THEN** system continues normally with empty subscription list

#### Scenario: Inactive subscriptions skipped
- **WHEN** application starts with subscriptions where status="inactive"
- **THEN** inactive subscription rows are not converted into runtime users

### Requirement: Subscription to UserConfig conversion
The system SHALL convert database subscriptions into UserConfig objects for pipeline processing, inheriting SMTP credentials from global email configuration and applying configured subscription delivery defaults. This conversion SHALL be implemented by a single reusable helper used by app startup, CLI startup, and runtime subscription creation.

#### Scenario: Subscription converted to UserConfig
- **WHEN** subscription is loaded from database
- **THEN** system creates UserConfig with: user_id=email, display_name=email, subscriptions.sub_domains=sub_domains array, notify.email.enabled=true, notify.email.recipients=[email], SMTP credentials (smtp_host, smtp_port, smtp_user, smtp_password, sender, use_tls) copied from AppConfig.email, and thresholds.top_n set from subscription delivery default

#### Scenario: Multiple subscriptions converted
- **WHEN** 5 active subscriptions exist in database
- **THEN** system creates 5 UserConfig objects, each with SMTP credentials from global config and the configured subscription delivery default

#### Scenario: Global email config missing
- **WHEN** subscription is loaded but AppConfig.email has enabled=false or missing credentials
- **THEN** system creates UserConfig with notify.email.enabled=false and logs warning "Global email config not configured, subscription user will not receive emails"

#### Scenario: Startup and runtime conversion are consistent
- **WHEN** a subscription is loaded at startup and another subscription is added at runtime with the same global email config and delivery defaults
- **THEN** both resulting UserConfig objects use the same conversion logic and equivalent email notifier fields and thresholds

### Requirement: Subscription query methods
The system SHALL provide methods to query, check, and update subscription state.

#### Scenario: Check if email subscribed
- **WHEN** system calls `is_email_subscribed(email)` method
- **THEN** returns True if email exists in subscriptions table with status="active", False otherwise

#### Scenario: Get subscription by email
- **WHEN** system calls `get_subscription(email)` method
- **THEN** returns subscription object with email, sub_domains, created_at, status if exists, None otherwise

#### Scenario: Mark subscription inactive
- **WHEN** system calls an unsubscribe/deactivate method for an existing email
- **THEN** the corresponding subscription row has `status="inactive"`

## ADDED Requirements

### Requirement: Inactive duplicate handling
The system SHALL handle attempts to subscribe an email that has an inactive subscription with clear behavior and without creating duplicate rows.

#### Scenario: Inactive email subscribes again
- **WHEN** a user submits the subscription form with an email that exists with `status="inactive"`
- **THEN** the system does not create a duplicate row and returns a clear message indicating the email has an inactive subscription or requires reactivation support
