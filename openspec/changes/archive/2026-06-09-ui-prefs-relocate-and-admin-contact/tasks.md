## 1. Config

- [x] 1.1 Add optional `admin_contact: str = ""` field to `WebConfig` in `src/paper_agent/config.py` (right after `public_base_url`).
- [x] 1.2 Document the field in `config.example.yaml` under the existing web section, with a one-line comment showing both name+email and email-only examples.
- [x] 1.3 Add unit tests in `tests/test_config.py` covering: default value is `""`; a yaml file with the field round-trips intact; a yaml file omitting the field still loads (no migration).

## 2. Subscribe page server side

- [x] 2.1 In `subscribe_page` (`src/paper_agent/web/routes.py`), pull `admin_contact = config.web.admin_contact if config else ""` and pass it into the `subscribe.html` template context.
- [x] 2.2 In `subscribe_api` (the POST handler), compute the contact suffix once at the top via a small local helper (e.g. `def _suffix(c): return f"（{c}）" if c else ""`).
- [x] 2.3 Append the suffix to every `请联系管理员…` error string in `subscribe_api` (currently 4 occurrences). Keep the existing `请联系管理员` substring intact as a prefix so existing substring assertions in tests don't break.

## 3. Subscribe page template

- [x] 3.1 In `src/paper_agent/web/templates/subscribe.html`, update the 订阅规则 line that says `请<strong>联系管理员</strong>添加` to render `（{{ admin_contact }}）` after 管理员 when `admin_contact` is truthy.
- [x] 3.2 Apply the same `{% if admin_contact %}（{{ admin_contact }}）{% endif %}` snippet to the access-code section's `请联系管理员获取访问码` (if present in the template).

## 4. Header → chip-filter button relocation

- [x] 4.1 Delete the `<button id="preferences-toggle">…</button>` line from `src/paper_agent/web/templates/base.html`.
- [x] 4.2 In `src/paper_agent/web/templates/index.html`, append the relocated button as the last child of the `.chip-filter` div (after the chips `{% endfor %}`) with class `chip-filter-prefs-btn`.
- [x] 4.3 Add a CSS rule in `src/paper_agent/web/static/style.css` near the existing `.chip-filter` block: `.chip-filter-prefs-btn { margin-left: auto; }`.

## 5. Web tests

- [x] 5.1 In `tests/test_web_browsing.py` (or the most appropriate web test file), add a test asserting `id="preferences-toggle"` is present on `GET /` and absent on `GET /subscribe`.
- [x] 5.2 In `tests/test_subscription_api.py`, add a test that with default config, `GET /subscribe` response does NOT contain `（` after the 管理员 token (i.e., no parenthetical leaks).
- [x] 5.3 In `tests/test_subscription_api.py`, add a test that with `config.web.admin_contact = "admin@example.com"`, the `GET /subscribe` response contains the substring `联系管理员（admin@example.com）`.
- [x] 5.4 In `tests/test_subscription_api.py`, extend one existing error-path test to assert the same suffix appears in the error fragment when `admin_contact` is configured.
- [x] 5.5 (Optional) Assert HTML autoescape works: configure `admin_contact = "<b>x</b>"`, GET `/subscribe`, assert raw `<b>` is NOT in the body — escaped form `&lt;b&gt;` is.

## 6. Verify end-to-end

- [x] 6.1 Run `pytest tests/ -v` — all green.
- [x] 6.2 Run `ruff check src/ tests/` — clean.
- [x] 6.3 Manually load `/` in a browser: confirm the 偏好设置 button sits at the right edge of the 领域筛选 row and the panel still opens.
- [x] 6.4 Manually load `/subscribe` (with `admin_contact` unset, then with it set in `config.yaml` after restart): confirm no header button and the parenthetical appears/disappears as expected.
