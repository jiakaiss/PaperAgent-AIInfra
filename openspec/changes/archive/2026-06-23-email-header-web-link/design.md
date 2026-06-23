## Context

`config.web.public_base_url` is already configured by operators today and
used by `subscriptions.build_unsubscribe_url()` to assemble signed
unsubscribe links inside each email. The same value identifies the
deployment's web UI root — exactly what a recipient would click to browse
beyond the digest. This change reuses that existing config field; no new
operator setup is required.

The email rendering path is small and well-isolated:
`EmailNotifier._build_message` → `format_email_html(papers, unsubscribe_url=...)`.
Adding a second optional URL parameter follows the established pattern.

## Goals / Non-Goals

**Goals:**
- Recipients can click a single link in any digest to land on the Paper
  Agent web UI root.
- Zero operator action required when `web.public_base_url` is already set.
- Behavior unchanged when `web.public_base_url` is empty (graceful degrade,
  matches today's emails).

**Non-Goals:**
- Per-paper deep-links from email rows back into specific web-UI filter
  states. Each paper already links to its arXiv abstract; deep-linking to
  the web UI's filtered view is a future enhancement.
- A new operator config knob. The web URL is already known — we don't add a
  parallel `email.web_url` to `config.yaml`.
- Changing the unsubscribe-link block at the bottom (still rendered as
  today, separately from the new top-of-email link).

## Decisions

**Decision 1: Reuse `config.web.public_base_url` instead of a new field.**
Operators already set this for unsubscribe links. Adding a parallel
`email.web_url` invites drift (two URLs pointing at the same server) and
extra docs. Trade-off: callers that want a *different* URL for the email
link than for unsubscribe links can't have one — accepted; nobody has
asked for that.

**Decision 2: Thread the URL through `EmailNotifierConfig.web_url` rather
than passing it into `format_email_html` from the notifier directly via
config lookup.** The notifier already takes only `EmailNotifierConfig` —
it has no reference back to `AppConfig`. Adding `web_url` to
`EmailNotifierConfig` and populating it at subscription-conversion time
(in `subscriptions.build_subscription_email_config`) mirrors how
`unsubscribe_url` is already plumbed through. Alternative considered:
pass `AppConfig` into the notifier — rejected, leaks global config into a
per-user object.

**Decision 3: Render the link as a short prose line above the date/count
line, not inside the table.** Email clients render `<table>` reliably but
links *inside* the same first row as the count could look like a paper
row. A standalone `<p>` with a clearly-marked icon (🔗) above the date
line reads unambiguously as a meta navigation element.

**Decision 4: `format_email_html(web_url="")` — empty string ⇒ omit the
header link entirely.** Mirrors the existing `unsubscribe_url=""` convention
in the same function signature. Tests that don't supply `web_url` get
byte-identical output to today.

## Risks / Trade-offs

- **[Risk]** Operators with `public_base_url` pointing at an internal-only
  hostname (e.g. `http://localhost:8000`) would surface a broken link to
  external recipients. → **Mitigation**: documented in the existing
  `WebConfig` docstring; same risk already exists for unsubscribe links, so
  no new surface area.
- **[Risk]** Some email clients aggressively rewrite or strip top-of-email
  CTA links as suspicious. → **Mitigation**: link uses plain `<a href>`
  with inline color/style matching the existing unsubscribe link styling
  pattern — known to render in Gmail/Outlook/Apple Mail (same path the
  unsubscribe link already takes successfully today).
- **[Trade-off]** Existing subscription rows in the DB don't have a stored
  `web_url` — but `web_url` is *not* persisted in the subscriptions table
  (only the email and access code are). It's computed at conversion time
  from the live `config.web.public_base_url` on every app start, so a
  restart picks up the new behavior without any migration. Documented in
  CLAUDE.md under the existing "Important: Changes to `config.email` ...
  require app restart" note.

## Migration Plan

1. Merge change.
2. On next restart, subscription users with `config.web.public_base_url`
   set get the new header link in their next digest.
3. No rollback complexity — reverting the commit removes the link; users
   continue to receive emails normally.
