## MODIFIED Requirements

### Requirement: Subscription form collects email and sub-domain preferences
The subscription form SHALL include an email address input field and a multi-select interface for choosing sub-domains of interest. When subscription access control is enabled, the form SHALL also include an access-code input field. The form SHALL use JavaScript validation instead of HTML5 `required` attributes on checkboxes to provide clear error messages.

#### Scenario: Form displays required fields
- **WHEN** subscription page loads with subscription access control disabled
- **THEN** form contains email input field, sub-domain selection interface, and submit button

#### Scenario: Form displays access code when required
- **WHEN** subscription page loads with subscription access control enabled
- **THEN** form contains email input field, access-code input field, sub-domain selection interface, and submit button

#### Scenario: Sub-domain selection shows all available options
- **WHEN** user views the sub-domain selection interface
- **THEN** all 14 standard sub-domains from the taxonomy are displayed as selectable options

#### Scenario: User can select multiple sub-domains
- **WHEN** user clicks on multiple sub-domain options
- **THEN** all selected sub-domains are highlighted/checked

#### Scenario: No sub-domain selected shows clear error
- **WHEN** user attempts to submit form without selecting any sub-domain
- **THEN** JavaScript validation prevents submission and displays "请至少选择一个感兴趣的领域" error message

#### Scenario: Missing access code shows clear error
- **WHEN** access control is enabled and user attempts to submit form without entering an access code
- **THEN** JavaScript validation prevents submission and displays a clear authorization-code error message

#### Scenario: Email input uses HTML5 validation
- **WHEN** user enters invalid email format
- **THEN** browser's native email validation prevents submission

### Requirement: Form submission via POST request
The subscription form SHALL submit data via POST request to `/api/subscribe` endpoint. When subscription access control is enabled, the submitted data SHALL include the access code entered by the user.

#### Scenario: Form submits to correct endpoint
- **WHEN** user submits the subscription form
- **THEN** browser sends POST request to `/api/subscribe` with email and sub-domain data

#### Scenario: Access code submitted when enabled
- **WHEN** access control is enabled and user submits the subscription form
- **THEN** browser sends POST request to `/api/subscribe` with email, access-code, and sub-domain data

#### Scenario: Form uses HTMX for submission
- **WHEN** form is submitted
- **THEN** HTMX handles the submission asynchronously and updates the page with response

## ADDED Requirements

### Requirement: Subscription access denial message
The subscription form SHALL display a clear authorization failure message when `/api/subscribe` rejects a request due to missing or invalid access code.

#### Scenario: Invalid access code response
- **WHEN** user submits the subscription form with an invalid access code
- **THEN** the form displays an error message indicating that subscription requires valid authorization
