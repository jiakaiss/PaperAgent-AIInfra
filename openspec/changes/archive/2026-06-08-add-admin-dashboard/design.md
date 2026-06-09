## Context

The site has grown from one test user a week ago to 10 active subscribers across multiple Huawei/h-partners domains, plus a daemon and a public web frontend. Operationally, every monitoring question — *who subscribed?*, *did anyone receive papers today?*, *is the daemon alive?*, *is the cache growing?* — currently requires SSH + ad-hoc SQL. As volume grows this becomes unsustainable.

This change introduces a single-operator dashboard layered onto the existing FastAPI + Jinja2 + HTMX stack, with strict isolation between the public surface (paper browsing, subscribe form) and the operator surface (subscriber list, system stats).

**Current state to build on:**
- FastAPI app factory in `web/app.py` already mounts `/static` and registers a single public router from `web/routes.py`.
- `PaperDatabase` already exposes `get_stats` (global), `load_active_subscriptions`, `count_papers`, and `get_sub_domain_counts` — most data we need is one aggregate query away.
- Existing rendering pattern: full page returns rendered template, refinements/refreshes pull HTML fragments via HTMX. Reuse this verbatim.
- Existing config pattern: `AppConfig` composes typed sub-configs (`FetchConfig`, `WebConfig`, ...) with `${ENV_VAR}` interpolation via `_interpolate_env`. New `AdminConfig` slots in identically.

**Constraints:**
- Single operator, single shared credential — no multi-user auth.
- No new Python dependencies, no chart library.
- Read-only in this change; mutation endpoints are out of scope.
- Sensitive fields (API keys, SMTP password, unsubscribe HMAC secret, access codes) MUST never appear in admin responses.
- Disabled-by-default must fail-closed to 404 (not 401, not 500) so an unconfigured deployment doesn't advertise the surface exists.

## Goals / Non-Goals

**Goals:**
- One URL (`/admin`) gives the operator a complete monitoring view: subscribers, per-user delivery, paper-library health, system status.
- Authentication enforced via stdlib `secrets.compare_digest` against config-stored credentials, behind HTTP Basic Auth (browser-native prompt, no login page).
- All admin routes share one auth dependency so adding a new admin route in the future requires zero auth boilerplate.
- All pages render with **no JavaScript dependencies beyond the existing HTMX bundle** — pure server-side HTML + CSS bars + small data tables.
- Tests cover the auth gate (correct/wrong/missing credentials, disabled mode), the no-sensitive-fields invariant, and one happy-path assertion per panel.

**Non-Goals:**
- Mutation endpoints (resend digest, edit user, force-unsubscribe). Operators can still do these via CLI/SQL.
- Role-based access control, multi-admin support, OAuth, SSO.
- Real-time updates (WebSocket / SSE). Page reload is fine.
- Audit logging of admin views (no mutations means low value).
- Replacement of the `paper-agent stats` CLI command — the dashboard and CLI cover overlapping but distinct workflows; both stay.
- Chart visualizations. Trends are rendered as 7-column tables.

## Decisions

### Decision 1: HTTP Basic Auth over session/login-page or token-in-URL

**Choice:** Standard HTTP Basic Auth with credentials checked via `secrets.compare_digest`.

**Rationale:**
- Zero new code paths (no login form, no logout, no session store). Browser handles the credential prompt and remembers it for the session.
- The realm string ("paper-agent-admin") lets the operator log out by clearing the browser's saved auth for the realm.
- `secrets.compare_digest` is the stdlib answer to timing-attack-safe comparison.

**Alternatives considered:**
- *URL-token + cookie* (mirroring the existing subscription `access_codes` flow): rejected because admin tokens leaked in URLs end up in browser history and proxy logs — strictly worse than Basic Auth's header-only credentials.
- *Login page + signed session cookie*: rejected as a single-operator UI doesn't need session UX, password reset flows, or logout buttons. ~150 lines of code for negative value.
- *IP allowlist*: rejected because the operator's IP changes (laptop / cellular / VPN).

### Decision 2: `enabled=false` (or empty password) returns 404, not 401

**Choice:** When `admin.enabled` is false, or `admin.password` is empty/whitespace, every `/admin*` route is unregistered or responds 404.

**Rationale:**
- 401 advertises "this surface exists, you just don't have credentials" and invites credential-stuffing attempts.
- 404 means "no such page" — indistinguishable from a typo or feature absence.
- Empty password is treated identically to disabled, because a deployed config with `password: ""` is a misconfiguration (no possible credential matches), not "anyone can log in".

**Implementation note:** Achieve this by *not registering* the admin router when admin is disabled, rather than registering it and short-circuiting in the dependency. Cleaner, and FastAPI's default 404 handler handles it for free. We do this check once at `create_app` time; runtime toggling requires a restart, which is acceptable for a single-operator deployment.

### Decision 3: Dashboard is one HTML page with HTMX-loaded panels

**Choice:** `GET /admin` returns a shell page with four "panel" containers; each panel has an `hx-get` pointing at the corresponding `_subscribers` / `_user_stats` / `_papers` / `_system` partial. Initial load uses `hx-trigger="load"` so all four populate on page open. A "Refresh" button in each panel header re-triggers its own fetch.

**Rationale:**
- Matches the existing pattern (`/_paper_list` partial driven by HTMX from `/`).
- Lets each panel refresh independently — system status changes minute-to-minute, subscribers daily, etc.
- Lets each partial be tested in isolation without parsing the full shell page.

**Alternative considered:**
- *Server-side rendering everything in `/admin` in one shot*: rejected because refreshing system status would require a full page reload, losing scroll position on the subscribers table.

### Decision 4: New aggregate methods on `PaperDatabase` (not a separate "admin stats" module)

**Choice:** Add `get_user_stats`, `get_daily_sent_counts(days)`, `get_daily_paper_counts(days)`, plus minor counters (e.g., `count_active_subscriptions`) directly on `PaperDatabase`.

**Rationale:**
- These are SQL aggregates over the same tables `PaperDatabase` already owns. Putting them anywhere else means a second class holding a second connection.
- Naming is generic enough to be reusable outside admin (e.g., a future CLI `paper-agent report` could use `get_daily_sent_counts`).
- `PaperDatabase` is already 566 lines and growing — but the additions are <80 lines and thematically consistent with `get_stats` / `get_sub_domain_counts` which already live there.

**Alternative considered:**
- *Separate `AdminStats` service class*: rejected as premature abstraction. Revisit if the file passes ~800 lines or if admin stats genuinely diverge from the table model.

### Decision 5: New `admin-dashboard` capability + minor deltas to `web-server` and `subscription-storage`

**Choice:** Most behavior (auth model, panel contracts, sensitive-field rule, disabled-mode behavior) belongs to a new `admin-dashboard` capability. `web-server` gets a small delta noting that admin routes register conditionally. `subscription-storage` gets a delta adding the three new query methods.

**Rationale:**
- The admin surface has its own auth model, its own security invariants, and its own rendering conventions — strong indicators of a distinct capability rather than a feature of the existing web capability.
- Keeping the data-aggregation requirements with `subscription-storage` (where `load_active_subscriptions` already lives) avoids creating a third storage-related capability.

### Decision 6: 7-day trend tables, not 30-day, in the initial release

**Choice:** Trend data (daily sent, daily scored) shows the last 7 days as a 7-column table.

**Rationale:**
- Fits comfortably on screen with no horizontal scroll.
- Matches the cadence the operator actually checks ("did anything go out yesterday and today?").
- Trivially extensible to 30 days later by changing one query parameter, but the wider table would force scroll on laptops.

### Decision 7: CSS-bar proportions instead of pie/bar charts for tier distribution

**Choice:** Render tier distribution and sub-domain distribution as horizontal CSS bars with text labels (`breakthrough  4   ▓░░░░░░░░░░░░░░░  0.8%`).

**Rationale:**
- No JS, no SVG, no chart library. ~20 lines of CSS for `.bar` and `.bar-fill` classes.
- Accessible by default (screen readers read the numbers, not pixel rectangles).
- Matches the user's explicit "数字卡片 + 表格 + CSS 进度条" preference.

## Risks / Trade-offs

- **Risk: Operator forgets to set `ADMIN_PASSWORD` env var → admin disabled silently.**
  *Mitigation:* `create_app` logs `INFO: Admin dashboard disabled (admin.enabled=false or password empty)` on every startup so the choice is visible. Also: `paper-agent doctor` will gain a check in a future change.

- **Risk: HTTP Basic Auth credentials transit in clear over HTTP if TLS is misconfigured.**
  *Mitigation:* Out of scope to enforce — the public site is already on TLS via the reverse proxy at `paper.aiinfraagent.com`. Document in CLAUDE.md: "Admin dashboard MUST be served over HTTPS."

- **Risk: Aggregate queries (`get_daily_sent_counts`, `get_user_stats`) become slow as `sent_papers` grows past ~100k rows.**
  *Mitigation:* The existing `idx_sent_user(user_id, sent_at)` index already covers user-stats queries. The daily-rollup queries scan one day's worth of rows per group; expected to stay sub-millisecond at current ~10 users × 10 papers/day rate (≈3.6k rows/year). Revisit if delivery scale grows 100×.

- **Trade-off: No mutation endpoints means operator still needs SSH for "delete today's sent records and resend" tasks.**
  *Accepted:* mutations carry write-side authz risk and demand audit logging — a separate change. Most monitoring is read-only.

- **Trade-off: Single shared credential means rotation requires editing config + restart.**
  *Accepted:* single-operator deployment. Documenting rotation in CLAUDE.md is sufficient.

- **Risk: A future contributor adds a panel that accidentally renders SMTP password (e.g., dumps `config.dict()`).**
  *Mitigation:* A test (`test_admin_responses_omit_sensitive_fields`) walks every admin route and asserts the response body does not contain known secret values seeded into the test config. New panels added in violation will fail this test.

## Migration Plan

1. Add `AdminConfig` to `config.py` with `enabled=False` default — zero-impact on existing deployments.
2. Add new `PaperDatabase` methods (additive, no schema changes).
3. Add admin module + templates + CSS.
4. Conditionally register admin router in `create_app`.
5. Update `config.example.yaml` with a documented (but commented-out / `enabled: false`) admin section.
6. Update `CLAUDE.md` and `README.md`.

**Rollback:** Delete `admin.enabled: true` from `config.yaml` (or set to false), restart. Admin surface returns 404 immediately.

**Operator enablement steps (post-deploy):**
1. Generate a strong password (e.g., `openssl rand -base64 24`).
2. Export `ADMIN_PASSWORD` in the daemon/web env, OR write it under `admin.password` in config.yaml.
3. Add `admin: { enabled: true, username: admin }` to `config.yaml`.
4. Restart the web server.
5. Visit `https://paper.aiinfraagent.com/admin` — browser prompts for credentials.

## Open Questions

None — all earlier-raised questions (password storage, chart approach, implementation path) were resolved before this design was written.
