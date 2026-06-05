## MODIFIED Requirements

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
