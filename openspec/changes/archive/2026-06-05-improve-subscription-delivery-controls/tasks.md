## 1. Configuration and Migration

- [x] 1.1 Add config models/fields for subscription access control, unsubscribe signing secret, subscription default delivery count, scheduler interval mode, and web minimum quality filter.
- [x] 1.2 Update `config.example.yaml` and relevant docs/comments with safe defaults and operational notes for access codes, unsubscribe secret, delivery count, and increased query frequency.
- [x] 1.3 Add idempotent SQLite migration logic for subscription unsubscribe metadata while preserving existing rows and `status` semantics.

## 2. Subscription Access Control

- [x] 2.1 Update subscription page rendering to show an access-code input only when subscription access control is enabled.
- [x] 2.2 Update client-side subscription validation to require an access code when configured.
- [x] 2.3 Update `/api/subscribe` to validate submitted access code before duplicate checks or database writes, and to avoid logging submitted codes.
- [x] 2.4 Add tests for disabled gate, valid code, missing code, invalid code, and no database write on unauthorized attempts.

## 3. Unsubscribe Management

- [x] 3.1 Implement unsubscribe token signing and verification helpers using a configured secret.
- [x] 3.2 Add database helper to mark a subscription inactive and record unsubscribe metadata when available.
- [x] 3.3 Add unsubscribe confirmation page/API routes for valid token display, invalid token rejection, and confirmed unsubscribe.
- [x] 3.4 Add unsubscribe links to subscription email digests when signing is configured, without generating insecure links when it is not.
- [x] 3.5 Add tests for valid unsubscribe, invalid token, already inactive subscription, and inactive subscriptions being skipped by runtime loading.

## 4. Delivery Volume and Scheduler Frequency

- [x] 4.1 Update subscription-to-`UserConfig` conversion to apply configured subscription default `thresholds.top_n`, defaulting to 10.
- [x] 4.2 Preserve explicit config-file user `thresholds.top_n` overrides and existing per-user filtering behavior.
- [x] 4.3 Extend daemon scheduler creation to support interval-based execution while retaining existing daily cron behavior.
- [x] 4.4 Add tests for subscription default top_n, configured top_n, config-file user override, cron schedule compatibility, and invalid interval validation.

## 5. Paper Browsing Quality Filter

- [x] 5.1 Extend `PaperDatabase._build_filter_clause`, `list_papers`, and `count_papers` to accept and apply `min_quality`.
- [x] 5.2 Pass configured web minimum quality threshold through `/` and `/_paper_list` route handlers for full-page and HTMX responses.
- [x] 5.3 Update templates or empty-state text if needed so hidden low-quality papers are not counted or displayed unexpectedly.
- [x] 5.4 Add tests for quality-only filtering, combined quality/sub-domain/search filters, pagination count consistency, and disabled quality filter.

## 6. Integration and Verification

- [x] 6.1 Add or update unit tests covering subscription loading, runtime subscription creation, unsubscribe exclusion, and pipeline delivery count behavior.
- [x] 6.2 Run `ruff check src/ tests/` and fix lint issues.
- [x] 6.3 Run `pytest tests/ -v` and fix failing tests.
- [x] 6.4 Manually verify dry-run pipeline behavior for a subscription user and web subscription/unsubscribe flows where feasible.
