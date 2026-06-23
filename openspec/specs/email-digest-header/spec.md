# email-digest-header Specification

## Purpose

Provide a prominent, clickable web-UI link in the header of every HTML digest email so subscribers can navigate directly to the Paper Agent web interface. The link is rendered only when `config.web.public_base_url` is configured, and the value flows from global config through subscription-to-UserConfig conversion to the email formatter, following the same restart-required pattern as SMTP credentials and thresholds.

## Requirements

### Requirement: Email digest renders a web-UI link in the header

The system SHALL render a prominently-placed hyperlink near the top of every HTML digest email, pointing at the Paper Agent web UI root, whenever `config.web.public_base_url` is configured and non-empty. The link MUST appear above the date/count metadata line so recipients see it before scanning the paper table.

#### Scenario: Web URL configured

- **WHEN** `config.web.public_base_url` is set to a non-empty string and a digest email is rendered for any user
- **THEN** the resulting HTML body contains an `<a href="...">` element whose target equals the configured URL, located inside the email header block (before the date/count line and before the paper table)

#### Scenario: Web URL not configured

- **WHEN** `config.web.public_base_url` is empty or unset and a digest email is rendered
- **THEN** the resulting HTML body contains no header web-UI link, and the rest of the email (date, count, paper table, unsubscribe footer) is byte-identical to the output produced before this change

### Requirement: Web URL propagates from global config to per-user notifier

The system SHALL copy `config.web.public_base_url` into each subscription user's `EmailNotifierConfig.web_url` field at subscription-to-`UserConfig` conversion time, alongside the existing SMTP credentials and unsubscribe URL plumbing. The value SHALL NOT be persisted in the `subscriptions` SQLite table — it is recomputed from live config on every app start.

#### Scenario: Conversion copies the web URL

- **WHEN** `load_subscriptions_into_config()` runs at app startup with a non-empty `config.web.public_base_url`
- **THEN** every resulting `UserConfig.notify.email.web_url` equals `config.web.public_base_url`

#### Scenario: Config change requires restart

- **WHEN** an operator changes `config.web.public_base_url` in `config.yaml` while the app is running
- **THEN** existing in-memory `UserConfig` objects retain the prior value until the app is restarted, matching the documented restart-required behavior for `config.email` and `config.thresholds`

### Requirement: Formatter accepts and renders the web URL

The `format_email_html(papers, unsubscribe_url=..., web_url=...)` function SHALL accept `web_url` as an optional keyword-only parameter with default `""`. When `web_url` is empty the function MUST omit the header link.

#### Scenario: Default invocation omits link

- **WHEN** `format_email_html(papers)` is called without supplying `web_url`
- **THEN** the returned HTML contains no header web-UI link element

#### Scenario: Explicit URL renders link

- **WHEN** `format_email_html(papers, web_url="https://example.com/")` is called
- **THEN** the returned HTML contains exactly one `<a>` element in the header block whose `href` attribute equals `"https://example.com/"`