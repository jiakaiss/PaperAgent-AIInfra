## 1. Frontend Template

- [x] 1.1 Add "全选" and "取消全选" buttons in `index.html` preferences panel, between the mode toggle section and the sub-domain checkbox list. Use `onclick="PaperAgentPrefs.setSubDomains(PaperAgentPrefs.getValidSubDomains())"` for select all and `onclick="PaperAgentPrefs.setSubDomains([])"` for clear all. Apply `btn btn-sm` CSS classes.

## 2. Frontend CSS

- [x] 2.1 Add button styling for the select-all/clear-all button group in `style.css`. Ensure buttons are spaced correctly and visually consistent with the preferences panel aesthetic.

## 3. Tests

- [x] 3.1 Add JS unit tests in `tests/js/preferences.test.mjs`: (a) calling `setSubDomains(getValidSubDomains())` selects all checkboxes and chips, (b) calling `setSubDomains([])` clears all checkboxes and chips, (c) no-op when already in the target state.

## 4. Verification

- [x] 4.1 Run `node --test tests/js/preferences.test.mjs` and verify all tests pass.
- [x] 4.2 Manual verification: launch `paper-agent web`, open preferences panel, click "全选" to verify all checkboxes and chips activate, click "取消全选" to verify all clear. Verify paper list updates correctly.
