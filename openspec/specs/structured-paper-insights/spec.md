## ADDED Requirements

### Requirement: Extended scoring schema fields

The `ScoredPaper` model SHALL include the following additional fields populated by the LLM scorer:
- `key_contributions: list[str]` — 1 to 3 short bullet phrases capturing the paper's distinguishing contributions (each bullet ≤ 120 characters)
- `problem_statement_zh: str` — 1 to 2 sentences in Chinese describing the problem the paper addresses
- `methods_zh: str` — 1 to 2 sentences in Chinese describing the methods or approach used
- `impact_tier: Literal["breakthrough", "solid", "incremental"]` — categorical impact tier

The `SCORE_TOOL` JSON schema SHALL list these fields as required outputs alongside the existing `relevance_score`, `quality_score`, `summary_zh`, and `sub_domain_tags`.

#### Scenario: Scorer returns all fields for a typical paper
- **WHEN** the Claude scorer processes a paper about KV-cache compression
- **THEN** the returned `ScoredPaper` has `key_contributions` length between 1 and 3, non-empty `problem_statement_zh`, non-empty `methods_zh`, and `impact_tier` equal to one of `"breakthrough"`, `"solid"`, or `"incremental"`

#### Scenario: Scorer enforces bullet count bounds
- **WHEN** the LLM response contains 5 contribution bullets for a single paper
- **THEN** the scorer truncates `key_contributions` to the first 3 bullets and logs a warning

#### Scenario: Invalid impact_tier value rejected
- **WHEN** the LLM response contains `impact_tier="amazing"` for a paper
- **THEN** the paper falls back to `impact_tier="solid"` and a warning is logged

### Requirement: Tier-aware sorting

The pipeline SHALL sort scored papers primarily by `impact_tier` rank (`breakthrough` < `solid` < `incremental`) and secondarily by `total_score` descending. The `sort_by_score(papers, weights=...)` helper SHALL accept the new tier rank as the primary key.

#### Scenario: Breakthrough outranks higher-scoring solid paper
- **WHEN** sorting two papers where paper A has `impact_tier="breakthrough"` and `total_score=7.2`, and paper B has `impact_tier="solid"` and `total_score=9.0`
- **THEN** paper A appears before paper B

#### Scenario: Same tier sorts by total_score
- **WHEN** sorting two `solid` papers with `total_score=8.5` and `total_score=7.1`
- **THEN** the 8.5 paper appears before the 7.1 paper

### Requirement: Backward-compatible storage migration

`PaperDatabase` SHALL add `key_contributions` (TEXT, JSON-encoded), `problem_statement_zh` (TEXT), `methods_zh` (TEXT), and `impact_tier` (TEXT) columns to the `papers` table on startup via idempotent `ALTER TABLE` statements. Reads of legacy rows where these columns are NULL SHALL return `key_contributions=[]`, `problem_statement_zh=""`, `methods_zh=""`, and `impact_tier="solid"`.

#### Scenario: Upgrade with existing data preserves rows
- **WHEN** the daemon starts against a database with 500 papers scored under the old schema
- **THEN** the 4 new columns are added, no existing row is deleted or rewritten, and a `list_papers()` call returns the 500 papers with default values for the new fields

#### Scenario: Repeat startup is idempotent
- **WHEN** the daemon starts a second time after the migration ran successfully
- **THEN** the `ALTER TABLE` calls produce no error and no schema change

### Requirement: Backfill CLI command

The CLI SHALL expose `paper-agent rescore --missing-fields -c <config>` that re-scores cached papers whose `impact_tier` is NULL or whose `key_contributions` JSON column is NULL. The command SHALL process papers in batches matching `ScoringConfig.batch_size` and SHALL update existing rows in place (not create new rows).

#### Scenario: Backfill processes only missing rows
- **WHEN** the database has 500 papers, 300 scored with the new schema and 200 with NULL `impact_tier`, and the operator runs `paper-agent rescore --missing-fields`
- **THEN** only the 200 legacy papers are sent to the scorer and their `papers` rows are updated in place; the 300 already-scored papers are skipped

#### Scenario: Backfill is resumable
- **WHEN** the backfill is interrupted after processing 100 of 200 papers
- **THEN** rerunning the command processes only the remaining 100 papers
