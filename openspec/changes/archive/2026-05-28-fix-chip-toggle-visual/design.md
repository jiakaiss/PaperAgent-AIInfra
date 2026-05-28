## Context

The `web-frontend` change shipped a main-page chip filter (sub-domain tags) that toggles the persisted `subDomains` array in `localStorage` and re-fetches the paper list via HTMX. The preferences panel has an equivalent set of 14 checkboxes. Both are supposed to stay in sync visually — if you check a checkbox, the chip turns active-blue; if you click a chip, the checkbox gets checked.

**Observed bug**: Clicking a chip calls `PaperAgentPrefs.toggleChip(tag)` → `toggleSubDomain(tag)` → `refreshPaperList()`. The data persists and the HTMX request fires (paper count updates), but the chip's `chip-active` CSS class is never toggled. The chip still looks inactive. Checkbox state in the (hidden) preferences panel is also not updated.

In `app.js`, the checkbox `change` handler calls `_syncChips(checked)` to update chip visuals — but only in the checkbox→chip direction. There is no equivalent chip→checkbox sync path.

## Goals / Non-Goals

**Goals:**
- Clicking a chip toggles its own `chip-active` class immediately (no flicker, no race with the HTMX swap).
- Clicking a chip also updates the matching checkbox in the preferences panel (checked/unchecked), so the two UIs stay consistent if the user opens the panel later.
- The fix is small, localized to `preferences.js` (the source of the `toggleSubDomain`/`toggleChip` helpers), with at most a supporting helper in `app.js`.

**Non-Goals:**
- Rewriting the preferences/chip architecture.
- Adding two-way data binding or a JS framework.
- Persisting chip state anywhere new — `localStorage` is already correct; only the DOM is out of sync.

## Decisions

### 1. Single source of truth for visual sync: `_syncAllUI()` helper

**Decision:** Add a `_syncAllUI(prefs)` helper that updates both chip `chip-active` classes and checkbox `checked` states from the current prefs. Call it after every mutation (`setMode`, `setSubDomains`, `toggleSubDomain`) and on initial bootstrap.

**Alternatives considered:**
- *Per-element toggle inside `toggleChip`*: simpler but risks drift — e.g., calling `setSubDomains` from a different code path wouldn't update visuals consistently.
- *MutationObserver on localStorage*: overkill; we control all writes through `PaperAgentPrefs`.

**Rationale:** Centralizing the sync keeps the invariant ("DOM reflects prefs") in one place. Every mutation path calls the same function.

### 2. `_syncAllUI` lives in `preferences.js`, not `app.js`

**Decision:** Put `_syncAllUI` in the preferences module so it can be invoked right after `_persist()` inside `setMode`/`setSubDomains`/`toggleSubDomain` without a circular dependency on `app.js`. `app.js` continues to own event-listener wiring and bootstrap.

**Rationale:** `preferences.js` is already the "owner" of prefs state; letting it also own the DOM-sync side effect avoids the bootstrap code needing to remember to call sync manually after each mutation.

### 3. No new spec file; add an ADDED requirement to `user-preferences`

**Decision:** Add one new requirement — "Sub-domain chip filter visual sync" — to the existing `user-preferences` capability spec. The paper-browsing spec is untouched because it concerns URL-based filtering, not interactive chip clicks.

**Rationale:** The bug is about preferences state being rendered consistently across the two UI surfaces (panel + chips). That belongs in `user-preferences`.

## Risks / Trade-offs

- **[Race with HTMX swap]** The HTMX swap replaces `#paper-list-container` only, not the chip filter, so chip DOM state survives the swap. No race. → Mitigation: none needed.
- **[Multiple chips per tag]** If the UI ever renders the same tag twice (e.g., a second chip filter elsewhere), `_syncAllUI` queries by `data-tag` attribute and toggles all matches. → Mitigation: the current `querySelectorAll("[data-tag=...]")` loop already handles N chips.
- **[Bootstrap path]** On first page load, `_syncAllUI` is called by `app.js` after `applyPrefsToUrl()`; no change to the existing bootstrap order is required — we just replace the three separate `_syncModeRadios`/`_syncCheckboxes`/`_syncChips` calls with one `_syncAllUI(prefs)`. → Mitigation: keep the individual helpers as private, called internally by `_syncAllUI`.
