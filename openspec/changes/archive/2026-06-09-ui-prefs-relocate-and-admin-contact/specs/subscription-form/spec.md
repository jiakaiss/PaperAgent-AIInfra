## MODIFIED Requirements

### Requirement: Subscription form displays guidance for requesting new sub-domains
The subscription signup page SHALL display a notice informing users that the listed sub-domains are the currently supported set, and that users with needs outside this list should contact the administrator to request additions. The notice SHALL appear together with the delivery schedule notice in the rules area. When the operator has configured `web.admin_contact`, the notice SHALL render the configured value as a parenthetical immediately after the word 管理员 (e.g. `联系管理员（admin@example.com）`). When `web.admin_contact` is empty or unset, the notice SHALL render exactly as before with no parenthetical. The same suffix rule SHALL apply to any server-side error message that uses the phrase `请联系管理员` in the subscribe flow.

#### Scenario: User sees how to request new sub-domains
- **WHEN** user visits `/subscribe`
- **THEN** the page contains text instructing users to contact the administrator if they need a sub-domain that is not in the current list

#### Scenario: Contact info absent when not configured
- **WHEN** the subscription page renders and `web.admin_contact` is the empty string (or unset)
- **THEN** the notice contains `联系管理员` with no following parenthetical and no email/handle in the page source

#### Scenario: Contact info shown when configured
- **WHEN** the subscription page renders and `web.admin_contact = "admin@example.com"`
- **THEN** the notice contains the substring `联系管理员（admin@example.com）`

#### Scenario: Error messages use the same contact suffix
- **WHEN** the subscribe POST handler returns an error containing `请联系管理员` (e.g. email not configured, access code missing) and `web.admin_contact = "admin@example.com"`
- **THEN** the rendered error message contains `请联系管理员（admin@example.com）`

#### Scenario: Operator content is HTML-escaped
- **WHEN** the operator configures `web.admin_contact = "<script>alert(1)</script>"`
- **THEN** the rendered page shows the literal characters and does NOT execute the script (Jinja2 autoescape applies)


## ADDED Requirements

### Requirement: Operator-configurable admin contact display
The application configuration SHALL expose an optional `web.admin_contact` string field. When set, web-facing surfaces that reference 管理员 SHALL display the configured value as a parenthetical hint so end users know how to reach the operator. When unset or empty, those surfaces SHALL render with no contact hint, identical to the pre-configuration baseline. The field SHALL be free-form (any non-empty string is accepted) so the operator can write a name, email, chat handle, or combination.

#### Scenario: Default config has no admin contact
- **WHEN** an `AppConfig` is constructed with default values
- **THEN** `config.web.admin_contact` equals the empty string `""`

#### Scenario: Configured contact round-trips through config loader
- **WHEN** `config.yaml` contains `web.admin_contact: "张三 <admin@example.com>"`
- **THEN** `load_config()` returns a config where `config.web.admin_contact == "张三 <admin@example.com>"`

#### Scenario: Operator omits the field entirely
- **WHEN** an existing `config.yaml` does not mention `admin_contact` at all
- **THEN** loading the config succeeds and `config.web.admin_contact == ""` (no migration needed)
