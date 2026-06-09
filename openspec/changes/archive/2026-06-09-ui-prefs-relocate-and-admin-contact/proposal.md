## Why

Two small UX problems in the web frontend bug the operator:
1. The **偏好设置** button lives in the global header but the panel it controls only exists on the home page (`/`). On `/subscribe` the button is rendered but inert — clicking it does nothing because there's no panel to toggle.
2. The subscribe page tells users "如需新增类别，请联系管理员添加" without telling them **how** to reach the admin. The operator has no way to publish their contact (name / email / chat handle) other than editing the template by hand.

## What Changes

- **Move the 偏好设置 toggle** out of `base.html` (global header) into `index.html`'s `.chip-filter` row, right-aligned next to the 领域筛选 chips. Result: the button only appears where it works, and the panel still opens/closes via the same JS.
- **Add a new optional config field** `web.admin_contact: str = ""`. When set, the subscribe page renders it as a parenthetical after 管理员: `联系管理员（admin@example.com）`. When empty, the page reads exactly as today (no parenthetical). The same suffix appears in the four `请联系管理员…` error strings emitted by the subscribe form's server-side validation, for consistency.

No breaking changes — the config field defaults to empty string, the panel JS already null-guards the missing button, and the existing `请联系管理员` substring is preserved as a prefix in all touched strings.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `user-preferences`: relocates the 偏好设置 toggle from the global header into the index page's chip-filter row. Panel behavior, localStorage schema, and JS API are unchanged.
- `subscription-form`: subscribe page and the four server-side error messages SHALL include the optional `web.admin_contact` value as a parenthetical after 管理员 when configured.

## Impact

- **Code**:
  - `src/paper_agent/config.py` — `WebConfig` gains one optional field.
  - `src/paper_agent/web/routes.py` — `/subscribe` route passes `admin_contact` to template; subscribe POST handler appends the suffix to error strings.
  - `src/paper_agent/web/templates/base.html` — removes the `<button id="preferences-toggle">` line.
  - `src/paper_agent/web/templates/index.html` — adds the relocated button at the end of `.chip-filter`.
  - `src/paper_agent/web/templates/subscribe.html` — two `{% if admin_contact %}…{% endif %}` insertions.
  - `src/paper_agent/web/static/style.css` — one new rule for right-aligning the relocated button.
- **Config**: `config.yaml` / `config.example.yaml` gain a new optional `web.admin_contact` field; existing configs remain valid (defaults to `""`).
- **Tests**: extends `tests/test_config.py`, `tests/test_subscription_api.py`, and adds two assertions in web template tests for button presence/absence.
- **No DB migration. No JS API change. No notifier change.**
