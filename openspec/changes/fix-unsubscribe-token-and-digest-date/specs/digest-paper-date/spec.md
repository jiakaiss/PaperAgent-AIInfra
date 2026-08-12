# Spec Delta: digest-paper-date

## ADDED Requirements

### Requirement: Digest email displays each paper's published date

The HTML and plain-text digest emails SHALL display each paper's published date, formatted as `YYYY-MM-DD`, in the paper card's metadata area (near the authors). The date reflects the paper's `published` field as fetched from arXiv, not the digest send time.

#### Scenario: Paper card shows published date

- **WHEN** a digest email is rendered for a paper that has a non-empty `published` value
- **THEN** the paper's card contains the published date formatted as `YYYY-MM-DD`, displayed in the metadata area alongside the authors

#### Scenario: Paper without published date

- **WHEN** a digest email is rendered for a paper whose `published` value is missing or `None`
- **THEN** the card renders without a date element and the rest of the card (title, authors, summary, badges) is unaffected

#### Scenario: Plain-text digest shows published date

- **WHEN** a plain-text digest email is rendered for a paper that has a non-empty `published` value
- **THEN** the paper's text entry includes the published date formatted as `YYYY-MM-DD`
