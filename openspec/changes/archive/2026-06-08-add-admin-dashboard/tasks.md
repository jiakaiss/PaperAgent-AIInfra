## 1. Config — `AdminConfig`

- [x] 1.1 Add `AdminConfig` Pydantic model in `src/paper_agent/config.py` with `enabled: bool = False`, `username: str = "admin"`, `password: str = ""` and a helper property `is_active` returning `enabled and bool(password.strip())`.
- [x] 1.2 Add `admin: AdminConfig = Field(default_factory=AdminConfig)` field on `AppConfig`.
- [x] 1.3 Confirm `${ENV_VAR}` interpolation already covers nested fields (it does, via `_interpolate_recursive`) — no new interpolation logic needed.
- [x] 1.4 Update `config.example.yaml` with a documented `admin:` section (enabled: false, comments showing both env var and plain-text usage).

## 2. Storage — aggregate query methods

- [x] 2.1 Implement `PaperDatabase.get_user_stats()` returning a list of dicts (or a small `UserStats` dataclass) covering every email in `subscriptions` UNION every distinct `user_id` in `sent_papers`. Use one query that LEFT JOINs subscriptions to a `sent_papers` aggregate; default zero counts for users with no deliveries.
- [x] 2.2 Implement `PaperDatabase.get_daily_sent_counts(days: int)` that:
  - Computes the last `days` calendar dates in local time (Python side, via `date.today() - timedelta`).
  - Issues one `SELECT DATE(sent_at), COUNT(*) ... GROUP BY DATE(sent_at)` covering the window.
  - Merges results into a list of `(date_str, count)` ordered most-recent-first; missing days get `count=0`.
- [x] 2.3 Implement `PaperDatabase.get_daily_paper_counts(days: int)` symmetric to 2.2 but against `papers.scored_at`.
- [x] 2.4 Implement `PaperDatabase.count_active_subscriptions()` — one `SELECT COUNT(*) WHERE status='active'`.
- [x] 2.5 Add unit tests in `tests/test_admin_storage.py` (or extend `test_web_storage.py` / `test_subscription_storage.py`) covering: empty DB, sparse deliveries, ordering, and that a subscribed user with zero deliveries still appears in `get_user_stats`.

## 3. Auth dependency + admin module skeleton

- [x] 3.1 Create `src/paper_agent/web/admin.py` with module-level `router = APIRouter(prefix="/admin")`.
- [x] 3.2 Implement `verify_admin(credentials: HTTPBasicCredentials = Depends(HTTPBasic(realm="paper-agent-admin", auto_error=False)))` dependency:
  - If `credentials is None`: raise `HTTPException(401, headers={"WWW-Authenticate": 'Basic realm="paper-agent-admin"'})`.
  - Else compare both username AND password with `secrets.compare_digest` against the config values read from `request.app.state.config.admin`; raise the same 401 on mismatch.
  - Use `compare_digest` on bytes; encode both sides as utf-8.
  - Compare BOTH fields even when one is wrong (don't short-circuit on username mismatch) to avoid a username-enumeration timing channel.
- [x] 3.3 Add `router.dependencies = [Depends(verify_admin)]` so every route under the router shares the gate.

## 4. Admin routes — wire up all five endpoints

- [x] 4.1 `GET /admin` → render `admin/dashboard.html` shell with four panel containers.
- [x] 4.2 `GET /admin/_subscribers` → query subscriptions + per-user `get_user_stats`, apply `?q=` and `?sort=` / `?order=`, render `admin/_subscribers.html` partial. Use only the columns specified in the spec.
- [x] 4.3 `GET /admin/_user_stats` → call `get_user_stats()` + `get_daily_sent_counts(7)`, render `admin/_user_stats.html` partial.
- [x] 4.4 `GET /admin/_papers` → call existing `count_papers()` for totals + new `get_daily_paper_counts(7)` + existing `get_sub_domain_counts()` + a small helper for tier distribution (one `SELECT COALESCE(impact_tier,'solid'), COUNT(*) GROUP BY ...`), render `admin/_papers.html` partial.
- [x] 4.5 `GET /admin/_system` → gather: scoring model, ingest interval, digest hour/timezone, SMTP host (NOT credentials), `db_path` + size from `Path(db_path).stat().st_size`, `MAX(scored_at)` from `papers`, `MAX(sent_at)` from `sent_papers`, `count_active_subscriptions()`, `len(config.users)`; render `admin/_system.html` partial. Add a `is_mismatched` boolean for the active-vs-runtime comparison.
- [x] 4.6 `GET /admin/subscribers.csv` → build CSV with stdlib `csv.writer` writing to an `io.StringIO`, return `Response(content, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f"attachment; filename=subscribers-{date.today():%Y%m%d}.csv"})`. Columns per spec; sub-domains joined with `;`.

## 5. Templates + CSS

- [x] 5.1 Create directory `src/paper_agent/web/templates/admin/`.
- [x] 5.2 Create `admin/base.html` extending nothing (independent from public base — avoids accidental coupling) but reusing static-asset cache-busting globals.
- [x] 5.3 Create `admin/dashboard.html` with four `<section>` containers, each with `hx-get="/admin/_<panel>"`, `hx-trigger="load, refreshClick"`, and a `<button>` that emits the `refreshClick` event via `hx-on:click="this.closest('section').dispatchEvent(new Event('refreshClick'))"` or equivalent.
- [x] 5.4 Create `admin/_subscribers.html` with: search input (HTMX-driven), sortable column headers (links emit `hx-get` with updated `sort/order`), and the data table. Sub-domain count cell uses `title="{{ sub_domains|join(', ') }}"`.
- [x] 5.5 Create `admin/_user_stats.html` with the per-user table + the 7-column daily-totals table.
- [x] 5.6 Create `admin/_papers.html` with three stat cards, tier distribution rows (use `.bar` + `.bar-fill` with `style="width: {{ pct }}%"`), sub-domain distribution rows, and the 7-column daily-scored table.
- [x] 5.7 Create `admin/_system.html` with definition-list style rows, plus a visual mismatch highlight when `is_mismatched`.
- [x] 5.8 Create `src/paper_agent/web/static/admin.css` — scope every rule under `body.admin` or under a `.admin-page` wrapper so it cannot leak into the public site. Include `.stat-card`, `.bar`, `.bar-fill`, `.panel`, `.mismatch-warning` classes.
- [x] 5.9 Confirm `admin/base.html` links to `/static/admin.css?v={{ admin_css_version }}` (compute via the existing `_file_version` helper in `app.py`).

## 6. Wire admin into the app factory

- [x] 6.1 In `src/paper_agent/web/app.py`, import `admin.router` and `AdminConfig`.
- [x] 6.2 After registering the public router, check `config.admin.is_active`:
  - If true: register the admin router and add an `admin_css_version` global to the Jinja env (use `_file_version("admin.css")`).
  - If false: log `INFO` "Admin dashboard disabled (admin.enabled=false or password empty)"; do not register the router.
- [x] 6.3 If true and `config.admin.username == ""`, log a WARNING ("admin enabled with empty username — using default 'admin'") and treat as `"admin"`.

## 7. Tests

- [x] 7.1 Create `tests/test_admin.py`. Use a fixture that builds an `AppConfig` with seeded sentinel secret values (`unique-smtp-secret-123`, `sk-test-unique-key-456`, `hmac-unique-789`, `code-unique-abc`) and a tmp-path SQLite DB pre-populated with a few subscriptions + sent rows.
- [x] 7.2 Test: `admin.enabled=false` → `GET /admin` returns 404 and `WWW-Authenticate` header is absent.
- [x] 7.3 Test: `admin.enabled=true, password=""` → same as 7.2.
- [x] 7.4 Test: `admin.enabled=true` with valid password → unauthenticated `GET /admin` returns 401 with `WWW-Authenticate: Basic realm="paper-agent-admin"`.
- [x] 7.5 Test: wrong username with correct password → 401.
- [x] 7.6 Test: correct credentials → 200 for `/admin`, all four partials, and `/admin/subscribers.csv`. Assert basic content markers (e.g., the email of a seeded subscriber appears in `_subscribers`).
- [x] 7.7 Test (parameterized over all admin URLs): the response body does NOT contain any of the four seeded sentinel secret strings.
- [x] 7.8 Test: `_subscribers?q=alice` filters as expected; `?sort=email&order=asc` orders alphabetically.
- [x] 7.9 Test: `_system` flags the active-vs-runtime mismatch when one is removed from `config.users`.
- [x] 7.10 Test: `subscribers.csv` parses with `csv.DictReader` and contains the expected header columns and one row per subscription.
- [x] 7.11 Unit tests for `get_user_stats`, `get_daily_sent_counts`, `get_daily_paper_counts`, `count_active_subscriptions` (per 2.5).
- [x] 7.12 Run `pytest tests/test_admin.py tests/test_admin_storage.py -v` and ensure green.

## 8. Documentation

- [x] 8.1 Update `CLAUDE.md` with a new section "### Admin Dashboard (`web/admin.py`)" describing: how to enable (config + env var), the five routes and what each shows, the no-secrets rule, and the operator enablement steps from `design.md`'s Migration Plan.
- [x] 8.2 Update `README.md` with a short "Admin dashboard" subsection pointing at CLAUDE.md for details.
- [x] 8.3 Update `config.example.yaml` per 1.4.

## 9. Validation

- [x] 9.1 `ruff check src/ tests/` clean.
- [x] 9.2 `ruff format src/ tests/`.
- [x] 9.3 `pytest tests/ -v` — full suite green (no regression in existing web tests).
- [x] 9.4 Manual smoke test: set `ADMIN_PASSWORD`, restart web server, visit `/admin` in a browser, verify all four panels populate and the CSV downloads cleanly.
- [x] 9.5 `openspec validate add-admin-dashboard --strict` passes.
