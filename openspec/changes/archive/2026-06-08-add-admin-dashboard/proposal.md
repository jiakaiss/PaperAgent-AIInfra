## Why

The site owner currently has no in-product way to monitor the service — checking who subscribed, how many papers were delivered, what the LLM cache looks like, or whether the daemon is actually running all require shelling into the server and running ad-hoc SQL. As the subscriber list grows (10 active subscribers as of 2026-06-08, up from 1 test user a week ago) this overhead compounds and small problems (subscribers added but not in runtime config, daemon stalled, delivery counts dropping) go unnoticed until someone complains.

Add an authenticated `/admin` dashboard scoped to the site owner so the same monitoring questions can be answered in a browser tab, without changing any data or exposing it to subscribers.

## What Changes

- Add a new `admin` capability that owns operator-facing observability surfaces — read-only dashboards, no mutation endpoints in scope for this change.
- Add HTTP Basic Auth gate keyed off a new `admin` config section (`enabled` / `username` / `password`, with `${ENV_VAR}` interpolation reusing the existing helper).
- Add four dashboard panels (subscribers / per-user delivery stats / paper library overview / system status), all rendered server-side as HTML partials following the existing HTMX + Jinja2 pattern.
- Add a CSV export endpoint for the subscriber list (`/admin/subscribers.csv`) since that's the data most likely to be pulled into a spreadsheet.
- Add aggregate query methods to `PaperDatabase` (`get_user_stats`, `get_daily_sent_counts`, `get_daily_paper_counts`, plus supporting count queries) — these are reusable for any future operator tooling, not admin-only conceptually.
- Modify the web capability to register the admin router alongside the existing public routes, with a documented isolation boundary between public and admin surfaces.
- Modify the configuration capability surface (via `AppConfig`) to include the new `admin` section.

Constraints baked into scope:
- **No charts library, no new Python dependencies.** Trends rendered as 7-column tables; proportions as CSS bars.
- **Read-only.** No "trigger digest" / "edit subscription" buttons in this change — those can come later as a separate capability addition.
- **Sensitive fields never rendered.** API keys, SMTP passwords, unsubscribe HMAC secret, and access codes are excluded from every admin response by construction.
- **Disabled-by-default fails closed to 404, not 401 or 500** — an unconfigured server should not advertise that an admin surface exists.

## Capabilities

### New Capabilities
- `admin-dashboard`: Authenticated operator dashboard. Owns the auth gate, the four read-only data panels (subscribers, per-user delivery stats, paper library overview, system status), the CSV export endpoint, and the rule that sensitive credentials never appear in admin responses.

### Modified Capabilities
- `web-server`: Adds the admin router registration and the rule that `/admin*` paths are gated independently of public routes. The public routes themselves are unchanged.
- `subscription-storage`: Adds aggregate read methods (`get_user_stats`, `get_daily_sent_counts`, `get_daily_paper_counts`) on `PaperDatabase`. The storage schema and existing methods are unchanged.

## Impact

**Affected code:**
- `src/paper_agent/config.py` — new `AdminConfig` model + field on `AppConfig`.
- `src/paper_agent/storage/database.py` — new aggregate query methods.
- `src/paper_agent/web/app.py` — register admin router.
- `src/paper_agent/web/admin.py` — **new file** holding auth dependency + all admin routes.
- `src/paper_agent/web/templates/admin/` — **new directory** with dashboard shell + four partial templates.
- `src/paper_agent/web/static/admin.css` — **new file** scoped to admin pages (no overlap with existing `style.css`).
- `tests/test_admin.py` — **new test file** covering auth, disabled mode, happy paths, and the no-secrets rule.

**Dependencies:** none new. Auth uses stdlib `secrets.compare_digest`; CSV uses stdlib `csv`; existing FastAPI + Jinja2 + HTMX stack covers the rest.

**Config:**
- `config.example.yaml` gains a documented `admin:` section.
- Existing deployments are unaffected — when `admin` is absent or `enabled=false`, the dashboard is invisible (404 on all `/admin*`).

**Docs:**
- `CLAUDE.md` gains an "Admin Dashboard" section (enable / routes / data sources / security notes).
- `README.md` mentions the dashboard entrypoint and points at CLAUDE.md for details.

**Out of scope (explicitly):**
- Mutation endpoints (resend digest, edit thresholds, force-unsubscribe).
- Multi-admin / role-based auth — single shared credential is sufficient for the current single-operator deployment.
- Real-time updates (WebSocket / SSE) — page refresh is acceptable.
- Audit log of admin actions — there are no mutating actions to log yet.
