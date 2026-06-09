## ADDED Requirements

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
