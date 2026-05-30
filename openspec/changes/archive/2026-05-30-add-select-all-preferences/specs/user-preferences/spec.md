## ADDED Requirements

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
