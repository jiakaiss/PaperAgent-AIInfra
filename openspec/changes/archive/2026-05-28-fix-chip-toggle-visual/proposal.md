## Why

When users click a sub-domain chip on the main page while in "custom" mode, the chip's visual state (active/inactive color) does not update, even though the underlying data (paper count, paper list) refreshes correctly. This creates a confusing UX: users think their click didn't register, or that the chip is broken. The issue is a JS-side bug — the chip's `chip-active` CSS class is only toggled when the preferences panel checkbox changes, not when the main-page chip itself is clicked.

## What Changes

- Fix `preferences.js` so that `toggleSubDomain()` / `toggleChip()` also toggles the visual state of every chip matching that tag on the page (both in the main-page chip filter and, if visible, in the preferences panel checkboxes).
- Add a regression test (JS unit test or E2E check) to verify the chip's `chip-active` class reflects `subDomains` after a click.
- Clarify in the spec that the chip filter's visual state is always in sync with the persisted `subDomains` array.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `user-preferences`: The sub-domain chip filter on the main page must visually reflect the current `subDomains` state immediately after a click — the clicked chip (and any matching chip elsewhere on the page) must toggle its active styling in sync with the persisted preference.

## Impact

- Client-side JS only: `src/paper_agent/web/static/preferences.js` (and possibly `app.js`).
- No backend, storage, or API changes.
- Existing web tests (`test_web_browsing.py`) are unaffected since they don't execute JS.
