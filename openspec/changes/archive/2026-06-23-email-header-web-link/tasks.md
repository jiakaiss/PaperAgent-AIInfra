## 1. Config plumbing

- [x] 1.1 Add `web_url: str = ""` field to `EmailNotifierConfig` in `src/paper_agent/config.py` (next to `unsubscribe_url`).
- [x] 1.2 Update `build_subscription_email_config()` in `src/paper_agent/subscriptions.py` to accept a `web_url` kwarg and copy it into the returned email config dict.
- [x] 1.3 Update `subscription_to_user_config()` (or whichever callsite invokes `build_subscription_email_config`) to pass `config.web.public_base_url` through.

## 2. Formatter

- [x] 2.1 Extend `format_email_html(papers, unsubscribe_url="", web_url="")` in `src/paper_agent/formatter/templates.py` to accept the new keyword arg.
- [x] 2.2 Render a `<p>` containing a "🔗 在网页中浏览全部论文" link above the date/count line when `web_url` is non-empty; omit it when empty (header block stays byte-identical to today's output).

## 3. Notifier

- [x] 3.1 In `src/paper_agent/notifier/email_notifier.py`, forward `self.config.web_url` into the `format_email_html` call in `_build_message`.

## 4. Tests

- [x] 4.1 Add `test_format_email_html_includes_web_link_when_set` in `tests/test_formatter.py` — assert the link appears with the supplied href. (Also added `..._omits_web_link_when_empty` and `..._web_link_and_unsubscribe_link_coexist`.)
- [x] 4.2 Add `test_format_email_html_omits_web_link_when_empty` in `tests/test_formatter.py` — assert no header `<a>` link when `web_url=""` (default).
- [x] 4.3 Add `test_email_notifier_forwards_web_url_into_rendered_html` + `..._omits_web_link_when_web_url_empty` + `..._notify_path_invokes_smtp` in new `tests/test_email_notifier.py` — inspect MIME payload directly, plus a separate SMTP-mock test for the network path.
- [x] 4.4 Add `test_subscription_to_user_config_copies_web_url` in `tests/test_subscriptions.py` AND end-to-end `test_load_subscriptions_copies_web_url_from_public_base_url` + `..._empty_when_public_base_url_unset` in `tests/test_subscription_storage.py` — set `config.web.public_base_url`, load subscriptions, assert each resulting `UserConfig.notify.email.web_url` matches.

## 5. Docs

- [x] 5.1 Update CLAUDE.md "Web Subscriptions" section to mention `web_url` is now copied alongside SMTP creds and the unsubscribe URL at conversion time.
- [x] 5.2 Mention the new header link in `README.md` (or wherever email features are listed) so operators know to set `web.public_base_url` to benefit.

## 6. Verification

- [x] 6.1 Run `ruff check src/ tests/` and `ruff format src/ tests/`. — All checks passed, 60 files already formatted.
- [x] 6.2 Run `pytest tests/ -v` — all green. — 442 passed.
- [ ] 6.3 Optional sanity check: `paper-agent test --notifier email --user <test_email>` against a config with `web.public_base_url` set; inspect inbox for the new link. — left for operator to run against a live SMTP config.
