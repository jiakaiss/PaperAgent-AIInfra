## ADDED Requirements

### Requirement: Focused audit before refactor
Before making cleanup changes, the implementation SHALL audit the target code paths and identify duplicated logic, inconsistent state transitions, and high-confidence bugs.

#### Scenario: Audit subscription and filtering paths
- **WHEN** implementation begins
- **THEN** the developer inspects subscription config conversion, subscription API validation, frontend preference URL construction, and related tests before editing

#### Scenario: Record findings as tasks or fixes
- **WHEN** the audit finds a high-confidence bug or duplication
- **THEN** it is either fixed in this change or explicitly documented as out of scope

### Requirement: Behavior-preserving cleanup
Cleanup changes SHALL preserve existing external behavior unless a bug is explicitly identified and covered by tests.

#### Scenario: Refactor helper extraction
- **WHEN** duplicated logic is extracted into a helper
- **THEN** existing behavior tests for subscriptions, email config, and web filtering continue to pass

#### Scenario: Bug fix during cleanup
- **WHEN** behavior changes due to a bug fix
- **THEN** a regression test demonstrates the expected behavior

### Requirement: Test coverage for simplified paths
Simplified code paths SHALL remain covered by automated tests at the behavior level.

#### Scenario: Subscription helper coverage
- **WHEN** subscription-to-UserConfig conversion is simplified
- **THEN** tests verify the resulting UserConfig contains the correct subscriptions and email notifier configuration

#### Scenario: Frontend filter helper coverage
- **WHEN** frontend URL/filter logic is simplified
- **THEN** JS tests verify mode, sub-domain, search, time range, and empty custom-mode behavior
