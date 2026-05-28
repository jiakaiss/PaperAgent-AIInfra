## Context

`paper-agent` today is a CLI + daemon with a push-only notification model. The storage layer is a single SQLite database with two tables (`papers`, `sent_papers`); the scoring and notification paths are well-tested and should not be disturbed.

Constraints:
- The project is Python-only; no Node.js toolchain is currently in use, and introducing one is out of scope.
- Jinja2 is already a runtime dependency — server-rendered HTML is the path of least resistance.
- Multiple processes (`paper-agent daemon` + the new web server) may read/write the same SQLite file; WAL mode should be enabled.
- The web server is a stateless reader over the existing `papers` cache; it does not own user identity or preference persistence.

Stakeholders: the existing CLI users (operators) and the new "web reader" persona who just wants to see their paper feed.

## Goals / Non-Goals

**Goals:**
- A usable web UI to browse scored papers and manage keyword preferences.
- Toggle between "my chosen sub-domains" and "all papers" — persisted in the browser.
- Zero-friction first use: open the page, pick tags, see papers. No sign-up, no login.
- Zero impact on the existing pipeline (`run`, `daemon`, `test`, `stats`, `init` commands untouched).
- Single-command launch: `paper-agent web`.

**Non-Goals:**
- Authentication of any kind — preferences live in the browser; the server has no concept of a user identity.
- Cross-device preference sync — out of scope for v1; each browser keeps its own `localStorage`.
- Custom free-text keywords — users pick from the 14 predefined sub-domains only.
- Real-time updates (WebSocket push when new papers arrive) — the user refreshes the page.
- Modifying the existing notification channels — web is a parallel surface, not a replacement.

## Decisions

### 1. FastAPI + Jinja2 + HTMX, not Flask or a SPA

**Decision:** FastAPI with Jinja2 server-rendered templates and HTMX for lightweight partial updates (mode toggle, keyword chip selection, pagination).

**Alternatives considered:**
- *Flask*: simpler but synchronous; FastAPI's async + Pydantic validation aligns with the rest of the codebase.
- *React / Vue SPA*: requires Node toolchain, separate build step, and a JSON API — overkill for a read-mostly paper browser.
- *Pure Jinja2 with full page reloads*: works but feels sluggish; HTMX adds ~10KB and gives a SPA-like feel without JS framework overhead.

**Rationale:** The project is Python-first, Jinja2 is already installed, and the UI is a list + form — HTMX handles it cleanly.

### 2. Preferences live in browser `localStorage`, not in SQLite

**Decision:** Mode (`custom` / `all`) and selected sub-domain tags are stored in the browser's `localStorage` under a single key (e.g. `paper_agent_prefs = { mode, subDomains[] }`). The server has no concept of a web user or a preference row. The JS layer reads preferences on load and translates them into URL query params (`?mode=...&sub_domain=...`) when requesting paper lists.

**Alternatives considered:**
- *Server-side `web_users` table with username-only identity*: would enable cross-device sync, but requires login UI, session cookies, and user CRUD — substantial overhead for a personal/team tool where preferences are low-value (14 checkboxes).
- *`config.yaml` extension*: YAML is operator-driven and static; mutating it on every browser toggle races with the daemon and is fragile.
- *Cookies for preference storage*: works but opaque to JS without extra code and limited to ~4KB; `localStorage` is simpler and has a 5MB quota.

**Rationale:** Preferences are cheap to recreate (just pick tags again). `localStorage` is synchronous, well-supported, and keeps the server stateless. If cross-device sync is needed later, we can add an optional export/import (JSON file) without changing the server.

### 3. No authentication, no user identity

**Decision:** The web server has no login, no session cookie, no user table. Every visitor sees the same paper corpus; only their locally-stored preferences differ.

**Alternatives considered:**
- *Username-only identity*: rejected — adds friction (login form on first visit) for minimal benefit when preferences are already browser-local.
- *Password auth / OAuth*: substantial surface area (hashing, reset flow, token storage) for a tool meant to be used on a trusted LAN.

**Rationale:** Zero-friction first use is a goal. If the tool is ever exposed beyond localhost, add optional basic-auth middleware at the reverse-proxy layer — no app changes needed.

### 4. Paper queries go through the existing `PaperDatabase` class

**Decision:** Add new read methods to `PaperDatabase`: `list_papers(sub_domains, search, limit, offset)`, `count_papers(sub_domains, search)`, `get_sub_domain_counts()`. No user-related CRUD is added.

**Alternatives considered:**
- *Separate `WebDatabase` class*: duplicates the connection setup; SQLite is fine with multiple methods on one class.

**Rationale:** Single source of truth for the SQLite connection; the existing `__init__` already manages the connection lifecycle.

### 5. SQLite WAL mode + shared connection per request

**Decision:** Enable WAL journal mode on the SQLite connection (allows concurrent readers while the daemon writes). FastAPI dependency injects a `PaperDatabase` per request.

**Alternatives considered:**
- *Read-only replica*: unnecessary; WAL handles read/write concurrency.
- *Global shared connection*: unsafe under FastAPI's async event loop.

**Rationale:** WAL is a one-line change and solves the daemon-writes-while-web-reads problem.

### 6. Mode toggle is a client-side preference with URL override

**Decision:** The `custom` vs `all` mode is stored in `localStorage` and applied on page load. The URL can override it with `?mode=...` for shareable links; visiting with an override also writes the new value to `localStorage` so the next visit sticks.

**Rationale:** Users expect their preference to survive across visits; the URL override is a convenience (share a filtered view) that also becomes the new default on visit.

## Risks / Trade-offs

- **[Browser-local preferences]** Switching browsers or clearing site data loses preferences. → Mitigation: acceptable for v1 (preferences are 14 checkboxes, trivial to re-pick); add optional JSON export/import as a follow-up if needed.
- **[No auth / no user identity]** Anyone with network access to the server sees all papers. → Mitigation: bind to `127.0.0.1` by default; document that `--host 0.0.0.0` is for trusted networks only. Add optional basic-auth middleware at the reverse-proxy layer if ever exposed.
- **[SQLite concurrency]** Heavy simultaneous writes from the daemon + web could lock. → Mitigation: WAL mode + busy timeout; the web is read-only against the papers table, so contention is minimal.
- **[HTMX coupling]** HTMX is a third-party lib with its own release cadence. → Mitigation: pin version, serve from `static/` not CDN, small surface area (a handful of `hx-get`/`hx-post` attributes).
- **[No real-time]** Users won't see new papers without refresh. → Mitigation: out of scope for v1; note as future work.
- **[First-run experience]** A fresh DB has no papers. → Mitigation: empty-state template explains "run `paper-agent run` first".
