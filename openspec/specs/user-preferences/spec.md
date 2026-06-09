## ADDED Requirements

### Requirement: localStorage preference schema
The client SHALL store preferences in `localStorage` under the key `paper_agent_prefs` as a JSON object with the shape `{ "mode": "custom" | "all", "subDomains": string[] }`. The default value (when the key is absent) SHALL be `{ "mode": "all", "subDomains": [] }`.

#### Scenario: First visit
- **WHEN** a new visitor opens `/` and `localStorage` has no `paper_agent_prefs` key
- **THEN** the JS treats mode as `all`, `subDomains` as empty, and renders all papers

#### Scenario: Stored value is corrupt or invalid
- **WHEN** `paper_agent_prefs` exists but is not valid JSON or has an unexpected shape
- **THEN** the JS falls back to the default `{ mode: "all", subDomains: [] }` and overwrites the corrupt value

### Requirement: Mode toggle persistence
The preferences UI SHALL include a mode toggle switching between `custom` and `all`. Toggling SHALL immediately write the new value to `localStorage` and re-render the paper list with the new filter applied. Selecting any specific sub-domain through a chip or checkbox SHALL switch mode to `custom` so the selection affects results immediately.

#### Scenario: Switch to custom
- **WHEN** user toggles mode from `all` to `custom`
- **THEN** `paper_agent_prefs.mode` is updated in `localStorage` and the paper list re-fetches using the user's current `subDomains`

#### Scenario: Switch back to all
- **WHEN** user toggles mode back to `all`
- **THEN** `paper_agent_prefs.mode` is updated and the paper list re-fetches showing all papers

#### Scenario: Preference survives reload
- **WHEN** user sets mode to `custom` and reloads the page
- **THEN** the page opens in `custom` mode without prompting

#### Scenario: Selecting domain switches to custom
- **WHEN** user is in `all` mode and selects `quantization` via a chip or checkbox
- **THEN** `paper_agent_prefs.mode` becomes `custom`, `paper_agent_prefs.subDomains` includes `quantization`, and the paper list re-fetches with `sub_domain=quantization`

### Requirement: Sub-domain selection persistence
The preferences UI SHALL render one checkbox per sub-domain (14 total, from `SUB_DOMAINS` keys). Toggling a checkbox SHALL update `paper_agent_prefs.subDomains` in `localStorage` and re-render the paper list. Free-text keywords are NOT supported. In `custom` mode, selected sub-domains SHALL be included as repeated `sub_domain` query parameters on every paper-list fetch.

#### Scenario: Select tags
- **WHEN** user checks `quantization`, `sparsity`, `pruning`
- **THEN** `paper_agent_prefs.subDomains` is `["quantization", "sparsity", "pruning"]` and the paper list filters to papers matching any of those tags

#### Scenario: Deselect a tag
- **WHEN** user unchecks `sparsity`
- **THEN** `paper_agent_prefs.subDomains` becomes `["quantization", "pruning"]` and the list updates

#### Scenario: Empty selection in custom mode
- **WHEN** user is in `custom` mode and all checkboxes are unchecked
- **THEN** the paper list shows zero papers with an explanatory empty-state message ("Select at least one sub-domain in preferences")

#### Scenario: HTMX request includes selected sub-domains
- **WHEN** `paper_agent_prefs.mode = "custom"` and `subDomains = ["quantization", "moe"]`
- **THEN** the paper-list request URL contains `sub_domain=quantization&sub_domain=moe`

#### Scenario: All mode omits sub-domain filters
- **WHEN** `paper_agent_prefs.mode = "all"` and `subDomains = ["quantization"]`
- **THEN** the paper-list request URL omits `sub_domain` parameters and shows all papers

### Requirement: Preferences UI
The app SHALL render a preferences control accessible from the main page (a collapsible panel or modal). The control SHALL display the current mode toggle and the 14 sub-domain checkboxes. The "偏好设置" trigger button SHALL be rendered inline with the main page's 领域筛选 (sub-domain chip filter) row, NOT in the global site header. Pages that do not host the preferences panel (e.g. `/subscribe`) SHALL NOT render the trigger button.

#### Scenario: Open preferences
- **WHEN** user clicks the "偏好设置" button on the main page
- **THEN** the preferences panel opens showing current mode and checked/unchecked sub-domain boxes matching `localStorage`

#### Scenario: Close without changes
- **WHEN** user closes the preferences panel without editing
- **THEN** no `localStorage` writes occur and the paper list is unchanged

#### Scenario: Button placed next to sub-domain filter
- **WHEN** the main page renders
- **THEN** the "偏好设置" button appears as part of the chip-filter row (visually aligned to the right of the 领域筛选 chips), not in the site header

#### Scenario: Button absent on pages without panel
- **WHEN** user visits `/subscribe` (or any page that does not include `#preferences-panel`)
- **THEN** no `#preferences-toggle` element is rendered, so there is no dead button to click

### Requirement: URL mode override
`GET /` SHALL accept an optional `?mode=custom|all` query parameter. When present, the JS SHALL write the value to `localStorage` (replacing the previous mode) before rendering.

#### Scenario: Override to all
- **WHEN** user visits `/?mode=all` with `localStorage.mode = "custom"`
- **THEN** `localStorage.mode` is updated to `all` and all papers are shown

#### Scenario: Invalid mode value ignored
- **WHEN** user visits `/?mode=banana`
- **THEN** the override is ignored and the `localStorage` mode is used

### Requirement: Preferences JS module
A client-side JS module (e.g. `static/preferences.js`) SHALL expose `getPrefs()`, `setMode(mode)`, `setSubDomains(tags)`, and `applyPrefsToUrl()` helpers. All `localStorage` access SHALL go through this module so other scripts don't touch the raw key. The module SHALL expose or internally use a single paper-list URL builder so chip clicks, checkbox changes, search, time range, and pagination preserve each other's filters. The module SHALL avoid duplicate state mutation paths for chips, checkboxes, mode radios, and time range chips.

#### Scenario: getPrefs returns defaults when missing
- **WHEN** `getPrefs()` is called and `localStorage` has no key
- **THEN** it returns `{ mode: "all", subDomains: [] }`

#### Scenario: setSubDomains rejects unknown tags
- **WHEN** `setSubDomains(["quantization", "bogus"])` is called
- **THEN** only valid `SUB_DOMAINS` keys are persisted (the bogus entry is dropped)

#### Scenario: URL builder preserves filters
- **WHEN** current state has search `q=llm`, time range `since=1m`, and custom sub-domains `["quantization"]`
- **THEN** the generated HTMX URL includes `q=llm`, `since=1m`, and `sub_domain=quantization`

#### Scenario: Unified mutation path
- **WHEN** a chip click and a checkbox change select the same sub-domain
- **THEN** both interactions update localStorage, UI state, and paper-list URL through equivalent shared logic

### Requirement: Sub-domain chip filter visual sync

The sub-domain chip filter on the main page SHALL visually reflect the current `subDomains` state in `localStorage` immediately after any interaction that mutates that state. Concretely: every chip element whose `data-tag` attribute matches a selected sub-domain SHALL carry the `chip-active` CSS class; every chip whose tag is NOT selected SHALL NOT carry that class. The same invariant applies to the preferences panel checkboxes (already correct) and the mode radio buttons. Clicking a sub-domain chip SHALL also cause the paper list to re-fetch using the updated selected sub-domains when mode is `custom`.

#### Scenario: Click inactive chip to select
- **WHEN** the user clicks a chip for tag `moe` that does not have the `chip-active` class
- **THEN** the chip gains the `chip-active` class, `paper_agent_prefs.subDomains` is updated to include `moe`, the matching preferences-panel checkbox becomes checked, and the paper list re-fetches with `sub_domain=moe`

#### Scenario: Click active chip to deselect
- **WHEN** the user clicks a chip for tag `moe` that has the `chip-active` class
- **THEN** the chip loses the `chip-active` class, `moe` is removed from `paper_agent_prefs.subDomains`, and the matching checkbox becomes unchecked

#### Scenario: Checkbox change syncs chip visuals
- **WHEN** the user unchecks the `sparsity` checkbox in the preferences panel
- **THEN** the `sparsity` chip on the main page loses the `chip-active` class

#### Scenario: Chip and checkbox state survive page reload
- **WHEN** the user clicks chips `quantization` and `moe`, then reloads the page
- **THEN** on load, both chips display with the `chip-active` class and both checkboxes in the preferences panel are checked

#### Scenario: All chips for the same tag toggle together
- **WHEN** the page renders two chip elements with the same `data-tag="kv_cache"` and the user clicks either one
- **THEN** both chip elements toggle their `chip-active` class in unison

### Requirement: Select all / clear all sub-domain toggle

The preferences panel SHALL render a single toggle button (id `sub-domain-toggle`) above the sub-domain checkbox list. The button text SHALL be "全选" when not all sub-domains are selected, and "取消全选" when all 14 are selected. Clicking the button SHALL toggle between selecting all valid sub-domains and clearing all, updating `paper_agent_prefs.subDomains`, syncing checkbox/chip states, updating the button text, and refreshing the paper list.

#### Scenario: Click toggle when none selected
- **WHEN** no sub-domains are selected and user clicks the button (labeled "全选")
- **THEN** all 14 sub-domain checkboxes become checked, `paper_agent_prefs.subDomains` contains all valid tags, all corresponding chips gain the `chip-active` class, the button text becomes "取消全选", and the paper list re-fetches

#### Scenario: Click toggle when all selected
- **WHEN** all 14 sub-domains are selected and user clicks the button (labeled "取消全选")
- **THEN** all sub-domain checkboxes become unchecked, `paper_agent_prefs.subDomains` becomes `[]`, all chips lose the `chip-active` class, the button text becomes "全选", and the paper list re-fetches

#### Scenario: Click toggle when partially selected
- **WHEN** some (but not all) sub-domains are selected and user clicks the button (labeled "全选")
- **THEN** all 14 sub-domain checkboxes become checked, `paper_agent_prefs.subDomains` contains all valid tags, and the button text becomes "取消全选"

#### Scenario: Toggle state persists across page reload
- **WHEN** user clicks the toggle to select all sub-domains and reloads the page
- **THEN** all 14 checkboxes are checked, all chips are active, and the button is labeled "取消全选"
