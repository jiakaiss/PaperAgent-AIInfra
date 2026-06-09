## Context

Two UX papercuts surfaced during operator use:
- 偏好设置 toggle in the global header is dead on `/subscribe` (the panel only exists on `/`).
- The subscribe page tells users to contact the admin but provides no actual contact handle.

Current state:
- `src/paper_agent/web/templates/base.html:21` renders the global `<button id="preferences-toggle">`.
- `src/paper_agent/web/templates/index.html:6-66` holds the `<aside id="preferences-panel">` sidebar.
- `src/paper_agent/web/static/app.js:40-53` wires the toggle — already null-guards a missing button.
- `src/paper_agent/web/templates/subscribe.html:19` hardcodes `<strong>联系管理员</strong>添加`.
- `src/paper_agent/config.py:297-302` defines `WebConfig { min_quality, public_base_url }`.

## Goals / Non-Goals

**Goals:**
- Button visible **only** where the panel exists.
- Operator-configurable contact info, gracefully absent when unset.
- Zero-impact for users who don't set the new config field.

**Non-Goals:**
- Redesigning the preferences panel itself.
- Internationalizing the admin contact label.
- Building a full "operator profile" with multiple fields (name + email + Slack). One free-form string only.

## Decisions

### Move the button, leave the panel

- **Why move only the button?** The user asked for the *button* to be co-located with 领域筛选. The panel works as a sidebar and the user did not complain about it. Moving the panel would be a larger CSS refactor with no asked-for benefit.
- **Why right-aligned inside `.chip-filter`?** `.chip-filter` is already a flex row. `margin-left: auto` on the button pushes it to the row's right edge — visually balanced with the search bar above and naturally associated with the领域 chips. Alternatives ruled out:
  - *Separate row above chips* — adds a lonely floating button; vertical clutter.
  - *Gear icon* — loses the "偏好设置" label; needs a new icon asset.

### Put `admin_contact` in `WebConfig`, not `AdminConfig`

- `AdminConfig` (`config.py:358-372`) is explicitly the operator-only HTTP Basic Auth gate for `/admin`. Stashing a *public-facing* contact string there couples "show contact info" to "admin dashboard enabled", which is wrong semantically and breaks if someone runs the public site without enabling the dashboard.
- `WebConfig` already documents itself as "web-facing features" and houses `public_base_url` — exactly the same flavor.

### Single free-form string, not name + email

User said "**名字或邮箱**" (name **or** email). A single optional string lets the operator write whatever's appropriate (`"张三 <admin@example.com>"`, `"@AdminAlice on Slack"`, plain email, …) without us imposing format.

### Pass via template context, not Jinja2 global

Only `subscribe.html` needs `admin_contact` today. Plumbing it through `app.state` or a context processor invites accidental exposure on unrelated templates; passing it explicitly from the two route handlers that need it stays local and grep-able.

### Suffix in error strings too, for consistency

The subscribe POST handler has four `请联系管理员…` server-side error strings. If the form shows `联系管理员（admin@example.com）` but errors show only `联系管理员`, users get inconsistent guidance. A tiny local helper `_contact_suffix(s) → "（s）" | ""` keeps the four f-strings readable.

## Risks / Trade-offs

- **[Risk]** A user with a stale browser cache still sees the old `base.html` (header button) but loads new `index.html` (also has button) → two buttons briefly.
  - **Mitigation**: existing `style_version` / `app_version` cache-busting in `app.py:36-51` invalidates on file mtime change.
- **[Risk]** Operator pastes raw HTML or `<script>` into `admin_contact`.
  - **Mitigation**: Jinja2 autoescape is on by default; `{{ admin_contact }}` is escaped. Server-side error strings use Python f-strings inside JSON template context, also escaped on render. Adding a `len(s) ≤ 200` check in the validator would be defensive but cosmetic.
- **[Trade-off]** Putting the toggle inside `.chip-filter` means the button wraps to a new line on very narrow viewports (≤ ~480px). Acceptable — the page already wraps chips at that width.

## Migration Plan

- No DB migration. No JS API change. No notifier change.
- Existing `config.yaml` files remain valid (new field defaults to `""`).
- Rollout is a single commit; no feature flag needed.
- Rollback = revert the commit.

## Open Questions

None — design questions resolved during exploration.
