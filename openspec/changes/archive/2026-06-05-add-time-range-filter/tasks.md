## 1. Storage Layer

- [x] 1.1 Add `published_after: date | None = None` parameter to `PaperDatabase.list_papers()`. Extend the existing `_build_filter_clause()` (or inline WHERE construction) with `AND published >= ?` when `published_after` is provided. Pass the ISO date string as the bound parameter.
- [x] 1.2 Add `published_after: date | None = None` parameter to `PaperDatabase.count_papers()`. Use the same filter clause extension so count and list stay in sync.
- [x] 1.3 Extend `tests/test_web_storage.py` with time range filter cases: (a) `list_papers(published_after=...)` returns only recent papers, (b) `count_papers(published_after=...)` matches the total from paginating `list_papers`, (c) time range combines with `sub_domains` and `search` using AND logic.

## 2. Backend Routes

- [x] 2.1 Add a `_parse_since(since: str | None) -> date | None` helper in `routes.py`. Map `1w`→7 days, `1m`→30 days, `3m`→90 days, `6m`→180 days, `1y`→365 days, `3y`→1095 days. Return `None` for missing or invalid values (no filter applied). Use `date.today() - timedelta(days=...)` for the conversion.
- [x] 2.2 Add `since: str | None = Query(None)` parameter to the `index()` route handler. Convert via `_parse_since()`, pass as `published_after` to `_compute_page_context()`. Include `since` in the template context so the chip group can render the active state.
- [x] 2.3 Add `since: str | None = Query(None)` parameter to the `paper_list_fragment()` route handler. Same conversion and pass-through. Include `since` in the `_paper_list.html` template context if needed for empty-state messaging.
- [x] 2.4 Update `_compute_page_context()` to accept and forward `published_after: date | None` to `db.list_papers()` and `db.count_papers()`.
- [x] 2.5 Extend `tests/test_web_browsing.py` with route-level time range tests: (a) `GET /?since=1m` returns only papers from the past month, (b) `GET /?since=invalid` ignores the filter, (c) `GET /?since=6m&sub_domain=quantization` combines filters with AND logic, (d) `GET /?since=1y&q=flashattention` combines with search.

## 3. Frontend Template

- [x] 3.1 Add a time range chip group to `index.html` below the sub-domain chip filter. Render 7 chips: "All time" (no `?since=`), "1 week" (`1w`), "1 month" (`1m`), "3 months" (`3m`), "6 months" (`6m`), "1 year" (`1y`), "3 years" (`3y`). Mark the active chip with `chip-active` class based on the `since` template variable. Use `onclick="PaperAgentPrefs.setSince('...')"` for each chip.
- [x] 3.2 Add `since` to the server-context JSON block in `index.html` so the JS module knows the active time range on page load: `"serverSince": {{ since | tojson }}`.

## 4. Frontend JavaScript

- [x] 4.1 Add `setSince(value)` function to `preferences.js`. Accept one of `1w`, `1m`, `3m`, `6m`, `1y`, `3y`, or `""` (all time). Update the URL bar via `replaceState` with the new `?since=` value (or remove the param for all time), then call `refreshPaperList()`. Sync the time range chip active states.
- [x] 4.2 Add `_syncTimeChips(since)` helper to `preferences.js`. Mark the chip whose `data-since` matches the current value with `chip-active`; remove it from all others. Call this from `syncAllUI()` and `setSince()`.
- [x] 4.3 Update `buildQueryString()` in `preferences.js` to include the `since` param when building the HTMX URL for `/_paper_list`. Read the current since value from the active chip or a module-level variable.
- [x] 4.4 Update `refreshPaperList()` and `_syncUrlBar()` in `preferences.js` to include the time range in the URL.
- [x] 4.5 Add time range chip click handlers in `app.js` (or rely on inline `onclick` from the template). Ensure the active chip state is correct on page load when `?since=` is present in the URL.
- [x] 4.6 Extend `tests/js/preferences.test.mjs` with time range tests: (a) `setSince('1m')` updates the URL and chip active state, (b) `setSince('')` removes the since param, (c) `_syncTimeChips` marks the correct chip as active.

## 5. CSS

- [x] 5.1 Add styles for the time range chip group in `style.css`. Use the same chip styling as the sub-domain filter. Add `flex-wrap: wrap` so chips wrap on narrow screens (< 768px). Add a label "时间范围:" matching the "领域筛选:" label style.

## 6. Verification

- [x] 6.1 Run `pytest tests/ -v` and verify all existing and new tests pass.
- [x] 6.2 Run `ruff check src/ tests/` and `ruff format src/ tests/` to ensure lint compliance.
- [x] 6.3 Run `node --test tests/js/preferences.test.mjs` and verify all JS tests pass.
- [x] 6.4 Manual verification: launch `paper-agent web`, click each time range chip, verify URL updates, chip active state, and paper list re-fetches correctly. Test combined filters (time range + sub-domain + search). Test page reload preserves time range state.
