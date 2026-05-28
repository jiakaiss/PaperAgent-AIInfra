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
The preferences UI SHALL include a mode toggle switching between `custom` and `all`. Toggling SHALL immediately write the new value to `localStorage` and re-render the paper list with the new filter applied.

#### Scenario: Switch to custom
- **WHEN** user toggles mode from `all` to `custom`
- **THEN** `paper_agent_prefs.mode` is updated in `localStorage` and the paper list re-fetches using the user's current `subDomains`

#### Scenario: Switch back to all
- **WHEN** user toggles mode back to `all`
- **THEN** `paper_agent_prefs.mode` is updated and the paper list re-fetches showing all papers

#### Scenario: Preference survives reload
- **WHEN** user sets mode to `custom` and reloads the page
- **THEN** the page opens in `custom` mode without prompting

### Requirement: Sub-domain selection persistence
The preferences UI SHALL render one checkbox per sub-domain (14 total, from `SUB_DOMAINS` keys). Toggling a checkbox SHALL update `paper_agent_prefs.subDomains` in `localStorage` and re-render the paper list. Free-text keywords are NOT supported.

#### Scenario: Select tags
- **WHEN** user checks `quantization`, `sparsity`, `pruning`
- **THEN** `paper_agent_prefs.subDomains` is `["quantization", "sparsity", "pruning"]` and the paper list filters to papers matching any of those tags

#### Scenario: Deselect a tag
- **WHEN** user unchecks `sparsity`
- **THEN** `paper_agent_prefs.subDomains` becomes `["quantization", "pruning"]` and the list updates

#### Scenario: Empty selection in custom mode
- **WHEN** user is in `custom` mode and all checkboxes are unchecked
- **THEN** the paper list shows zero papers with an explanatory empty-state message ("Select at least one sub-domain in preferences")

### Requirement: Preferences UI
The app SHALL render a preferences control accessible from the main page (a collapsible panel or modal). The control SHALL display the current mode toggle and the 14 sub-domain checkboxes.

#### Scenario: Open preferences
- **WHEN** user clicks the "偏好设置" button
- **THEN** the preferences panel opens showing current mode and checked/unchecked sub-domain boxes matching `localStorage`

#### Scenario: Close without changes
- **WHEN** user closes the preferences panel without editing
- **THEN** no `localStorage` writes occur and the paper list is unchanged

### Requirement: URL mode override
`GET /` SHALL accept an optional `?mode=custom|all` query parameter. When present, the JS SHALL write the value to `localStorage` (replacing the previous mode) before rendering.

#### Scenario: Override to all
- **WHEN** user visits `/?mode=all` with `localStorage.mode = "custom"`
- **THEN** `localStorage.mode` is updated to `all` and all papers are shown

#### Scenario: Invalid mode value ignored
- **WHEN** user visits `/?mode=banana`
- **THEN** the override is ignored and the `localStorage` mode is used

### Requirement: Preferences JS module
A client-side JS module (e.g. `static/preferences.js`) SHALL expose `getPrefs()`, `setMode(mode)`, `setSubDomains(tags)`, and `applyPrefsToUrl()` helpers. All `localStorage` access SHALL go through this module so other scripts don't touch the raw key.

#### Scenario: getPrefs returns defaults when missing
- **WHEN** `getPrefs()` is called and `localStorage` has no key
- **THEN** it returns `{ mode: "all", subDomains: [] }`

#### Scenario: setSubDomains rejects unknown tags
- **WHEN** `setSubDomains(["quantization", "bogus"])` is called
- **THEN** only valid `SUB_DOMAINS` keys are persisted (the bogus entry is dropped)
