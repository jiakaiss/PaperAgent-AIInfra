## ADDED Requirements

### Requirement: Sub-domain chip filter visual sync

The sub-domain chip filter on the main page SHALL visually reflect the current `subDomains` state in `localStorage` immediately after any interaction that mutates that state. Concretely: every chip element whose `data-tag` attribute matches a selected sub-domain SHALL carry the `chip-active` CSS class; every chip whose tag is NOT selected SHALL NOT carry that class. The same invariant applies to the preferences panel checkboxes (already correct) and the mode radio buttons.

#### Scenario: Click inactive chip to select
- **WHEN** the user clicks a chip for tag `moe` that does not have the `chip-active` class
- **THEN** the chip gains the `chip-active` class, `paper_agent_prefs.subDomains` is updated to include `moe`, and the matching preferences-panel checkbox becomes checked

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
