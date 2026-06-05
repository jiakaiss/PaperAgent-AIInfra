## Context

Recent work added several cross-cutting features:

- web subscription form and API
- global email configuration
- subscription-to-UserConfig conversion
- front-end preference filtering and HTMX URL construction
- expanded CSS/templates and test suites

These changes are functional, but some responsibilities now exist in multiple places:

- SMTP readiness checks appear in config validation, app startup, and subscription routes.
- Subscription-to-UserConfig conversion exists in both web startup code and CLI startup code.
- Frontend filtering behavior depends on several functions (`setMode`, `setSubDomains`, `toggleSubDomain`, `setSince`, `refreshPaperList`, `buildQueryString`).
- Tests repeat config/database/client setup.

This change is a focused cleanup/audit pass, not a rewrite.

## Goals / Non-Goals

**Goals:**
- Centralize duplicated email/subscription helper logic.
- Centralize frontend filter URL construction and empty-state handling.
- Reduce repeated test fixture code.
- Run an audit of subscription and filtering paths for high-confidence bugs.
- Preserve current behavior except for explicit bug fixes.

**Non-Goals:**
- No new product features.
- No database schema changes unless a clear bug requires it.
- No framework changes or new frontend build system.
- No authentication/session system.

## Decisions

### 1. Extract subscription helper functions near config/app boundaries

Create small helper functions for:

- checking whether global email config is usable for subscriptions
- building a subscription user's email notify config from `AppConfig.email`
- converting subscription rows into `UserConfig`

Preferred location: `paper_agent.config` or a small module like `paper_agent.subscriptions` if imports would otherwise create cycles.

Rationale: `web/app.py`, `web/routes.py`, and `cli.py` all need similar behavior; duplicating it risks divergence.

### 2. Keep database free of SMTP credentials

Subscription rows should continue storing only subscription identity and preference data. SMTP credentials stay in `config.yaml` / `AppConfig.email` and are copied into runtime `UserConfig` objects.

Rationale: avoids storing secrets in SQLite and preserves one source of truth.

### 3. Preserve stateless web browsing architecture

The server remains stateless with respect to preferences. The frontend is still responsible for converting localStorage into query parameters.

Cleanup should make this easier to reason about, not move preference state server-side.

### 4. Audit before editing broadly

Implementation should start with a targeted audit:

- grep for duplicated SMTP/config logic
- inspect subscription tests for behavior assumptions
- inspect JS URL-building tests
- run test subsets to establish baseline

Only then should code be changed.

## Risks / Trade-offs

- **[Risk] Refactor changes behavior accidentally** → Mitigation: keep changes small, run existing full test suite, add targeted tests before edits.
- **[Risk] Moving helpers creates import cycles** → Mitigation: choose a neutral helper module if `config.py` imports would become awkward.
- **[Risk] Tests become overfit to implementation details** → Mitigation: prefer behavior tests (resulting UserConfig, resulting URL, returned fragment), not private helper assertions unless helpers are intended contracts.
- **[Trade-off] Some duplication may remain** → Acceptable if removing it would require broader architectural changes than the value justifies.
