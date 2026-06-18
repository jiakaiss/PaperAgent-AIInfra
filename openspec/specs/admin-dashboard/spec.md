# admin-dashboard Specification

## Purpose
Provide an operator-only dashboard, mounted under `/admin` and gated by HTTP Basic Auth, that surfaces subscriber state, per-user delivery counts, paper-library health, and runtime configuration so a deployment operator can monitor and triage the system without shelling into the database.

## Requirements

### Requirement: Admin configuration section
The system SHALL accept a top-level `admin` section in `config.yaml` containing `enabled` (bool, default false), `username` (string, default `"admin"`), and `password` (string, default empty). The `password` field SHALL support `${ENV_VAR}` interpolation via the same mechanism used elsewhere in the config.

#### Scenario: Default config has admin disabled
- **WHEN** `config.yaml` omits the `admin` section
- **THEN** `AppConfig.admin.enabled` is `false` and no admin routes are reachable

#### Scenario: Password from environment variable
- **WHEN** `admin.password` is set to `${ADMIN_PASSWORD}` and the env var holds `s3cret`
- **THEN** the effective admin password used for auth comparison is `s3cret`

#### Scenario: Plain-text password accepted
- **WHEN** `admin.password` is set to a literal string in `config.yaml`
- **THEN** that literal string is used as the admin password without modification

### Requirement: Admin surface is gated by HTTP Basic Auth
The system SHALL protect every route under the `/admin` prefix with HTTP Basic Authentication. Credential comparison SHALL use `secrets.compare_digest` to avoid timing-attack leakage. The realm string SHALL be `paper-agent-admin`.

#### Scenario: Missing credentials
- **WHEN** an unauthenticated request is made to any `/admin*` URL on an enabled admin
- **THEN** the response is `401 Unauthorized` with header `WWW-Authenticate: Basic realm="paper-agent-admin"`

#### Scenario: Wrong password
- **WHEN** a request supplies the configured username with an incorrect password
- **THEN** the response is `401 Unauthorized` with the same `WWW-Authenticate` header

#### Scenario: Wrong username
- **WHEN** a request supplies a username that does not match `admin.username` even with the correct password
- **THEN** the response is `401 Unauthorized`

#### Scenario: Correct credentials
- **WHEN** a request supplies the configured username and password via the standard `Authorization: Basic …` header
- **THEN** the response is the requested admin page with status `200 OK`

### Requirement: Disabled or unconfigured admin returns 404
When `admin.enabled` is `false`, or when `admin.password` is empty or whitespace-only, the system SHALL NOT register any admin routes; every `/admin*` URL SHALL return `404 Not Found` indistinguishably from any other unknown path.

#### Scenario: Admin disabled
- **WHEN** `admin.enabled: false` is configured and a request is made to `/admin`
- **THEN** the response is `404 Not Found` with no `WWW-Authenticate` header

#### Scenario: Empty password is treated as disabled
- **WHEN** `admin.enabled: true` but `admin.password` is an empty or whitespace-only string
- **THEN** every `/admin*` URL returns `404 Not Found`

#### Scenario: Startup logs the chosen mode
- **WHEN** the web app starts
- **THEN** an INFO-level log line records whether the admin dashboard is enabled or disabled (without printing the password)

### Requirement: Admin dashboard shell page
The system SHALL serve `GET /admin` as a single HTML shell page containing four panel containers, each labeled "订阅 / 用户统计 / 论文库 / 系统". Each container SHALL load its content asynchronously via HTMX on page load and SHALL offer a per-panel refresh control.

#### Scenario: Page renders
- **WHEN** an authenticated operator visits `/admin`
- **THEN** the response is HTML containing four labeled panel containers and HTMX directives that fetch each partial

#### Scenario: Panels load on open
- **WHEN** the dashboard shell finishes loading in the browser
- **THEN** each panel issues an HTMX `GET` against its respective partial endpoint and renders the result

#### Scenario: Per-panel refresh
- **WHEN** the operator clicks a panel's refresh control
- **THEN** only that panel's partial endpoint is re-fetched and its DOM region is swapped

### Requirement: Subscribers panel
The system SHALL serve `GET /admin/_subscribers` as an HTML fragment listing every subscription row with: ID, email, created-at timestamp, status (active or unsubscribed), unsubscribed-at timestamp (when applicable), number of subscribed sub-domains (with the full list available as a tooltip), cumulative delivered-paper count, and most-recent-delivery timestamp. The fragment SHALL support an email substring search via a `?q=` query parameter and sort by a `?sort=` parameter accepting at minimum `created_at`, `email`, `total_sent`, `last_sent_at` (each with optional `?order=asc|desc`).

#### Scenario: Lists all subscriptions
- **WHEN** the operator opens the subscribers panel with no filters
- **THEN** every row of the subscriptions table is rendered, both active and inactive

#### Scenario: Email search
- **WHEN** the operator types `huawei` into the search input
- **THEN** only rows whose email contains `huawei` (case-insensitive) are rendered

#### Scenario: Sort by last delivery
- **WHEN** the request is `GET /admin/_subscribers?sort=last_sent_at&order=desc`
- **THEN** the rows are ordered by `last_sent_at` descending, with subscribers who never received a paper sorted last

#### Scenario: Sub-domain tooltip
- **WHEN** a row shows "14 个子领域" as the sub-domain summary
- **THEN** the rendered cell exposes the full list as a `title` (or equivalent tooltip) attribute

### Requirement: Per-user delivery stats panel
The system SHALL serve `GET /admin/_user_stats` as an HTML fragment containing (a) a per-user table with columns `user_id`, `total_sent`, `sent_7d`, `sent_30d`, `last_sent_at` and (b) a 7-column daily-totals table listing the past 7 calendar days (most recent first) with the total papers sent each day.

#### Scenario: Per-user counts
- **WHEN** the panel loads
- **THEN** each row reflects accurate counts of papers in `sent_papers` for that user across the all-time, last-7-days, and last-30-days windows

#### Scenario: Daily-totals table
- **WHEN** the panel loads
- **THEN** the daily-totals table shows exactly 7 columns (one per the most recent 7 calendar days in the configured timezone), and each cell holds the total `sent_papers` rows whose `sent_at` falls within that day

#### Scenario: Empty user has zero counts
- **WHEN** a subscription user has never received a paper
- **THEN** their row appears with `total_sent`, `sent_7d`, `sent_30d` all `0` and `last_sent_at` rendered as `—` (or equivalent placeholder)

### Requirement: Paper library overview panel
The system SHALL serve `GET /admin/_papers` as an HTML fragment containing (a) numeric "stat cards" for total cached papers, papers scored today, and papers scored in the past 7 days; (b) impact-tier distribution rendered as a row per tier showing the count, percentage, and a CSS-only proportional bar; (c) sub-domain distribution rendered identically across the 14 standard sub-domains; and (d) a 7-column daily-newly-scored table for the past 7 days.

#### Scenario: Stat cards
- **WHEN** the panel loads
- **THEN** the three stat-card numbers equal `COUNT(*)` of `papers`, `COUNT(*) WHERE DATE(scored_at) = today`, and `COUNT(*) WHERE DATE(scored_at) >= today - 6` respectively

#### Scenario: Tier distribution
- **WHEN** the cache contains a mix of impact tiers
- **THEN** the panel renders one row per `IMPACT_TIERS` value, each showing the count, the percent of total, and a CSS bar whose width matches the percent

#### Scenario: Sub-domain distribution
- **WHEN** the panel loads
- **THEN** counts come from `PaperDatabase.get_sub_domain_counts()` and the 14 standard sub-domains are rendered in a consistent order even when a sub-domain has zero papers

#### Scenario: Daily-scored table
- **WHEN** the panel loads
- **THEN** the table shows the past 7 calendar days with each cell holding the number of `papers` rows whose `scored_at` date matches

### Requirement: System status panel
The system SHALL serve `GET /admin/_system` as an HTML fragment summarizing the runtime state of the deployment, including: scoring model name, ingest interval, digest hour and timezone, SMTP host (NOT credentials), database path and on-disk size in bytes, the most recent `scored_at` timestamp from `papers` (used as a proxy for *paper-level activity*, NOT daemon liveness — the panel SHALL annotate this row to make the distinction clear), the most recent `sent_at` timestamp from `sent_papers` (last successful digest), the count of active subscriptions, the count of users currently loaded in the runtime `AppConfig.users` (so the operator can detect a load discrepancy), AND a daemon-liveness banner derived from `daemon_heartbeat.assess_health(db_path, ingest_interval_minutes)`.

The daemon banner SHALL appear at the top of the panel (above the data rows, because it's the most actionable signal) and SHALL render one of four visually-distinct states:

- `running` — green dot, shows PID, uptime, time-since-last-heartbeat, and last-event
- `stale` — amber dot, shows PID and age of last heartbeat with a "scheduler may be wedged" hint
- `dead` — red dot, shows PID with "process no longer exists" and the last recorded event
- `never_started` — gray dot, shows a hint to run `paper-agent daemon -c config.yaml`

#### Scenario: Renders without crashing on empty DB
- **WHEN** the panel loads against a freshly-created database with no papers, no sent rows, and no heartbeat file
- **THEN** the response is `200 OK`, the daemon banner renders `never_started`, and "last ingest" and "last digest" fields render `—` (or equivalent)

#### Scenario: Detects active-vs-runtime mismatch
- **WHEN** 10 active subscriptions exist in the database but only 9 users appear in the live `AppConfig.users`
- **THEN** the panel renders both numbers and visually highlights the mismatch (e.g., differing color or a warning glyph)

#### Scenario: Database size reported
- **WHEN** the panel loads
- **THEN** the database file size (in bytes, formatted human-readably) is rendered alongside the database path

#### Scenario: Daemon running banner
- **WHEN** the daemon is alive and its heartbeat is fresh
- **THEN** the panel renders a green-dot banner showing the daemon's PID, uptime, and the age of its last heartbeat

#### Scenario: Daemon dead banner
- **WHEN** the heartbeat file exists but the recorded PID is gone (e.g., the daemon crashed)
- **THEN** the panel renders a red-dot banner with the missing PID and the last recorded event

#### Scenario: Daemon stale banner
- **WHEN** the daemon process is alive but the heartbeat is older than 2× the ingest interval
- **THEN** the panel renders an amber-dot banner indicating the scheduler may be wedged

#### Scenario: Daemon never-started banner
- **WHEN** no heartbeat file exists next to the database
- **THEN** the panel renders a gray-dot banner with a hint to run `paper-agent daemon`

#### Scenario: Last-ingest row is annotated
- **WHEN** the panel renders the "最近一次 ingest" row
- **THEN** the row includes a note clarifying that the timestamp only advances when new papers are scored, distinct from daemon liveness

### Requirement: Subscribers CSV export
The system SHALL serve `GET /admin/subscribers.csv` returning a CSV document with `Content-Type: text/csv; charset=utf-8` and `Content-Disposition: attachment; filename=subscribers-<YYYYMMDD>.csv`. The CSV SHALL include at minimum the columns `id`, `email`, `status`, `created_at`, `unsubscribed_at`, `sub_domains` (semicolon-joined), `total_sent`, `last_sent_at`. Generation SHALL use the stdlib `csv` module.

#### Scenario: Download attachment
- **WHEN** the operator visits `/admin/subscribers.csv`
- **THEN** the response is `200 OK` with `Content-Disposition: attachment` and a parseable CSV body whose header row matches the documented column list

#### Scenario: All subscriptions exported
- **WHEN** the database holds N subscription rows (active or inactive)
- **THEN** the CSV body holds exactly N data rows plus 1 header row

### Requirement: Admin responses never expose secrets
No admin response (HTML or CSV) SHALL contain values from any of: `scoring.api_key`, `email.smtp_password`, `subscriptions.unsubscribe.secret`, or `subscriptions.access.access_codes`. This rule SHALL be enforced by a test that seeds known secret values into a test config and asserts none of them appear in the response body of any admin route.

#### Scenario: SMTP password not rendered
- **WHEN** the operator loads `/admin/_system` with a configured SMTP password `unique-smtp-secret-123`
- **THEN** the response body does not contain the substring `unique-smtp-secret-123`

#### Scenario: API key not rendered
- **WHEN** the scoring API key is `sk-test-unique-key-456` and the operator loads any admin route
- **THEN** the substring `sk-test-unique-key-456` does not appear in the response

#### Scenario: Unsubscribe secret not rendered
- **WHEN** `subscriptions.unsubscribe.secret` is `hmac-unique-789` and the operator loads any admin route
- **THEN** that substring does not appear in the response

#### Scenario: Access codes not rendered
- **WHEN** `subscriptions.access.access_codes` contains `code-unique-abc` and the operator loads any admin route
- **THEN** that substring does not appear in the response

### Requirement: Admin styling is isolated
Admin pages SHALL be styled by a dedicated CSS file (e.g., `src/paper_agent/web/static/admin.css`) loaded only on admin templates. The public `style.css` SHALL NOT be modified to accommodate admin styling.

#### Scenario: Admin CSS exists and is mounted
- **WHEN** `/admin` is loaded
- **THEN** the rendered HTML references `/static/admin.css` and the file is reachable

#### Scenario: Public page styling unchanged
- **WHEN** the public `/` page is loaded
- **THEN** its `<link rel="stylesheet">` tags do not reference admin CSS

### Requirement: Citation coverage stats panel

When `citations.enabled` is `true`, the `GET /admin/_papers` fragment SHALL additionally render a citation-coverage sub-section containing: the count and percentage of cached papers with a non-null `citations_updated_at` (i.e., ever refreshed), the count with `citation_count > 0`, the most recent `citations_updated_at` timestamp across the cache (last refresh), and a one-line summary of the `citations` config (provider, refresh interval, enabled state). When `citations.enabled` is `false`, the sub-section SHALL render a single line stating "引用数采集未启用 (citations.enabled=false)" and no coverage numbers.

#### Scenario: Coverage shown when enabled
- **WHEN** `citations.enabled=true` and the cache has 200 papers, 150 of which have non-null `citations_updated_at` and 80 have `citation_count > 0`
- **THEN** the panel renders "150 / 200 (75%) 已采集引用数", "80 篇有引用", the most recent refresh timestamp, and the provider/interval summary

#### Scenario: Disabled state message
- **WHEN** `citations.enabled=false`
- **THEN** the citation sub-section renders only "引用数采集未启用 (citations.enabled=false)" and no coverage counts

#### Scenario: Never refreshed
- **WHEN** `citations.enabled=true` but no paper has ever been refreshed (`citations_updated_at` all NULL)
- **THEN** the panel renders "0 / N (0%) 已采集引用数" and a last-refresh placeholder of `—`
