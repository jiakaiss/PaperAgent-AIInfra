# unsubscribe-management Specification

## Purpose
TBD - created by archiving change improve-subscription-delivery-controls. Update Purpose after archive.
## Requirements
### Requirement: Self-service unsubscribe endpoint
The system SHALL provide a self-service unsubscribe endpoint that lets a subscription recipient cancel future paper digest delivery after proving authorization with a valid unsubscribe token.

#### Scenario: Valid unsubscribe link
- **WHEN** a recipient opens an unsubscribe link containing their email and a valid token
- **THEN** the system displays an unsubscribe confirmation page for that email

#### Scenario: Invalid unsubscribe token
- **WHEN** a visitor opens an unsubscribe link with a missing, malformed, expired, or invalid token
- **THEN** the system rejects the request and does not change subscription status

#### Scenario: Confirm unsubscribe
- **WHEN** a recipient confirms unsubscribe with a valid email and token
- **THEN** the system marks the subscription inactive and displays a success message

### Requirement: Unsubscribed recipients excluded from delivery
The system SHALL exclude inactive or unsubscribed subscriptions from runtime user loading and paper delivery.

#### Scenario: Inactive subscription exists
- **WHEN** `load_subscriptions_into_config` loads subscriptions from storage
- **THEN** rows with `status` other than `active` are not converted into `UserConfig`

#### Scenario: Previously sent user unsubscribes
- **WHEN** a subscription is marked inactive after previous deliveries
- **THEN** subsequent pipeline runs do not send papers to that email from the subscription row

### Requirement: Unsubscribe link in subscription email digest
Email digests sent to web subscription users SHALL include an unsubscribe link when unsubscribe signing is configured.

#### Scenario: Digest includes unsubscribe link
- **WHEN** the system sends an email digest to a subscription-created user and unsubscribe signing is configured
- **THEN** the email body contains a link that can be used to unsubscribe that recipient

#### Scenario: Config missing for unsubscribe link
- **WHEN** unsubscribe signing is not configured
- **THEN** the system does not generate insecure plain unsubscribe links and logs a warning for operators

### Requirement: Unsubscribe persistence
The system SHALL persist unsubscribe state in the subscriptions table without deleting the subscription row.

#### Scenario: Subscription deactivated
- **WHEN** a subscription is unsubscribed
- **THEN** the database row remains present with `status="inactive"` and unsubscribe metadata recorded when supported by schema

#### Scenario: Already inactive subscription
- **WHEN** a recipient confirms unsubscribe for an already inactive subscription
- **THEN** the system treats the operation as successful and keeps the subscription inactive

