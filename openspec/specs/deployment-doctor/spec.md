## Requirements

### Requirement: Doctor CLI command
The CLI SHALL expose a `doctor` subcommand that validates deployment readiness without modifying production data.

#### Scenario: Run doctor
- **WHEN** the operator runs `paper-agent doctor -c config.yaml`
- **THEN** the command performs readiness checks and exits 0 if all required checks pass

#### Scenario: Missing config file
- **WHEN** the config path does not exist
- **THEN** doctor prints a clear error and exits non-zero

### Requirement: Configuration checks
Doctor SHALL validate that required configuration can be loaded and that key deployment fields are sane.

#### Scenario: Config loads
- **WHEN** config.yaml is valid
- **THEN** doctor reports config load success

#### Scenario: Invalid config
- **WHEN** config.yaml fails Pydantic validation
- **THEN** doctor reports the validation error and exits non-zero

### Requirement: Storage checks
Doctor SHALL validate that the configured storage path is writable and that SQLite can initialize required tables.

#### Scenario: Writable database path
- **WHEN** `storage.db_path` points to a writable location
- **THEN** doctor reports storage check success

#### Scenario: Unwritable database path
- **WHEN** `storage.db_path` points to an unwritable location
- **THEN** doctor reports the permission problem and exits non-zero

### Requirement: Web asset checks
Doctor SHALL validate that required templates and static assets exist.

#### Scenario: Web assets present
- **WHEN** templates and static files are present in the package
- **THEN** doctor reports web asset check success

#### Scenario: Missing web asset
- **WHEN** a required template or static file is missing
- **THEN** doctor reports the missing file and exits non-zero

### Requirement: Email readiness checks
Doctor SHALL check whether global email config is ready for subscription delivery.

#### Scenario: Email configured
- **WHEN** `config.email.enabled=true` and SMTP credentials are present
- **THEN** doctor reports email readiness success

#### Scenario: Email missing
- **WHEN** public subscriptions are expected but email config is incomplete
- **THEN** doctor reports missing SMTP fields with remediation guidance
