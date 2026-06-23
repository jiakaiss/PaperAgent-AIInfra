## Why

Email digests today land in the user's inbox with no easy path back to the
full Paper Agent web UI — to browse beyond the curated digest (e.g. filter by
tier, search older papers, change preferences) a recipient must remember or
look up the deployment URL. Surfacing a single prominent link at the top of
every digest closes this loop, mirrors how every well-formed newsletter
already works, and is essentially free given `config.web.public_base_url` is
already plumbed through for the unsubscribe link.

## What Changes

- Render a "🔗 在网页中浏览全部论文" link near the top of each digest email,
  pointing at `config.web.public_base_url` when configured.
- Thread `public_base_url` from `WebConfig` into `EmailNotifierConfig` at
  subscription-conversion time (same path that already copies SMTP creds and
  the unsubscribe URL).
- `format_email_html()` accepts a new optional `web_url: str = ""` parameter;
  when empty the header link is omitted (preserves current output for tests
  and any caller that doesn't pass it).
- No change to digest payload, scoring, or filtering — purely a presentation
  addition.

## Capabilities

### New Capabilities

- `email-digest-header`: rules for the meta links rendered above the paper
  table in digest emails (currently the web-UI link; future home for any
  similar header CTAs).

### Modified Capabilities

<!-- None — existing capabilities (global-email-config, unsubscribe-management)
     stay structurally unchanged; this only adds a new header element. -->

## Impact

- `src/paper_agent/config.py` — add `web_url` field to `EmailNotifierConfig`.
- `src/paper_agent/formatter/templates.py` — `format_email_html` accepts and
  renders the new header link.
- `src/paper_agent/notifier/email_notifier.py` — forwards `config.web_url`
  into the formatter.
- `src/paper_agent/subscriptions.py` — copies `config.web.public_base_url`
  into each subscription's `EmailNotifierConfig.web_url` at conversion time
  (same pattern as `unsubscribe_url`).
- Tests: `tests/test_templates.py` (header rendered when URL set, omitted
  otherwise), `tests/test_email_notifier.py` (notifier passes URL through),
  `tests/test_subscriptions.py` (conversion copies the URL).
- No DB schema changes, no new env vars, no breaking changes — existing
  `config.yaml` files without `web.public_base_url` simply render emails
  without the new link, identical to today.
