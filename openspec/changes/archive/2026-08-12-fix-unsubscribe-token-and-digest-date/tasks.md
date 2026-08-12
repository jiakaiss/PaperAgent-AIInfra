# Tasks: fix-unsubscribe-token-and-digest-date

## 1. Unsubscribe token freshness (digest send path)

- [x] 1.1 In `src/paper_agent/pipeline.py`, in the per-user digest send path (the `_send_to_user`/loop that calls `notifier.notify(to_send)`), recompute `unsubscribe_url = build_unsubscribe_url(user_email, config.web.public_base_url, config.subscriptions.unsubscribe.secret)` immediately before each `notifier.notify(...)` call, and assign it onto the notifier's config (`notifier.config.unsubscribe_url = unsubscribe_url`). Add a comment explaining the per-send re-sign (links `design.md` Decision 1). Import `build_unsubscribe_url` from `subscriptions`.
- [x] 1.2 Add a test (e.g. `tests/test_pipeline.py`) that sends a digest through a fake notifier and asserts the captured `unsubscribe_url` carries a token whose embedded timestamp is within a few seconds of the test's "now" (not the daemon-start timestamp) when `secret` + `public_base_url` are configured.
- [x] 1.3 Add a test asserting that when `secret` is empty / `public_base_url` is unset, the send path leaves the unsubscribe URL empty (no insecure plain link generated) and the digest still sends.

## 2. Paper published date in digest email

- [x] 2.1 In `src/paper_agent/formatter/templates.py` `_paper_row` (HTML card), render the paper's published date formatted as `YYYY-MM-DD` (`sp.paper.published.strftime("%Y-%m-%d")`) as a gray metadata line in the authors area, using the existing `color:#999; font-size:12px` inline-style idiom. Guard `if sp.paper.published:` so a missing date renders nothing.
- [x] 2.2 In the plain-text digest formatter (`format_email_text` / markdown path in the same file), add the published date (`YYYY-MM-DD`) to each paper entry, also guarded for `None`.
- [x] 2.3 Add a test that renders an HTML digest for a paper with `published` set and asserts the `YYYY-MM-DD` string appears in the card output near the authors.
- [x] 2.4 Add a test that renders an HTML (and plain-text) digest for a paper with `published=None` and asserts it does not crash and produces no date element (the rest of the card is intact).

## 3. Validation and deploy

- [x] 3.1 Run `pytest tests/ -v` and `ruff check src/ tests/`; fix any failures.
- [x] 3.2 Rebuild the Docker image and recreate the `daemon` (and `web`) container; confirm the next scheduled digest sends fresh-token unsubscribe links and dated paper cards (spot-check an email's unsubscribe link opens the confirmation page, and a paper card shows its date).
