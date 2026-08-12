# Spec Delta: unsubscribe-management

## MODIFIED Requirements

### Requirement: Unsubscribe link in subscription email digest
Email digests sent to web subscription users SHALL include an unsubscribe link when unsubscribe signing is configured. The token embedded in each digest's link SHALL be (re)signed at the time that digest is sent, so the link remains valid for `subscriptions.unsubscribe.token_max_age_hours` counting from the digest send time rather than from daemon startup or subscription creation time.

#### Scenario: Digest includes unsubscribe link

- **WHEN** the system sends an email digest to a subscription-created user and unsubscribe signing is configured
- **THEN** the email body contains a link that can be used to unsubscribe that recipient

#### Scenario: Token is fresh at send time

- **WHEN** a digest is sent to a subscription user and the daemon has been running longer than `subscriptions.unsubscribe.token_max_age_hours`
- **THEN** the unsubscribe link carries a token signed with the current send-time timestamp, so the link is valid when opened within `subscriptions.unsubscribe.token_max_age_hours` of the digest send

#### Scenario: Config missing for unsubscribe link

- **WHEN** unsubscribe signing is not configured
- **THEN** the system does not generate insecure plain unsubscribe links and logs a warning for operators
