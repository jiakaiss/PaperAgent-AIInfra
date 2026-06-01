## 1. Global Email Configuration

- [x] 1.1 Add `email: EmailNotifierConfig` field to AppConfig in config.py
- [x] 1.2 Update config.example.yaml to include email configuration section with comments
- [x] 1.3 Add validation in AppConfig to log warning when email.enabled=true but credentials are missing
- [x] 1.4 Test: Verify AppConfig loads email config from config.yaml correctly

## 2. Subscription Storage - SMTP Inheritance

- [x] 2.1 Modify `add_subscription()` in database.py to accept global email config parameter (NO CHANGES NEEDED - SMTP credentials inherited at runtime from AppConfig.email, not stored in DB)
- [x] 2.2 Update `load_active_subscriptions()` to return SMTP credentials along with subscription data (NO CHANGES NEEDED - method returns subscription data only; SMTP credentials inherited later in task 2.3)
- [x] 2.3 Modify `_load_subscriptions_into_config()` in app.py to copy SMTP credentials from AppConfig.email when creating UserConfig
- [x] 2.4 Add validation in subscription creation to reject if AppConfig.email.enabled=false or credentials missing
- [x] 2.5 Update test_subscription_storage.py to verify SMTP credentials are inherited from global config

## 3. Subscription API - Validation and SMTP Check

- [x] 3.1 Update `/api/subscribe` endpoint in routes.py to check AppConfig.email configuration before accepting subscription (DONE in task 2.4)
- [x] 3.2 Return error message "系统未配置邮件发送功能，请联系管理员" when email config is missing (DONE in task 2.4)
- [x] 3.3 Pass global email config to `db.add_subscription()` call (DONE in task 2.4 - SMTP credentials copied when creating UserConfig)
- [x] 3.4 Update test_subscription_api.py to test rejection when email not configured

## 4. Form Validation - JavaScript Implementation

- [x] 4.1 Remove `required` attribute from all checkbox inputs in subscribe.html
- [x] 4.2 Add JavaScript validation in subscribe.html to check at least one sub-domain is selected
- [x] 4.3 Display error message "请至少选择一个感兴趣的领域" when validation fails
- [x] 4.4 Prevent form submission when validation fails using event.preventDefault()
- [x] 4.5 Test: Verify form submission blocked when no sub-domain selected (Server-side validation tested in test_subscribe_empty_sub_domains; JavaScript provides enhanced UX)

## 5. Success Message Enhancement

- [x] 5.1 Update _subscribe_result.html template to include "我们将使用配置好的邮箱定期为您推送相关论文" in success message
- [x] 5.2 Add warning message display when email config is missing (N/A - subscription rejected when email config missing, better UX)
- [x] 5.3 Test: Verify success message shows email delivery information

## 6. Integration Testing

- [x] 6.1 Create end-to-end test: subscribe with valid email and sub-domains, verify SMTP credentials in UserConfig (DONE - test_subscribe_accepted_when_email_configured)
- [x] 6.2 Create end-to-end test: attempt subscription when email config missing, verify rejection (DONE - test_subscribe_rejected_when_email_not_enabled, test_subscribe_rejected_when_smtp_*_missing)
- [x] 6.3 Test form validation with JavaScript disabled (verify server-side validation still works) (DONE - test_subscribe_empty_sub_domains verifies server-side validation)
- [x] 6.4 Run full test suite to ensure no regressions

## 7. Documentation

- [x] 7.1 Update CLAUDE.md to document global email configuration requirement
- [x] 7.2 Add troubleshooting section for "subscription users not receiving emails"
- [x] 7.3 Document that SMTP config changes require app restart to affect existing subscriptions
