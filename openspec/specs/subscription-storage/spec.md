## Purpose

Define how web subscription records are stored, queried, loaded into runtime users, and managed over time.
## Requirements
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

### Requirement: Runtime subscription addition
The system SHALL add new subscriptions to both database and in-memory configuration without requiring restart, using global email config for SMTP credentials. Runtime creation SHALL use the same subscription-to-UserConfig helper as startup loading. The "without restart" guarantee SHALL hold for the long-running scheduler daemon process as well as the web server process: the daemon SHALL re-read active subscriptions from the database at the start of every scheduled ingest and digest job and reconcile its in-memory user list and per-user notifier set against the database, so a subscription created via the web form is delivered to by the next scheduled digest tick of an already-running daemon. Refresh failures (e.g. transient database read errors) SHALL log a warning and proceed with the previously-loaded user list rather than aborting the scheduled job.

#### Scenario: New subscription added at runtime
- **WHEN** subscription form is submitted while application is running
- **THEN** system saves to database AND adds corresponding UserConfig to current AppConfig.users list with SMTP credentials from AppConfig.email

#### Scenario: Pipeline uses new subscription immediately
- **WHEN** new subscription is added and pipeline runs
- **THEN** pipeline processes papers for the new subscriber without requiring restart

#### Scenario: Global email config missing during runtime addition
- **WHEN** subscription is added via web form but AppConfig.email is not configured
- **THEN** system saves subscription to database, creates UserConfig with notify.email.enabled=false, and returns error message "系统未配置邮件发送功能，请联系管理员"

#### Scenario: Daemon picks up subscription added after startup
- **WHEN** a subscription row is inserted into the `subscriptions` table after the scheduler daemon has already started and after its initial startup load of subscriptions
- **THEN** at the next scheduled digest job the daemon re-reads active subscriptions, appends a `UserConfig` for the new email, builds its per-user notifiers, and emits a digest to that user without any process restart

#### Scenario: Daemon drops user unsubscribed after startup
- **WHEN** a subscription's status is changed to `inactive` (or the row is removed from active subscriptions) after the daemon has already loaded it at startup
- **THEN** at the next scheduled digest job the daemon's reconcile removes the corresponding entry from the in-memory user list and from the per-user notifier set, so no digest is sent to that user

#### Scenario: Daemon refresh tolerates database read failure
- **WHEN** the daemon attempts to refresh subscriptions at the start of a scheduled job and the database read raises an exception
- **THEN** the daemon logs a warning, leaves its previously-loaded user list and notifier set unchanged, and proceeds with the scheduled job against that list

#### Scenario: Existing user's notifier is not rebuilt on refresh
- **WHEN** the daemon's scheduled refresh runs and a user is present in both the in-memory list and the active subscriptions table
- **THEN** that user's existing notifier instance is left untouched, so SMTP credential snapshots taken at process start are preserved (consistent with the documented "config.email changes require restart" rule)

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

### Requirement: Global email config validation for subscriptions
The system SHALL validate that global email configuration exists before allowing subscription creation.

#### Scenario: Subscription rejected when email not configured
- **WHEN** user submits subscription form and AppConfig.email.enabled=false or SMTP credentials are missing
- **THEN** system rejects subscription with error message "系统未配置邮件发送功能，请联系管理员" and does not save to database

#### Scenario: Subscription accepted when email configured
- **WHEN** user submits subscription form and AppConfig.email is properly configured with SMTP credentials
- **THEN** system accepts subscription and saves to database with SMTP credentials

### Requirement: Inactive duplicate handling
The system SHALL handle attempts to subscribe an email that has an inactive subscription with clear behavior and without creating duplicate rows.

#### Scenario: Inactive email subscribes again
- **WHEN** a user submits the subscription form with an email that exists with `status="inactive"`
- **THEN** the system does not create a duplicate row and returns a clear message indicating the email has an inactive subscription or requires reactivation support

### Requirement: Aggregate user delivery stats query
The system SHALL provide `PaperDatabase.get_user_stats()` returning, for every distinct `user_id` ever present in `sent_papers` AND every email in the `subscriptions` table, a record containing `user_id`, `total_sent`, `sent_7d`, `sent_30d`, `last_sent_at`. Users with no deliveries SHALL appear with zero counts and `last_sent_at = None`.

#### Scenario: User with deliveries
- **WHEN** `get_user_stats()` is called and user `alice@example.com` has 50 rows in `sent_papers`, 5 of them within the last 7 days and 20 within the last 30 days
- **THEN** the returned record for `alice@example.com` shows `total_sent=50`, `sent_7d=5`, `sent_30d=20`, and `last_sent_at` equal to the most recent `sent_at`

#### Scenario: Subscribed user with no deliveries
- **WHEN** `bob@example.com` exists in `subscriptions` but has no rows in `sent_papers`
- **THEN** `get_user_stats()` includes a record for `bob@example.com` with `total_sent=0`, `sent_7d=0`, `sent_30d=0`, `last_sent_at=None`

#### Scenario: Empty database
- **WHEN** `get_user_stats()` is called on a database with no subscriptions and no sent rows
- **THEN** the return value is an empty list (or equivalent empty collection)

### Requirement: Daily-sent aggregation query
The system SHALL provide `PaperDatabase.get_daily_sent_counts(days: int)` returning, for each of the last `days` calendar dates in the local timezone (most recent first), a record containing `date` (ISO `YYYY-MM-DD`) and `count` (the number of `sent_papers` rows whose `sent_at` falls on that date). Dates with zero deliveries SHALL still be present with `count=0`.

#### Scenario: Sparse activity
- **WHEN** `get_daily_sent_counts(days=7)` is called and only the day before yesterday saw deliveries
- **THEN** the returned list has 7 entries; 6 of them have `count=0` and the day-before-yesterday entry has the actual count

#### Scenario: Order is most-recent-first
- **WHEN** `get_daily_sent_counts(days=3)` is called
- **THEN** the first element corresponds to today, the second to yesterday, and the third to two days ago

#### Scenario: Empty database
- **WHEN** `get_daily_sent_counts(days=7)` is called on a database with no `sent_papers` rows
- **THEN** the result contains 7 entries each with `count=0`

### Requirement: Daily-scored aggregation query
The system SHALL provide `PaperDatabase.get_daily_paper_counts(days: int)` returning, for each of the last `days` calendar dates in the local timezone (most recent first), a record containing `date` (ISO `YYYY-MM-DD`) and `count` (the number of `papers` rows whose `scored_at` falls on that date). Dates with no scoring activity SHALL still be present with `count=0`.

#### Scenario: Recent scoring run
- **WHEN** `get_daily_paper_counts(days=7)` is called and a batch of 91 papers was scored today
- **THEN** the entry for today has `count=91` and earlier entries reflect their own actual counts (zero or positive)

#### Scenario: Order is most-recent-first
- **WHEN** `get_daily_paper_counts(days=3)` is called
- **THEN** the result is ordered today, yesterday, two-days-ago

### Requirement: Active-subscription counter
The system SHALL provide `PaperDatabase.count_active_subscriptions()` returning the integer count of rows in `subscriptions` whose `status = 'active'`.

#### Scenario: Counts only active rows
- **WHEN** the table holds 8 active and 2 inactive subscriptions
- **THEN** `count_active_subscriptions()` returns `8`

#### Scenario: Empty table
- **WHEN** the subscriptions table is empty
- **THEN** the method returns `0`

### Requirement: Global thresholds config replaces per-user thresholds
The system SHALL provide a top-level `thresholds` configuration section in `AppConfig` that defines `min_relevance`, `min_quality`, `top_n`, `min_tier`, and `per_sub_domain_top_n` shared by all subscription-derived users.

#### Scenario: Default thresholds
- **WHEN** `config.yaml` does not contain a `thresholds:` section
- **THEN** `AppConfig.thresholds` uses sensible defaults (min_relevance=6.0, min_quality=5.0, top_n=10, min_tier=solid)

#### Scenario: Configured thresholds applied to all subscribers
- **WHEN** `config.yaml` defines `thresholds.min_tier=breakthrough` and 3 active subscriptions exist
- **THEN** all 3 resulting UserConfig objects receive `min_tier=breakthrough`

