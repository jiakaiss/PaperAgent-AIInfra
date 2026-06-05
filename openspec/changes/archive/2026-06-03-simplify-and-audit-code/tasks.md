## 1. Audit current code paths

- [x] 1.1 Inspect subscription-related code in `config.py`, `web/app.py`, `web/routes.py`, `cli.py`, and tests for duplicated email/config logic
- [x] 1.2 Inspect frontend filter code in `preferences.js`, `app.js`, `index.html`, and JS tests for duplicated state mutation or URL-building logic
- [x] 1.3 Run targeted baseline tests: subscription API/storage tests, JS preference tests, and web browsing tests
- [x] 1.4 Record high-confidence bugs found during audit and decide whether to fix in this change

## 2. Simplify subscription/email helper logic

- [x] 2.1 Add a reusable helper for checking whether `AppConfig.email` is configured for subscription delivery
- [x] 2.2 Add a reusable helper for building subscription email notify config from `AppConfig.email`
- [x] 2.3 Add a reusable helper for converting a subscription row/email+domains into `UserConfig`
- [x] 2.4 Update `web/app.py` startup loading to use shared subscription helper
- [x] 2.5 Update `web/routes.py` runtime subscription creation to use shared subscription helper
- [x] 2.6 Update `cli.py` subscription loading to use shared subscription helper

## 3. Simplify frontend preference/filter logic

- [x] 3.1 Consolidate sub-domain selection mutations so chip and checkbox paths share equivalent logic
- [x] 3.2 Ensure the URL builder remains the single source for `sub_domain`, `q`, `since`, and `page` params
- [x] 3.3 Simplify empty custom-mode handling while preserving current behavior
- [x] 3.4 Remove redundant DOM sync code if helper extraction makes it unnecessary

## 4. Simplify tests and add bug coverage

- [x] 4.1 Refactor subscription API/storage tests to share config/database fixtures where practical
- [x] 4.2 Add or update tests for the shared subscription helper behavior
- [x] 4.3 Refactor JS test harness only where it reduces duplication without hiding behavior
- [x] 4.4 Add regression tests for any bugs found during audit

## 5. Verification

- [x] 5.1 Run subscription API/storage tests
- [x] 5.2 Run JS preference tests
- [x] 5.3 Run web browsing/storage tests
- [x] 5.4 Run full Python test suite
- [x] 5.5 Run linter/formatter if refactor changes formatting-sensitive code
