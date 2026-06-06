## ADDED Requirements

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
