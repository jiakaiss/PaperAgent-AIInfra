## MODIFIED Requirements

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

### Requirement: Preferences JS module
A client-side JS module (e.g. `static/preferences.js`) SHALL expose `getPrefs()`, `setMode(mode)`, `setSubDomains(tags)`, and `applyPrefsToUrl()` helpers. All `localStorage` access SHALL go through this module so other scripts don't touch the raw key. The module SHALL expose or internally use a single paper-list URL builder so chip clicks, checkbox changes, search, time range, and pagination preserve each other's filters.

#### Scenario: getPrefs returns defaults when missing
- **WHEN** `getPrefs()` is called and `localStorage` has no key
- **THEN** it returns `{ mode: "all", subDomains: [] }`

#### Scenario: setSubDomains rejects unknown tags
- **WHEN** `setSubDomains(["quantization", "bogus"])` is called
- **THEN** only valid `SUB_DOMAINS` keys are persisted (the bogus entry is dropped)

#### Scenario: URL builder preserves filters
- **WHEN** current state has search `q=llm`, time range `since=1m`, and custom sub-domains `["quantization"]`
- **THEN** the generated HTMX URL includes `q=llm`, `since=1m`, and `sub_domain=quantization`

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
