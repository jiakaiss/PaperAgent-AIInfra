## 1. Database schema extension

- [x] 1.1 Add `subscriptions` table schema to `storage/database.py` with columns: id, email, sub_domains (JSON), created_at, status
- [x] 1.2 Implement `add_subscription(email, sub_domains)` method in PaperDatabase
- [x] 1.3 Implement `get_subscription(email)` and `is_email_subscribed(email)` query methods
- [x] 1.4 Implement `load_active_subscriptions()` method to fetch all active subscriptions
- [x] 1.5 Add unit tests for subscription storage methods

## 2. Subscription API endpoint

- [x] 2.1 Create Pydantic model `SubscriptionRequest` for form validation (email format, sub-domains list)
- [x] 2.2 Add POST `/api/subscribe` route in `web/routes.py`
- [x] 2.3 Implement duplicate email detection and appropriate response
- [x] 2.4 Implement runtime UserConfig creation and addition to AppConfig.users
- [x] 2.5 Return success/error response with subscription details
- [x] 2.6 Add unit tests for subscription API endpoint

## 3. Subscription form page

- [x] 3.1 Create `subscribe.html` template with form layout
- [x] 3.2 Add email input field with HTML5 validation
- [x] 3.3 Add sub-domain multi-select interface (checkboxes or chips)
- [x] 3.4 Add submit button with HTMX POST to `/api/subscribe`
- [x] 3.5 Add success/error message display area
- [x] 3.6 Add GET `/subscribe` route to serve the form page
- [x] 3.7 Add navigation link to subscription page from main page

## 4. UI redesign - CSS foundation

- [x] 4.1 Define CSS variables for colors (primary, secondary, background, text, accent)
- [x] 4.2 Define CSS variables for spacing scale (xs, sm, md, lg, xl)
- [x] 4.3 Define CSS variables for typography (font-family, font-sizes, font-weights)
- [x] 4.4 Update base styles to use CSS variables
- [x] 4.5 Add responsive breakpoints (mobile <768px, tablet, desktop ≥1024px)

## 5. UI redesign - Component styles

- [x] 5.1 Style navigation header with links and current page indicator
- [x] 5.2 Style paper cards with hover effects and clear hierarchy
- [x] 5.3 Style sub-domain chips with active/inactive states
- [x] 5.4 Style buttons with hover, focus, and active states
- [x] 5.5 Style form inputs with focus indicators
- [x] 5.6 Style subscription form with modern layout
- [x] 5.7 Add responsive layout for mobile devices

## 6. Integration and testing

- [x] 6.1 Update `create_app()` to load subscriptions from database on startup
- [x] 6.2 Update Pipeline initialization to include subscription-based users
- [x] 6.3 Test end-to-end subscription flow (form submit → database → pipeline)
- [x] 6.4 Test duplicate email handling
- [x] 6.5 Test invalid email format rejection
- [x] 6.6 Visual testing of UI redesign across different viewport sizes
- [x] 6.7 Run full test suite to ensure no regressions
