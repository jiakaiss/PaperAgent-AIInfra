## 1. Dependencies & Project Scaffolding

- [x] 1.1 Add `fastapi`, `uvicorn[standard]` to `pyproject.toml` runtime deps
- [x] 1.2 Add `httpx` (FastAPI test client) to dev deps
- [x] 1.3 Create `src/paper_agent/web/` package with `__init__.py`, `app.py`, `routes.py`, `deps.py`
- [x] 1.4 Create `src/paper_agent/web/templates/` and `src/paper_agent/web/static/` directories
- [x] 1.5 Vendor HTMX into `src/paper_agent/web/static/vendor/htmx.min.js`

## 2. Storage Layer (read-only additions)

- [x] 2.1 Enable SQLite WAL journal mode and busy timeout on connection open in `storage/database.py`
- [x] 2.2 Add `list_papers(sub_domains=None, search=None, limit=25, offset=0) -> list[ScoredPaper]` method
- [x] 2.3 Add `count_papers(sub_domains=None, search=None) -> int` method
- [x] 2.4 Add `get_sub_domain_counts() -> dict[str, int]` method (per-tag paper counts for chip badges)
- [x] 2.5 Add tests for new storage methods (filter combinations, pagination, count/list consistency)

## 3. FastAPI App & Dependencies

- [x] 3.1 Implement `create_app(config: AppConfig) -> FastAPI` factory in `app.py` with Jinja2 + StaticFiles mounts
- [x] 3.2 Implement `get_db()` dependency yielding a per-request `PaperDatabase`
- [x] 3.3 Add `GET /health` route returning `{"status": "ok"}`

## 4. Paper Browsing Routes

- [x] 4.1 Implement `GET /` route that reads `?mode=`, `?sub_domain=`, `?q=`, `?page=` query params and renders `index.html` with the paper list
- [x] 4.2 Clamp `page` to valid range; default page size 25
- [x] 4.3 Validate `sub_domain` values against `SUB_DOMAINS` keys; ignore unknown tags
- [x] 4.4 Implement `GET /_paper_list` HTMX fragment route returning only the paper list + pagination partial (for in-place filter swaps)
- [x] 4.5 Add `index.html` template with paper cards, sub-domain chip filter, search box, mode toggle mount point, pagination controls, total count
- [x] 4.6 Add empty-state template branch for zero papers / zero matches
- [x] 4.7 Add `_paper_list.html` partial template used by both `/` and `/_paper_list`

## 5. Client-Side Preferences (localStorage)

- [x] 5.1 Add `static/preferences.js` with `getPrefs()`, `setMode(mode)`, `setSubDomains(tags)`, `applyPrefsToUrl()` helpers
- [x] 5.2 On page load, read `paper_agent_prefs` from `localStorage`; fall back to `{mode: "all", subDomains: []}` when absent or corrupt
- [x] 5.3 Validate stored `subDomains` against `SUB_DOMAINS` keys before use; drop unknowns
- [x] 5.4 When `?mode=` is present in the URL, write the new value to `localStorage` and drop the query param from the address bar (replaceState)
- [x] 5.5 Wire the mode toggle UI to `setMode()` + re-issue the HTMX request with updated query params
- [x] 5.6 Wire each sub-domain checkbox to `setSubDomains()` + re-issue the HTMX request
- [x] 5.7 Add preferences panel (collapsible sidebar or modal) to `index.html` with mode toggle and 14 checkboxes
- [x] 5.8 Persist sub-domain chip filter in localStorage alongside the "selected tags" preference (or as a separate `activeFilter` key) — clarify in design before implementing

## 6. Static Assets & Styling

- [x] 6.1 Add `static/style.css` with layout, paper card, chip, pagination, and preferences panel styles
- [x] 6.2 Add `static/app.js` to bootstrap preferences and wire up HTMX request params from localStorage
- [x] 6.3 Include responsive/mobile-friendly viewport meta tag in `base.html`

## 7. CLI Integration

- [x] 7.1 Add `@cli.command() def web(host, port, config)` to `cli.py`
- [x] 7.2 Wire `uvicorn.run(create_app(config), host=host, port=port)` inside the command
- [x] 7.3 Handle SIGTERM/SIGINT for graceful shutdown (uvicorn default is fine; verify)
- [x] 7.4 Update CLI `--help` text and README/CLAUDE.md with the new command

## 8. Tests

- [x] 8.1 Add `tests/test_web_app.py` with httpx-based tests for `/health` and `/` rendering
- [x] 8.2 Add `tests/test_web_browsing.py` covering list/filter/search/pagination/empty-state, sub-domain chip filter, mode query param passthrough
- [x] 8.3 Add `tests/test_web_storage.py` covering new `PaperDatabase` query methods (list_papers, count_papers, get_sub_domain_counts)
- [x] 8.4 Add JS unit tests (optional, if a lightweight runner like `node --test` is acceptable) for `preferences.js` helpers

## 9. Documentation & Verification

- [x] 9.1 Update `CLAUDE.md` with `paper-agent web` command, new files, and architecture notes
- [x] 9.2 Run full test suite (`pytest tests/ -v`) and fix failures
- [x] 9.3 Run linter (`ruff check`) and formatter (`ruff format`) on new files
- [x] 9.4 Manual verification: launch `paper-agent web`, walk through first visit → toggle mode → select keywords → browse → filter → reload → confirm preferences persist
