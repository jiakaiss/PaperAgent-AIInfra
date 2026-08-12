## Context

Two independent digest-email bugs (see `proposal.md`). The relevant code paths:

- **Unsubscribe URL lifecycle.** `build_unsubscribe_url(email, base_url, secret)` (`subscriptions.py:68`) calls `sign_unsubscribe_token`, which stamps `int(time.time())` into the token. The result is stored on `EmailNotifierConfig.unsubscribe_url` when a `UserConfig` is built - at daemon startup (`_load_subscriptions_into_config`) and at subscription-creation time (`web/routes.py:405`). The per-tick `Pipeline.refresh_users()` deliberately does *not* rebuild existing users' notifiers (CLAUDE.md documents this as an SMTP-credential stability guarantee). So the token timestamp is frozen at startup/subscription time. With `token_max_age_hours=720` (30d) and 49 days of uptime, every digest after 2026-07-24 carried an expired token.
- **Paper card rendering.** `format_email_html` (`formatter/templates.py:281`) → `_paper_row` (`:122`) renders title, authors, summary, structured insights, score badges, citation badge, tags. `sp.paper.published` is never referenced in the email formatter (confirmed: no `published`/`date` refs in `notifier/` or the email path of `formatter/`). The web UI shows published date (`8a527c5`); the email does not.

Both `unsubscribe.secret` and `web.public_base_url` are set in the deployed config, so the link is generated (not missing) - it's the *staleness* that breaks it.

## Goals / Non-Goals

**Goals:**
- Each digest email carries an unsubscribe token valid for `token_max_age_hours` from *that email's send time*, regardless of daemon uptime.
- Each paper card in the HTML digest shows its published date.

**Non-Goals:**
- Changing `token_max_age_hours`, the HMAC scheme, or the `unsubscribe.py` signing/verify primitives (they're correct; only the *call site* is wrong).
- Persisting unsubscribe URLs or tokens in the DB (they stay ephemeral, computed at send time).
- Rebuilding the digest email's overall layout; only the per-paper card gains a date element.
- Backfilling old emails already in subscribers' inboxes (impossible; the next digest fixes forward).

## Decisions

### Decision 1: Re-sign the token in the per-user digest send loop (not in refresh_users, not in the notifier)

The pipeline's digest send path (`pipeline.py` ~`_send_to_user`, where `notifier.notify(to_send)` is called) owns the per-user loop and has access to `self.config` (`public_base_url` + `unsubscribe.secret`). Right before notifying each user, recompute `unsubscribe_url = build_unsubscribe_url(user_email, public_base_url, secret)` and assign it to the notifier's config for that send.

**Why here:**
- `refresh_users` is the wrong place: CLAUDE.md explicitly states it must not touch existing notifiers (SMTP stability). Token freshness is not an SMTP credential, but piggybacking on refresh would still produce tokens up to `ingest_interval_minutes` stale and couple token lifetime to tick cadence.
- The notifier itself is the wrong place: it doesn't currently hold `base_url`+`secret`+`email`, and pushing them into `EmailNotifierConfig` would spread secret-handling into the notifier layer and change the persisted config shape.
- The send loop is the only point that knows both "this user" and "right now".

**Alternatives considered:**
- *Notifier holds secret + base_url, signs in `_build_message`.* Rejected: spreads secret into the notifier; changes config shape; the notifier is a thin SMTP sender, not a URL builder.
- *Refresh in `refresh_users` per tick.* Rejected: violates the documented notifier-stability invariant and produces tick-stale (not send-fresh) tokens.
- *Raise `token_max_age_hours` to e.g. 365d.* Rejected: band-aid; tokens still eventually expire under long uptimes, and long-lived tokens are weaker security-wise.

**Concurrency note:** the digest send loop is single-threaded and the notifier is a per-user singleton used only in this loop, so mutating `notifier.config.unsubscribe_url` per send is safe. A clear comment marks the mutation as intentional.

### Decision 2: Render the published date as a small metadata line in `_paper_row`

Add a gray, inline-styled line showing `sp.paper.published.strftime("%Y-%m-%d")` in the authors-metadata area of `_paper_row` (next to/below authors), matching the existing `color:#999; font-size:12px` idiom. Guard for `published is None` (skip the element).

**Why a separate line, not a badge:** the score/tier/citation badges carry judgment signals; the date is neutral metadata and belongs with authors, not in the badge cluster. Inline CSS only (email-client compatibility, per existing pattern in the file).

**Also apply to the text variant** (`format_email_text` / the markdown formatter at `templates.py:50`) for consistency, so plain-text readers see `📅 2026-08-10` too. Both formatters pull from the same `sp.paper.published`.

## Risks / Trade-offs

- **[Implicit notifier-config mutation]** Mutating `notifier.config.unsubscribe_url` per send is slightly implicit. → Mitigation: a comment at the assignment + a test asserting the URL in a sent digest carries a token timestamped within a few seconds of "now" (not the daemon start time).
- **[Legacy papers with `published=None`]** A missing date must not crash rendering. → Mitigation: guard `if sp.paper.published:` before formatting; test a None-published paper renders without the date element.
- **[Token still expires if a user sits on an email >30d]** A recipient who never opens digests for >30 days still hits an expired link from an old email. → Accepted: this is the documented `token_max_age_hours` contract; the fix ensures the *typical* case (open the latest digest) always works. Forward-only.
- **[Per-send HMAC cost]** 17 users × 1 HMAC/day is negligible.

## Migration Plan

No schema, config, or DB migration. Deploy = rebuild image + recreate daemon container (same sequence as the ingest-hang fix). After deploy:
- The next scheduled digest (15:00 Asia/Shanghai) sends fresh-token unsubscribe links and dated paper cards.
- Old emails in inboxes remain expired (unfixable retroactively); affected users can unsubscribe from the next day's email or via the web UI.

Rollback: revert the commit and redeploy; behavior returns to the static-token status quo (no data impact).

## Open Questions

None blocking. Optional follow-up (out of scope): consider whether `refresh_users` should also refresh the unsubscribe URL for *newly added* mid-run subscribers (currently handled at subscription-creation time, which is already send-fresh-adjacent - leave as is).
