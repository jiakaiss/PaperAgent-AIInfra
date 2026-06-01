## Requirements

### Requirement: Subscription form page accessible via navigation
The web UI SHALL provide a subscription signup page accessible at `/subscribe` route. The main page navigation SHALL include a link to this page.

#### Scenario: User navigates to subscription page
- **WHEN** user visits `/subscribe` URL
- **THEN** system displays the subscription signup form

#### Scenario: Main page includes subscription link
- **WHEN** user views the main paper list page
- **THEN** navigation area includes a visible link to the subscription page

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

### Requirement: Email validation before submission
The system SHALL validate email format on both client and server side before accepting a subscription.

#### Scenario: Invalid email format rejected
- **WHEN** user enters "not-an-email" and submits form
- **THEN** form displays validation error message and prevents submission

#### Scenario: Valid email accepted
- **WHEN** user enters "user@example.com" with valid format
- **THEN** form allows submission

### Requirement: Duplicate email detection
The system SHALL check if an email address is already subscribed and provide appropriate feedback.

#### Scenario: Email already subscribed
- **WHEN** user submits form with an email that already exists in subscriptions
- **THEN** system displays message indicating email is already subscribed and shows current subscription details

#### Scenario: New email subscription
- **WHEN** user submits form with a new email address
- **THEN** system creates new subscription and displays success message

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

### Requirement: Form submission via POST request
The subscription form SHALL submit data via POST request to `/api/subscribe` endpoint.

#### Scenario: Form submits to correct endpoint
- **WHEN** user submits the subscription form
- **THEN** browser sends POST request to `/api/subscribe` with email and sub-domain data

#### Scenario: Form uses HTMX for submission
- **WHEN** form is submitted
- **THEN** HTMX handles the submission asynchronously and updates the page with response
