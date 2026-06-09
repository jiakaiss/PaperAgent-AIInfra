## MODIFIED Requirements

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
