## MODIFIED Requirements

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
