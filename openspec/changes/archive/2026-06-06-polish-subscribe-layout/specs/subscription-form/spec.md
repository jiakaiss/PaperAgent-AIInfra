## ADDED Requirements

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
