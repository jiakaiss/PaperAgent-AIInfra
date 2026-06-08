## Context

The paper agent today does the following per run: a flat arXiv fetch by keyword union, Claude scoring that returns `(relevance, quality, summary_zh, sub_domain_tags)`, and a web/email render that shows the summary plus two numeric scores. The signal density is low — users skim a dozen cards trying to tell which papers are worth a deeper read, and there is no structural cue beyond the score numbers. On the fetch side, a single noisy keyword (e.g. `"serving"`) can dominate the superset and starve scoring of better candidates because the `max_results` cap is shared.

We want to push more of the "is this worth my time?" judgment into the scoring step (so it's done once and cached), and make that judgment visible in the UI through a coarse tier rather than asking users to mentally compare 7.4 vs 8.1. We also want a recency-prioritized second fetch pass so that cross-listed papers from cs.LG / cs.DC / cs.AR are not crowded out by raw keyword volume.

**Stakeholders**: subscribed users (consume the digest), the local AI Infra reader running the daemon (operator), future contributors (must continue to extend the schema cleanly).

**Constraints**:
- Single Claude tool call per batch — adding fields cannot break batching, only widen the response.
- SQLite schema must migrate in place on existing deployments without data loss.
- Web UI must stay HTMX-driven (no full SPA rebuild) and must continue to work when JS is disabled for `/health`.
- Backward compatibility for cached papers scored before this change.

## Goals / Non-Goals

**Goals:**
- Make impact tier (`breakthrough` / `solid` / `incremental`) a first-class, sortable, filterable property of every scored paper.
- Render key contributions, problem statement (zh), and methods (zh) on each web card and in the email digest.
- Make the front page reads as a curated "today's must-read" rather than an undifferentiated list.
- Improve retrieval quality by adding a recency-prioritized cross-list fetch pass and a configurable strategy for capping noisy keywords.
- Migrate the existing SQLite cache without forcing a full rescore.

**Non-Goals:**
- Personalized ranking (per-user learning from clicks) — out of scope; preferences stay declarative.
- Author/affiliation reputation scoring — explicitly excluded; tier is determined from abstract content only.
- PDF full-text scoring — abstract-only remains the contract.
- Comments, likes, or any user-generated content in the web UI.
- Multi-language summaries beyond zh.

## Decisions

### Decision 1: Tier as a categorical field on `ScoredPaper`, not a derived bucket

**Choice**: Add `impact_tier: Literal["breakthrough", "solid", "incremental"]` as a required field returned by the Claude tool call, stored as a TEXT column on `papers`.

**Alternatives considered**:
- *Derive tier from `total_score` ranges (e.g. >=8.5 → breakthrough)*: Rejected — total_score already mixes relevance + quality with arbitrary weights, and "breakthrough" is a qualitative judgment (e.g. a novel technique with modest quality writeup) that doesn't map cleanly onto a score band. Keeping it categorical lets the LLM make the call explicitly.
- *Add a fourth numeric `novelty_score`*: Rejected — adds cognitive load on the user (three numbers instead of two) without giving the UI a clean way to visually tier things.

**Rationale**: A 3-level categorical is small enough to map to visual treatments (border, badge, dimming), trivially filterable, and aligns with how readers actually triage ("worth a deep read" / "skim later" / "skip").

### Decision 2: Extend the existing tool schema, not add a second tool call

**Choice**: Widen `SCORE_TOOL`'s `input_schema` to require `key_contributions`, `problem_statement_zh`, `methods_zh`, `impact_tier` in the same per-paper object. Keep batch size at 10.

**Alternatives considered**:
- *Two-pass scoring (first numeric scores, then a second call for prose fields on the top-N)*: Rejected — would double API calls for top papers and complicate caching. The bottleneck today is token output for the summary; adding ~80–120 tokens of structured prose per paper is a ~30% increase, acceptable.
- *Separate "deep extract" tool callable on-demand from the web UI*: Rejected for v1 — adds a sync API endpoint, secrets-management surface, and unpredictable latency. Bake it into the existing batch instead.

**Rationale**: One pass keeps the pipeline shape unchanged. The marginal token cost is small relative to the input abstract cost (which dominates because it's per-paper).

### Decision 3: SQLite migration via additive columns + NULL-tolerant read

**Choice**: On `PaperDatabase.__init__`, run `ALTER TABLE papers ADD COLUMN <new>` for each missing column inside a `try/except sqlite3.OperationalError` (idempotent — SQLite errors on duplicate add). Reads coerce NULL → empty string / empty list / `"solid"` (default tier).

**Alternatives considered**:
- *Versioned migration framework (alembic-lite)*: Overkill for a single-table schema with no prior migration history. Re-evaluate once we have ≥3 schema changes in flight.
- *Drop and rescore everything*: Rejected — wastes API credits and loses delivery history association.

**Rationale**: Keeps the deployment story "just upgrade and restart". Existing cached papers render with empty contributions / `solid` tier until a rescore — visually graceful (no broken cards), and the `rescore --missing-fields` CLI gives the operator a one-shot path to backfill.

### Decision 4: Tier default — exclude `incremental` from the front page, include in `?tier=all`

**Choice**: When no `?tier=` is supplied, the server filters out `incremental` papers. The preferences panel's "minimum tier" selector (`breakthrough` / `solid` / `incremental`) controls what the client requests; the default in `localStorage` is `solid`.

**Alternatives considered**:
- *Show everything by default, let users opt out*: Rejected — defeats the "curated digest" goal. New users would see a long undifferentiated list and miss the tiering signal entirely.
- *Show breakthroughs only by default*: Rejected — on slow days the page would be near-empty, eroding trust that the system is actually fetching papers.

**Rationale**: `solid` as the floor means "papers worth your time today"; users who want completeness flip one toggle.

### Decision 5: Dual-track retrieval (two parallel paths, then merge)

**The problem we're fixing**: Today the fetcher runs one path — union all subscribed keywords, query arXiv for each, share one `max_results` budget across them. This fails in two ways:

1. **A noisy keyword eats the whole budget.** `"serving"` matches lots of web-serving / food-serving papers; it can consume most of `max_results` and squeeze out precise keywords like `"speculative_decoding"`.
2. **Keyword-only retrieval has blind spots.** A new high-quality cs.LG paper that uses different terminology (e.g. "context compression" instead of "kv cache") won't match any subscribed keyword, so it never reaches the scorer at all.

**Choice**: Run two retrieval paths in the same fetch and merge them.

- **Track 1 — keyword search (existing path, now with a per-keyword cap).** Each keyword query is capped at `max(min_per_keyword, max_results // num_keywords)`. With 20 keywords and `max_results=200`, each keyword can contribute at most 10 papers — `"serving"` can still be noisy, but it can't crowd out the other 19 keywords.
- **Track 2 — recent papers from related arXiv categories (new).** Independently of any keyword, query arXiv's listing API for papers published in the last `days_back` days under the configured categories (default `cs.LG`, `cs.DC`). This signal — "recent + in a related field" — is orthogonal to keywords, so it catches papers Track 1 would miss.
- **Merge.** Dedup by `arxiv_id`. When a paper appears in both tracks, the Track-1 record wins (so we keep the "which keyword matched this?" provenance for debugging).

The deduped union is what goes into Claude scoring. Claude then filters out irrelevant Track-2 papers via the existing `relevance_score`, so this doesn't degrade signal quality downstream — it just widens the funnel before scoring.

**Configuration**: Both tracks are gated by `fetch.quality_floor_strategy`. Setting it to `none` (the default for existing configs) preserves today's single-track behavior exactly; new installs default to `per_keyword_cap` which enables both tracks. Setting `fetch.cross_list_categories: []` keeps Track 1's cap but disables Track 2.

**Alternatives considered**:
- *Just tell users to add more keywords*: Doesn't solve the noisy-keyword problem (more keywords means smaller per-keyword shares, but the noisy one still wins on volume); and users shouldn't have to maintain a comprehensive keyword list to discover new terminology.
- *Embeddings-based retrieval (encode abstracts, k-NN against a query set)*: Out of scope — adds an embedding model dependency, vector store, and infra that doesn't fit a small SQLite deployment. Revisit if relevance drops on tier-aware scoring.
- *Score every fetched paper and let the LLM filter*: Rejected — cost scales linearly with fetch size; the per-keyword cap is the cheaper way to reduce noise BEFORE scoring.

**Rationale**: The per-keyword cap and the cross-list track address two different failure modes (one keyword dominating vs. terminology blind spots) with one shared infrastructure (the existing arXiv API client). Both are small, additive changes — neither requires a new dependency.

### Decision 6: Sort by tier first, then total_score

**Choice**: `sort_by_score` is updated to `(tier_rank, total_score)` where `tier_rank` is `0` for breakthrough, `1` for solid, `2` for incremental.

**Alternatives considered**:
- *Boost breakthrough papers by adding a constant to `total_score`*: Rejected — fragile (the constant has to be larger than any plausible score gap) and pollutes the displayed score.
- *Section the UI by tier with hard breaks*: Considered — actually a good extension for the email digest, where we DO group by tier with section headers. For the web UI, a single ordered list with visual tier cues reads better in pagination.

**Rationale**: Tier-first sort guarantees the most impactful work is on page 1 regardless of score noise.

## Risks / Trade-offs

- **[Risk] Token cost increase on first run after upgrade** → Mitigation: the increase is ~30% per paper (new prose fields), but only applies to NEW papers because cached ones are not rescored. The `rescore --missing-fields` CLI is opt-in, so operators control when (and whether) to pay the backfill cost.
- **[Risk] LLM consistently mislabels tier (everything is `solid`)** → Mitigation: prompt explicitly defines each tier with examples; we log tier distribution per run; the operator can spot-check via the web UI and adjust the prompt via `ScoringConfig.prompts`.
- **[Risk] Schema migration fails mid-run** → Mitigation: ALTER TABLE runs in `__init__` before any read/write; failures raise loudly with a clear "manual SQL needed" message. Each ALTER is independent — partial success leaves the DB usable for cached papers and only blocks new score writes that need missing columns (fail-fast at write time, not silent corruption).
- **[Risk] Cross-list fetch produces duplicates of keyword-fetched papers, inflating dedup work** → Mitigation: dedup happens by arxiv_id before scoring; cost is proportional to fetch size, not score size. Negligible at current scale (a few hundred IDs per day).
- **[Trade-off] Default `incremental` exclusion may hide papers a user wanted** → The preferences panel gives one-click "minimum tier = incremental" override, and the URL `?tier=incremental&tier=solid&tier=breakthrough` makes it shareable.
- **[Trade-off] Tier visual treatment (dimmed `incremental`) may feel patronizing** → Mitigation: dimming is an opacity reduction, not collapsing; the full card is still visible without interaction.

## Migration Plan

1. **Code deploy**: Push all code; the new schema columns are added on startup via `ALTER TABLE` (idempotent).
2. **Existing cached papers**: Render with `impact_tier="solid"` (default), empty `key_contributions`, empty prose fields. UI hides empty sections. No user-visible breakage.
3. **First scheduled run after upgrade**: Newly fetched papers get the full schema. Mixed list on the web UI is expected and acceptable for ~1 cycle.
4. **Optional backfill**: Operator runs `paper-agent rescore --missing-fields -c config.yaml` to re-score cached papers that lack the new fields. This is opt-in because it costs Claude credits.
5. **Rollback**: If a regression is found, revert the code; the extra DB columns are harmless (SQLite is permissive). Cached papers scored with the new schema continue to round-trip through the old code because the old code ignores unknown columns when constructing `ScoredPaper`. If the old code's `ScoredPaper.__init__` is strict, the rollback PR must also include a one-line `**kwargs` accept on the model — to be verified at implementation time.

## Open Questions

- Should the tier prompt include calibration examples (3 short abstracts labeled by tier)? Inclined to yes for stability across model versions, but it inflates the system prompt. **Resolution path**: ship without examples; add only if tier distribution looks degenerate after 1 week of runs.
- Should the email digest's tier section headers be localized (zh / en)? Default to zh to match `summary_zh`. Re-evaluate when/if `summary_en` becomes a separate field.
- Cross-list arXiv categories: should `cs.AR` be on by default? It's adjacent (hardware/architecture) but noisy for pure ML readers. **Resolution path**: include in `config.example.yaml` with a comment, default `cs.LG` + `cs.DC` only, let operator opt in.
