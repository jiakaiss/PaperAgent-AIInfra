## Purpose

Define the web subscription signup form experience, validation behavior, and submission feedback.
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

### Requirement: Subscription access denial message
The subscription form SHALL display a clear authorization failure message when `/api/subscribe` rejects a request due to missing or invalid access code.

#### Scenario: Invalid access code response
- **WHEN** user submits the subscription form with an invalid access code
- **THEN** the form displays an error message indicating that subscription requires valid authorization

### Requirement: Subscription form displays delivery schedule notice
The subscription signup page SHALL display a clearly visible notice informing users that paper digests are delivered once per day at 09:00 Asia/Shanghai (Beijing time). The notice SHALL appear above the form, after the page introduction, so users see it before filling in fields.

#### Scenario: User views subscription page
- **WHEN** user visits `/subscribe`
- **THEN** the page contains text indicating that digests are sent every day at 09:00 Beijing time

#### Scenario: Notice positioned before form
- **WHEN** the subscription page renders
- **THEN** the delivery schedule notice appears between the page introduction text and the first form field, not inside any `<form>` element

### Requirement: Subscription form displays guidance for requesting new sub-domains
The subscription signup page SHALL display a notice informing users that the listed sub-domains are the currently supported set, and that users with needs outside this list should contact the administrator to request additions. The notice SHALL appear together with the delivery schedule notice in the rules area.

#### Scenario: User sees how to request new sub-domains
- **WHEN** user visits `/subscribe`
- **THEN** the page contains text instructing users to contact the administrator if they need a sub-domain that is not in the current list

#### Scenario: Notice does not expose administrator contact details
- **WHEN** the subscription page renders
- **THEN** the notice references "administrator" without embedding any email address, phone number, or chat link as plain text on the page

### Requirement: Sub-domain checkbox grid maintains consistent chip layout
The subscription form's sub-domain selection grid SHALL render every checkbox card with the checkbox icon on the left and the label text on the same line, for all 14 standard sub-domains. The layout SHALL NOT wrap a card's label text onto a second line below its checkbox in any supported viewport width.

#### Scenario: Longest sub-domain labels stay on one line
- **WHEN** the subscription page renders on a desktop viewport (≥1024px)
- **THEN** `distributed_training`, `speculative_decoding`, and `memory_optimization` each display with the checkbox and full label text horizontally aligned in a single row inside their card

#### Scenario: All cards have visually identical structure
- **WHEN** a user views the 14 sub-domain cards
- **THEN** every card has the same row layout (checkbox left, label right, single line); none has its label stacked below the checkbox

### Requirement: Subscription page provides comfortable form width
The subscription page container SHALL be wide enough to display the sub-domain grid without crowding, while remaining narrower than the main paper list page so the form does not span the full viewport on large displays.

#### Scenario: Container width supports a 3-column sub-domain grid
- **WHEN** the subscription page renders on a viewport ≥1024px
- **THEN** the subscribe container is wide enough that the sub-domain grid displays 3 columns with each column at least 220px wide

#### Scenario: Container does not overflow narrow viewports
- **WHEN** the subscription page renders on a viewport ≤768px
- **THEN** the subscribe container fits within the viewport width and the sub-domain grid collapses to a single column

