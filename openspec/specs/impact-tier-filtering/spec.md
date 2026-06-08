## ADDED Requirements

### Requirement: Tier query parameter

`GET /` and `GET /_paper_list` SHALL accept an optional repeated `?tier=<value>` query parameter where `<value>` is one of `breakthrough`, `solid`, or `incremental`. When one or more `tier` values are provided, the returned list SHALL include only papers whose `impact_tier` matches one of the provided values. Unknown tier values SHALL be ignored.

#### Scenario: Filter to breakthrough only
- **WHEN** user visits `/?tier=breakthrough`
- **THEN** only papers with `impact_tier="breakthrough"` are shown

#### Scenario: Multiple tiers use OR semantics
- **WHEN** user visits `/_paper_list?tier=breakthrough&tier=solid`
- **THEN** papers with `impact_tier` equal to `breakthrough` or `solid` are shown and `incremental` papers are excluded

#### Scenario: Unknown tier value ignored
- **WHEN** user visits `/?tier=legendary`
- **THEN** the filter is ignored and the default tier behavior applies

#### Scenario: Combined with sub-domain and search
- **WHEN** user visits `/?tier=solid&sub_domain=moe&q=routing`
- **THEN** results match all three filters with AND logic

### Requirement: Default tier exclusion

When no `tier` parameter is provided and the client has no `minTier` set in `localStorage`, `GET /` and `GET /_paper_list` SHALL exclude papers with `impact_tier="incremental"`. Papers with NULL or legacy `impact_tier` SHALL be treated as `"solid"` for filtering purposes.

#### Scenario: Default page hides incremental
- **WHEN** a fresh visitor with empty `localStorage` opens `/`
- **THEN** only `breakthrough` and `solid` papers are listed; `incremental` papers do not appear

#### Scenario: Legacy paper appears under default filter
- **WHEN** a paper scored before the upgrade (NULL `impact_tier`) exists in the database and the user opens `/`
- **THEN** the paper appears in the list (treated as `solid`)

### Requirement: Preferences panel minimum-tier selector

The preferences panel SHALL include a "minimum tier" control with options `Breakthrough`, `Solid` (default), and `Incremental`. The control SHALL persist its value in `localStorage.paper_agent_prefs.minTier`. The client JS SHALL translate the stored `minTier` into the appropriate set of `tier` query params on each `/_paper_list` fetch.

#### Scenario: Setting minimum tier to breakthrough
- **WHEN** user selects "Breakthrough" in the preferences panel
- **THEN** `localStorage.paper_agent_prefs.minTier` becomes `"breakthrough"` and subsequent fetches request `?tier=breakthrough` only

#### Scenario: Setting minimum tier to incremental
- **WHEN** user selects "Incremental" in the preferences panel
- **THEN** `localStorage.paper_agent_prefs.minTier` becomes `"incremental"` and subsequent fetches request `?tier=breakthrough&tier=solid&tier=incremental` (all three)

#### Scenario: Setting minimum tier to solid (the default)
- **WHEN** user selects "Solid" in the preferences panel
- **THEN** `localStorage.paper_agent_prefs.minTier` becomes `"solid"` and subsequent fetches request `?tier=breakthrough&tier=solid`

### Requirement: Per-user tier threshold in config

`UserThresholdsConfig` SHALL accept an optional `min_tier` field with one of the values `breakthrough`, `solid`, or `incremental` (default `solid`). The per-user pipeline phase SHALL exclude papers whose `impact_tier` is below the configured minimum before applying `top_n`.

#### Scenario: User with breakthrough-only threshold
- **WHEN** a user has `thresholds.min_tier=breakthrough` and the run produces 2 breakthrough, 5 solid, and 10 incremental papers
- **THEN** only the 2 breakthrough papers (subject to `top_n`) are sent in the user's digest

#### Scenario: Default min_tier omitted
- **WHEN** a user's config does not set `thresholds.min_tier`
- **THEN** the pipeline behaves as if `min_tier="solid"` was set and `incremental` papers are excluded for that user
