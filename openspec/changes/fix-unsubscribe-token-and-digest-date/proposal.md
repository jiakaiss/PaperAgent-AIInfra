## Why

Two independent bugs in the digest email, both reported by a subscriber:

1. **Unsubscribe links are dead.** The unsubscribe token is signed once when a user's `UserConfig` is built (daemon startup or subscription time) and baked into the `EmailNotifierConfig`. It is never refreshed. With `token_max_age_hours: 720` (30 days) and the daemon running 49 days without restart, every digest sent after 2026-07-24 carried an already-expired token - clicking "取消订阅" shows the link is invalid. The bug silently recurs any time the daemon runs longer than the token lifetime; yesterday's restart only temporarily masks it.
2. **Papers have no date.** The digest email's per-paper card renders title, authors, summary, scores, and tags - but not the paper's published date. The web UI gained a published date recently (commit `8a527c5`); the email template was never updated, so subscribers can't gauge recency from the email alone.

## What Changes

- Regenerate the signed unsubscribe token **per digest send** so each email's "取消订阅" link is valid for `token_max_age_hours` counting from when *that email was sent*, independent of daemon uptime. The static `unsubscribe_url` baked into the notifier config is replaced by a freshly-signed URL at send time.
- Render each paper's `published` date in the digest email's per-paper card, formatted consistently with the web UI's published-date display.

## Capabilities

### New Capabilities
- `digest-paper-date`: The per-paper card in the HTML digest email SHALL display the paper's published date.

### Modified Capabilities
- `unsubscribe-management`: The "Unsubscribe link in subscription email digest" requirement changes so the token carried by each digest is (re)signed at send time and remains valid for the configured `token_max_age_hours` from the send time, rather than being a static token baked at daemon startup that expires under long-running daemons.

## Impact

- `src/paper_agent/pipeline.py` - digest send path: refresh the unsubscribe URL per user per send before notifying.
- `src/paper_agent/subscriptions.py` / `src/paper_agent/unsubscribe.py` - token signing is already time-stamped; the change is *when* it's called (per-send, not per-build). Possibly a helper to re-sign given an existing base URL + secret.
- `src/paper_agent/formatter/templates.py` - `_paper_row()` gains a published-date element.
- `tests/` - new tests: per-send token freshness (token timestamp ~= send time, not startup time), expired-token link now valid after a re-send, and published date present in rendered email HTML.
- No schema, DB, or config changes (existing `unsubscribe.secret`, `token_max_age_hours`, and `public_base_url` are sufficient).
