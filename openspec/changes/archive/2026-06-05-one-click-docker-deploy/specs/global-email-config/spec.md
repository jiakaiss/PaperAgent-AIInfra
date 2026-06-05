## MODIFIED Requirements

### Requirement: Email config environment variable interpolation
The system SHALL support `${ENV_VAR}` interpolation for sensitive email configuration fields. Docker deployment SHALL inject these variables from `.env` at runtime and SHALL NOT bake SMTP secrets into the Docker image.

#### Scenario: SMTP password from environment
- **WHEN** `config.yaml` contains `smtp_password: ${SMTP_PASSWORD}` and `SMTP_PASSWORD` environment variable is set
- **THEN** the interpolated value is used for SMTP authentication

#### Scenario: Missing environment variable
- **WHEN** `config.yaml` references a non-existent environment variable
- **THEN** the field is set to an empty string (non-strict mode)

#### Scenario: Docker runtime injection
- **WHEN** Docker Compose starts services with `.env` containing SMTP variables
- **THEN** the container receives those variables and `config.yaml` interpolation resolves them at runtime

#### Scenario: Secrets excluded from image
- **WHEN** the Docker image is built
- **THEN** `.env` and deployment config files containing secrets are excluded from the image
