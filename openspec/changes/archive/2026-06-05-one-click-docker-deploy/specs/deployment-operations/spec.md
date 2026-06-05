## ADDED Requirements

### Requirement: Deploy script
The project SHALL provide a deploy script for VPS operators that prepares directories, validates required files, builds images, and starts Docker Compose services.

#### Scenario: First deployment
- **WHEN** the operator runs `scripts/deploy.sh` after preparing `.env`
- **THEN** the script creates required deploy directories, runs doctor, builds the image, and starts services

#### Scenario: Missing .env
- **WHEN** `.env` is missing
- **THEN** the script prints instructions to copy `.env.example` and exits non-zero

### Requirement: Backup script
The project SHALL provide a backup script that creates timestamped SQLite backups.

#### Scenario: Backup database
- **WHEN** the operator runs `scripts/backup.sh`
- **THEN** a timestamped backup file is written under the configured backups directory

#### Scenario: Missing database
- **WHEN** no database file exists yet
- **THEN** the backup script prints a clear message and exits non-zero

### Requirement: Restore script
The project SHALL provide a restore script that restores a selected database backup safely.

#### Scenario: Restore backup
- **WHEN** the operator runs `scripts/restore.sh <backup-file>`
- **THEN** the script stops services, restores the database, and instructs or performs service restart

#### Scenario: Invalid backup path
- **WHEN** the requested backup file does not exist
- **THEN** the restore script prints an error and exits non-zero

### Requirement: Deployment documentation
The project SHALL document Docker VPS deployment steps and operational commands.

#### Scenario: Operator follows docs
- **WHEN** an operator reads the deployment docs
- **THEN** they can find steps for installing Docker, configuring `.env`, deploying, checking health, viewing logs, backing up, restoring, upgrading, and setting up HTTPS via reverse proxy

#### Scenario: Troubleshooting guidance
- **WHEN** deployment fails
- **THEN** the docs include guidance for common failures: missing env vars, SMTP auth failure, database permissions, port conflicts, and container health failures
