## Why

Users browsing papers in the web UI want to filter by publication date to see recent papers (past week, month, 3 months, 6 months, 1 year, or 3 years). Currently the paper list has no time-based filtering — users see all scored papers sorted by relevance, with no way to focus on recent work.

## What Changes

- **Backend**: Extend `PaperDatabase.list_papers()` and `count_papers()` to accept a `published_after: date | None` parameter that filters papers by their `published` date column.
- **Backend**: Add a `?since=` query parameter to the `GET /` and `GET /_paper_list` routes accepting values like `1w`, `1m`, `3m`, `6m`, `1y`, `3y` (relative to today).
- **Frontend**: Add a time range selector UI (dropdown or chip group) to the paper browsing page, defaulting to "all time" (no filter).
- **Frontend**: Wire time range changes to HTMX requests — when the user selects a time range, re-fetch the paper list with the new `?since=` param.
- **Frontend**: Update the URL bar to reflect the current time range (via `replaceState`) so filtered views are shareable and bookmarkable.

## Capabilities

### New Capabilities

(none — time range filtering is an extension of the existing paper browsing capability)

### Modified Capabilities

- `paper-browsing`: The paper list endpoint and `PaperDatabase` query methods gain a `published_after` filter. The UI gains a time range selector. The URL accepts a `?since=` parameter.

## Impact

- **Backend**: `src/paper_agent/storage/database.py` — extend `list_papers()` and `count_papers()` signatures.
- **Backend**: `src/paper_agent/web/routes.py` — parse `?since=` param, convert to `published_after` date, pass to storage methods.
- **Frontend**: `src/paper_agent/web/templates/index.html` — add time range selector UI.
- **Frontend**: `src/paper_agent/web/static/app.js` — wire time range changes to HTMX requests and URL updates.
- **Tests**: Extend `tests/test_web_storage.py` and `tests/test_web_browsing.py` with time range filter cases.
- **No changes** to notifier, pipeline, config, CLI, or localStorage preferences (time range is URL-only, not persisted).
