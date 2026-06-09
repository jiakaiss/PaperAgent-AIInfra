## ADDED Requirements

### Requirement: Conditional admin router registration
The FastAPI app factory SHALL conditionally register the admin router. The admin router SHALL be registered only when `AppConfig.admin.enabled` is `true` AND `AppConfig.admin.password` is a non-empty, non-whitespace-only string. When this condition does not hold, the admin router SHALL NOT be registered, with the effect that every `/admin*` URL is handled by FastAPI's default 404 handler.

#### Scenario: Admin enabled and password set
- **WHEN** `create_app` runs with `admin.enabled=true` and a real password
- **THEN** the admin router is registered and `/admin` returns `401` (with `WWW-Authenticate`) for an unauthenticated request

#### Scenario: Admin disabled
- **WHEN** `create_app` runs with `admin.enabled=false`
- **THEN** the admin router is not registered and `/admin` returns `404`

#### Scenario: Admin enabled but password empty
- **WHEN** `create_app` runs with `admin.enabled=true` and an empty `admin.password`
- **THEN** the admin router is not registered and `/admin` returns `404`

#### Scenario: Public routes unaffected
- **WHEN** the admin router is or is not registered
- **THEN** the public routes (`/`, `/_paper_list`, `/subscribe`, `/api/subscribe`, `/unsubscribe`, `/health`) are reachable and behave identically in both cases
