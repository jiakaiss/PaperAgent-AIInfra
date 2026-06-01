## MODIFIED Requirements

### Requirement: Subscription form collects email and sub-domain preferences
The subscription form SHALL include an email address input field and a multi-select interface for choosing sub-domains of interest. The form SHALL use JavaScript validation instead of HTML5 `required` attributes on checkboxes to provide clear error messages.

#### Scenario: Form displays required fields
- **WHEN** subscription page loads
- **THEN** form contains email input field, sub-domain selection interface, and submit button

#### Scenario: Sub-domain selection shows all available options
- **WHEN** user views the sub-domain selection interface
- **THEN** all 14 standard sub-domains from the taxonomy are displayed as selectable options

#### Scenario: User can select multiple sub-domains
- **WHEN** user clicks on multiple sub-domain options
- **THEN** all selected sub-domains are highlighted/checked

#### Scenario: No sub-domain selected shows clear error
- **WHEN** user attempts to submit form without selecting any sub-domain
- **THEN** JavaScript validation prevents submission and displays "请至少选择一个感兴趣的领域" error message

#### Scenario: Email input uses HTML5 validation
- **WHEN** user enters invalid email format
- **THEN** browser's native email validation prevents submission

### Requirement: Subscription confirmation feedback
The system SHALL provide clear feedback after successful or failed subscription attempts, including information about email delivery.

#### Scenario: Successful subscription
- **WHEN** form submission succeeds
- **THEN** system displays success message with subscribed email, selected sub-domains, and text "我们将使用配置好的邮箱定期为您推送相关论文"

#### Scenario: Failed subscription
- **WHEN** form submission fails due to server error
- **THEN** system displays error message and allows user to retry

#### Scenario: Email not configured
- **WHEN** form submission succeeds but global email config is missing
- **THEN** system displays success message with warning "系统未配置邮件发送功能，请联系管理员"
