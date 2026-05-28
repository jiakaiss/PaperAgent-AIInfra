## 1. Core JS Fix

- [x] 1.1 Add a `_syncAllUI(prefs)` helper in `src/paper_agent/web/static/preferences.js` that updates mode radio buttons, sub-domain checkboxes, and every chip's `chip-active` class from the given prefs
- [x] 1.2 Expose `_syncAllUI` on the global `PaperAgentPrefs` object so `app.js` can call it
- [x] 1.3 Call `_syncAllUI(prefs)` at the end of `setMode()`, `setSubDomains()`, and `toggleSubDomain()` so every mutation path re-syncs the DOM
- [x] 1.4 Remove the duplicate inline chip/checkbox sync in `toggleChip()` (the new `_syncAllUI` call covers it)

## 2. Bootstrap Cleanup

- [x] 2.1 In `src/paper_agent/web/static/app.js`, replace the three separate `_syncModeRadios` / `_syncCheckboxes` / `_syncChips` calls on DOMContentLoaded with a single `PaperAgentPrefs.syncAllUI(prefs)` call
- [x] 2.2 Keep the individual `_sync*` helpers as private (not exposed) so only `_syncAllUI` is the public sync entry point

## 3. Testing

- [x] 3.1 Add JS unit tests (using `node --test` or a tiny inline harness) for `_syncAllUI`: chip `chip-active` class reflects `prefs.subDomains`; checkbox `checked` reflects the same; mode radio matches `prefs.mode`
- [x] 3.2 Add a regression test that simulates a chip click end-to-end: click a chip → verify its class toggled → verify the matching checkbox flipped → verify `localStorage` was updated

## 4. Verification

- [x] 4.1 Run `pytest tests/ -v` and confirm the existing 100 web/pipeline tests still pass
- [x] 4.2 Run `ruff check src/ tests/` and `ruff format` on any touched Python files
- [x] 4.3 Manual verification: launch `paper-agent web`, switch to custom mode, click chips — confirm they change color, the matching checkbox updates when the preferences panel is opened, and a page reload preserves both states
