## Context

The scorer today ranks papers from abstract text alone (`relevance_score` + `quality_score`, tier as primary key). This biases toward strong-abstract papers and makes the system blind to (a) older landmark papers that are still reshaping practice and (b) recent papers whose impact only shows up as citations accrue. arXiv itself exposes no citation data, so the signal must come from an external bibliographic source.

Constraints from the existing architecture:
- **Single shared score cache** (`papers` table, arXiv-ID keyed) shared across all users; per-user state lives only in `sent_papers`.
- **Two-phase pipeline**: shared fetch/score/cache once, then per-user filter/sort/notify. Adding a fetch track must not break this shape.
- **Idempotent `ALTER TABLE ADD COLUMN` migrations** guarded by `PRAGMA table_info` — the established migration pattern; new columns must follow it.
- **Daemon already schedules** an ingest job (`ingest_interval_minutes`) and a daily digest; a citation-refresh job slots into the same `apscheduler`.
- **`total_score` is a documented property** with a stable meaning and is rendered in the UI — it must NOT be silently redefined to absorb citations.
- **Operator-opt-in backward compatibility**: prior changes (structured-insights, dual-track) all default to off and preserve old behavior; this change must too.

The user explicitly chose Semantic Scholar as the citation source and wants both (1) periodic re-check of cached papers' citations and (2) active reverse-discovery of high-citation older papers, with a dedicated "重要老作" digest section.

## Goals / Non-Goals

**Goals:**
- Fetch citation counts from Semantic Scholar via a swappable `CitationProvider` protocol.
- Store citation data in the `papers` table; refresh periodically without triggering Claude rescoring.
- Integrate citation as a ranking signal that doesn't crush brand-new (0-citation) papers.
- Discover and ingest older highly-cited papers as a separate `paper_kind="older"` track.
- Deliver up to N older works per digest in a distinct section, additive to `top_n`.
- Surface citation info in the web UI and admin dashboard.
- Default everything off; zero behavior change for existing deployments until the operator opts in.

**Non-Goals:**
- No LLM re-scoring on citation refresh (citation is a sort signal, not a score input — keeps Claude cost flat).
- No replacement of arXiv as the primary fresh-paper fetch source.
- No multi-provider citation aggregation (e.g., merging S2 + OpenAlex counts); the protocol is swappable but only S2 ships now.
- No per-user citation thresholds (the existing global-threshold model is preserved).
- No author/h-index signals, only paper-level citation counts.
- No rewrite of `total_score`'s meaning or the tier-first sort invariant.

## Decisions

### D1: Citation influences scores via Claude re-scoring, not via the `total_score` formula

The `total_score` formula stays `relevance*w_r + quality*w_q` — citation count is NEVER a term in the formula. Instead, when a paper's citations grow significantly, the pipeline re-runs the Claude scorer with the current citation counts supplied as input context; Claude then re-emits `relevance_score`, `quality_score`, `impact_tier`, etc., and `total_score` is recomputed from the refreshed `relevance`/`quality`. So citation affects `total_score` and `impact_tier` *indirectly*, by giving the LLM better evidence — never by editing the formula. The `citation_component` (log-normalized) remains only as a same-tier tiebreaker in `sort_by_score` for papers that tie on `(tier, total_score)` even after re-scoring.

**Why not fold citation directly into the `total_score` formula?** `total_score` is rendered in the UI with a documented 0–10 meaning ("R: 8.5 / Q: 7.0 / Total: 7.9"). A formula term would silently change displayed numbers and break the `configurable-scoring-weights` contract. Re-scoring keeps the formula stable while still letting rising citations lift both `total_score` (via re-evaluated relevance/quality) and `impact_tier` (via re-evaluated tier) — which is exactly the "评分动态化" the user asked for.

**Why re-score via Claude rather than a hardcoded rule?** The user explicitly chose Claude re-scoring over rule-based tier promotion. Rationale: the LLM can weigh citation evidence against the paper's actual content (a 500-citation survey vs a 500-citation seminal method differ), whereas a rule (`citation>N → breakthrough`) is blind. The cost is bounded by D7's guards.

**Why tier-first still?** A `breakthrough` paper with 0 citations (just published) must still outrank a `solid` paper with 5000 citations *until* the solid paper is re-scored and Claude promotes it. Re-scoring is the mechanism by which a rising-citation paper crosses tier boundaries; until it runs, the LLM's last judgment stands.

### D2: Log normalization that doesn't zero-penalize new papers

`citation_component = 10 * log10(1 + citation_count) / log10(1 + C)` where `C` is `citations.normalization_ceiling` (default `1000`, configurable). For `citation_count=0` → `0`; for `citation_count=C` → `10`; monotonic. Crucially, **two papers with the same citation count get the same component**, so a brand-new 0-citation paper is not pushed below another 0-citation peer — the penalty is only relative to papers that *do* have citations, applied through the sort key.

**Why log not linear?** A 5000-citation paper would saturate any linear 0–10 scale and dominate; log compresses the tail so a 50-citation paper (clearly notable) already scores meaningfully without 5000 swallowing everything.

**Why the ceiling is configurable?** Different domains have different citation distributions — a 1000-citation paper is exceptional in some sub-fields and routine in others. Operators who want citations to matter more for tied papers lower the ceiling (e.g., `200`, so 200-citation papers already saturate); those who want a gentler tiebreaker raise it.

**Alt considered:** percentile-rank within the candidate set. Rejected — non-deterministic per-run, harder to reason about, and the gentle tiebreaker role doesn't need that precision.

### D3: Separate `paper_kind` column instead of a second table

Older-works papers live in the same `papers` table with `paper_kind="older"`. They share the same score cache, the same `list_papers` query path, and the same web rendering — only a `WHERE paper_kind = ?` filter differs.

**Why not a second table?** The web UI, admin stats, and dedup logic all assume one paper cache keyed by arXiv ID. A second table would duplicate the schema and the `list_papers`/`count_papers` plumbing, and would complicate the `?older=` filter. One table + a discriminator column is the lighter change and matches how `impact_tier` already discriminates rows.

**Trade-off:** An older paper that later also surfaces in a fresh fetch (re-published, e.g. v2) keeps `paper_kind="older"` — acceptable, since the row is deduped by arXiv ID and we don't want to flip it back and forth.

### D4: Older-works discovery reuses Semantic Scholar search, not arXiv

The older-works track queries `GET /graph/v1/paper/search` (Semantic Scholar) filtered by sub-domain keyword + `citationCount >= min_citations_for_older_works` + publication year older than `current_year - citations.older_works_min_age_years` (default `2`), rather than arXiv's API. arXiv has no citation filter and no way to rank by impact, so it cannot produce "highly-cited older works" by itself. The age cutoff is its own knob (not derived from `fetch.days_back`) because "what counts as old" is an editorial choice independent of "how far back we sweep arXiv for fresh papers".

**Why skip non-arXiv papers?** The cache is arXiv-ID keyed (`papers.arxiv_id` PK). A Semantic Scholar paper without an arXiv ID can't be stored without widening the schema to a separate ID namespace. The user's subscription/digest model is arXiv-centric (abs URLs, the fetcher). Skipping non-arXiv results keeps the cache coherent. This is a known coverage gap (some seminal CS papers are S2-only); accepted for v1, noted as an open question.

**Per-ingest cap.** `citations.older_works_max_new_per_ingest` (default `20`) caps how many newly-discovered older papers go to the Claude scorer per ingest cycle. Without this cap, first-enable could trigger hundreds of one-time score calls for a 15-sub-domain taxonomy. Overflow isn't lost — uncached candidates are re-discovered next tick and naturally re-considered.

**Dedup:** Discovered older papers are deduped against the existing cache (skip if `arxiv_id` present, optionally flip `paper_kind` to `"older"`). They are then scored by Claude through the *existing* `score_papers` path — no new scorer code, just a different feeder.

### D5: Citation refresh is a daemon job + CLI, never inline in the digest path

The daily digest path must stay fast (it already runs per-user). Citation refresh is a separate scheduled job (cadence `citations.refresh_interval_hours`) that writes `citation_count`/`citations_updated_at` in place, then (per D7) triggers dynamic re-scoring for eligible papers. The digest reads whatever's currently cached. A manual `paper-agent refresh-citations` CLI covers backfills and operator-triggered refreshes.

**Why not refresh-then-send in the digest?** Per-user digest would each block on S2 API calls plus Claude re-scoring; with N users that's N× the latency and rate-limit pressure. Decoupling refresh+rescore from delivery matches the existing ingest-vs-digest split and keeps the digest path read-only over the cache.

### D7: Dynamic re-scoring is threshold-gated and rate-limited

Re-scoring is the expensive step (Claude API per paper), so it must not run on every refresh for every paper. The refresh job, after updating citation counts, selects papers eligible for re-scoring:

- **Growth threshold** — re-score only if `citation_count_now - citation_count_at_last_score >= rescore_min_delta` (default `50`) OR `(citation_count_now - citation_count_at_last_score) / max(1, citation_count_at_last_score) >= rescore_min_ratio` (default `0.2`). Papers whose citations haven't meaningfully moved are skipped.
- **Per-run cap** — at most `rescore_max_per_run` (default `20`) re-scores per refresh tick, picked by largest absolute citation growth first (biggest movers prioritized). Overflow waits for the next tick.
- **Per-paper min interval** — a paper re-scored within `rescore_min_interval_days` (default `7`) is skipped even if its growth threshold is met, to prevent hot papers from being re-scored every tick. Tracked via a new `scored_at`-style timestamp comparison (reuse the existing `scored_at` column).

Re-scoring reuses the existing `score_papers()` path with one change: the user-message template renders the paper's current `citation_count` and `influential_citation_count` as context (e.g. "该论文当前被引 320 次，其中 influential 12 次，请结合引用证据重新评估"). The `SCORE_TOOL` *output* schema is unchanged — only the input context gains citation info.

**Why these defaults?** 50 absolute OR 20% relative filters out noise (S2 counts drift by single digits); 20/run caps a daily refresh at ~20 Claude calls (cheap); 7-day interval stops a viral paper from being re-scored 30×/month. All four knobs are configurable.

**Why prioritize by absolute growth?** A paper going 10→60 (+50) is a bigger calibration signal than one going 1000→1010 (+10, 1%). Largest-delta-first spends the per-run budget where the LLM's original judgment is most likely stale.

**Trade-off:** A paper just above threshold but ranked 21st in growth waits a tick (up to `refresh_interval_hours` later). Acceptable — re-scoring is best-effort calibration, not real-time.

### D8: Older-works discovery — sort by citation, multi-keyword, source-tagged, single-trip

The first deploy of the older-works track surfaced four real-world failures the v1 spec missed; the discovery path was upgraded to address them. Recording the upgraded design here so future work doesn't regress:

- **Sort by `citationCount:desc`, not S2 default relevance.** S2's relevance ranking interleaves a lot of low-citation recent work into each page; combined with the `min_citations` floor, that produced 0–2 candidates per sub-domain. Citation-count sort makes the first 20 results the most-cited classics in the year window.
- **Multiple keyword variants per sub-domain.** A single search on `"speculative decoding"` misses papers titled "draft model" or "assisted generation". The fetcher now queries up to `older_works_keywords_per_sub_domain` (default 3) variants per sub-domain, drawn from `models.SUB_DOMAINS[sd]`, deduped by `arxiv_id` across variants.
- **Carry citations forward, don't re-query.** v1 returned only `Paper` objects from search and re-queried S2 batch in the pipeline to learn the citation count. Under rate-limit, the second call silently returned empty, producing zero-citation `paper_kind="older"` zombies in the cache. The fetcher now returns `(papers, source_map, citation_map)` and the pipeline feeds `citation_map` straight to the scorer's `citation_context`.
- **Force-tag the originating sub-domain.** A paper found via the "quantization" search but tagged "compiler" by the LLM would be invisible to quantization subscribers. After scoring, the originating sub-domain (recorded in `source_map` at first sighting) is merged into `sub_domain_tags`.
- **Already-cached classics get promoted, not skipped.** Long-running deployments accumulate cached fresh papers that, over time, became classics. v1 silently skipped them on rediscovery. v2 SQL-flips `paper_kind` to `"older"` when the cached `citation_count >= older_works_promote_min_citations` — preserving every other column (no rescore, no Claude call, idempotent on already-`"older"` rows).
- **Same auto-promotion happens during dynamic rescore.** Even without S2 search rediscovering the paper, if `rescore_dynamic` re-scores a `paper_kind="fresh"` row whose citations crossed `older_works_promote_min_citations` AND whose `published` date is at least `older_works_min_age_years` ago, the same write flips it to `"older"`. The age guard prevents recent viral hits from being misclassified as classics.

**Why `older_works_promote_min_citations` (default 500) is HIGHER than `min_citations_for_older_works` (default 100):** The discovery floor is a "what's worth considering" gate; the promotion threshold is a "this is definitely a classic" claim. Discovery + Claude scoring already filter out borderline cases via tier judgment, so a low discovery floor is fine. Promotion bypasses Claude entirely (we just flip a column) — so the bar must be high enough that we trust the citation count alone.

### D6: Default-off with bit-for-bit backward compatibility

`citations.enabled=false` (default), `citation_weight=0.0` (default), `older_works_per_digest=0` (default). With all defaults, the pipeline fetches from arXiv, scores with Claude, sorts tier-then-total_score, and delivers fresh-only digests — identical to today. Operators opt in by setting `citations.enabled: true` and tuning `citation_weight` / `older_works_per_digest`.

**Why this matters:** The repo's recent history shows a strong "default-off, opt-in" discipline (dual-track fetch, structured-insights). Matching it keeps upgrades safe for the existing deployment and lets each capability be evaluated independently.

## Risks / Trade-offs

- **[Semantic Scholar rate limits / downtime]** S2 allows ~100 req/min unauthenticated, 1 req/s recommended; with an API key, higher. → Mitigation: configurable `requests_per_second` (default `1.0`) and `batch_size` (default `50`, using S2 batch endpoint), plus per-request `request_timeout` (default `15s`). Refresh failures are logged and skipped (stale data remains); a `requests` exception does not crash the daemon job.
- **[Citation data lags reality]** S2's citation counts lag days–weeks behind actual citing activity, and some papers are never indexed. → Mitigation: accepted; the signal is a tiebreaker + re-score trigger, not a hard filter. Documented in admin panel ("已采集" coverage, not "全部论文").
- **[Re-scoring API cost]** Dynamic re-scoring spends Claude tokens per re-scored paper, unlike the original design. → Mitigation: D7's growth threshold + per-run cap (default 20) + per-paper 7-day interval bound it. A deployment with `refresh_interval_hours=24` and defaults spends ≤20 Claude calls/day on re-scoring. Operators who want zero cost set the thresholds high or disable via `rescore_max_per_run=0`.
- **[Re-scoring churns displayed scores]** A paper's `total_score`/`impact_tier` can change after re-scoring, which may surprise users who bookmarked a score. → Mitigation: accepted as intended behavior (the whole point of "评分动态化"); the web card could optionally show a small "评分已更新" hint — deferred, noted as open question.
- **[Auto-promotion mis-classifies a not-yet-classic]** A 2-year-old paper that crossed 500 citations might still be a fad rather than a true classic. → Mitigation: D8's age guard (must be ≥ `older_works_min_age_years`) prevents the most obvious failure mode (recent viral hits). The 500-citation threshold is itself conservative — operators who want stricter behavior can raise it. Promoted papers can also be demoted by an operator with one SQL UPDATE if needed; promotion is not destructive.
- **[Multi-keyword search × multi-sub-domain × N variants explodes HTTP volume]** With 15 sub-domains × 3 variants × 1 req/s = 45+ seconds per ingest just on S2 search. → Mitigation: `older_works_keywords_per_sub_domain` is configurable; the discovery track only runs when `older_works_per_digest > 0`; S2 search is GET (cheap) and the `requests_per_second` rate limit guards against bursts. If volume becomes an issue, operators can lower the variant count or the digest cadence.
- **[Non-arXiv seminal papers invisible]** Papers without an arXiv ID are skipped by the older-works track (D4). → Mitigation: documented as an open question; future work could add a non-arXiv ID namespace if coverage gap matters in practice.
- **[Citation component ordering surprise]** Operators may expect citations to dominate. With the gentle tiebreaker design (D1), a 5000-citation `solid` paper still ranks below a 0-citation `breakthrough`. → Mitigation: documented in CLAUDE.md and design; `citation_weight` is the visible lever but the tier invariant is intentional.
- **[DB migration on large caches]** Adding 4 columns to a large `papers` table is cheap (SQLite `ALTER TABLE ADD COLUMN` with defaults is O(1) metadata, no row rewrite). → No mitigation needed; this is the same pattern as the structured-insights migration.
- **[Older-works inflates digest volume]** Additive older works increase email length. → Mitigation: capped by `older_works_per_digest` (default `0` = off); operator controls it.
- **[S2 API key in config]** `citations.api_key` is a secret. → Mitigation: `${ENV_VAR}` interpolation (existing pattern); admin dashboard must not render it (covered by the existing "admin never exposes secrets" invariant — add `citations.api_key` to the sentinel list in `test_admin.py`).

## Migration Plan

1. **Code ships disabled.** All new config fields default off. Existing deployments see no behavior change on upgrade.
2. **DB migration auto-runs** on next daemon/web start (idempotent `ALTER TABLE`). Legacy rows read back with safe defaults (`citation_count=0`, `paper_kind="fresh"`, `citations_updated_at=NULL`).
3. **Operator opts in** by adding `citations: { enabled: true, ... }` to `config.yaml`, optionally `scoring.citation_weight: 0.2` and `thresholds.older_works_per_digest: 2`, then restarting.
4. **First refresh** runs on the next scheduled citation job (or via `paper-agent refresh-citations --all`). No Claude rescore occurs; only citation columns populate.
5. **Older-works track** runs on the next ingest once `older_works_per_digest > 0`; discovered papers are scored (Claude cost, one-time per paper) and cached.
6. **Rollback:** set `citations.enabled: false` (or `older_works_per_digest: 0` / `citation_weight: 0.0`) and restart. The new columns remain but are ignored. To fully remove citation data, an operator can `UPDATE papers SET citation_count=0, citations_updated_at=NULL` — no schema rollback is needed or provided (the columns are harmless when disabled).

## Open Questions

- **Re-scoring prompt sharpness**: does telling Claude the citation count actually shift its tier/score, or does it anchor on its first judgment? Needs empirical tuning of the user-message phrasing during implementation. If Claude ignores citation context, fall back to a rule-based tier-promotion backstop (out of scope for this change).
- **"评分已更新" UI hint**: should the web card show that a paper was re-scored (and when)? Deferred — add only if the score-churn surprise is a real complaint.
- **Non-arXiv seminal papers**: skip for v1 (D4). If the coverage gap is a real complaint, a future change could add a `semantic_scholar_id` column and a parallel fetch path. Out of scope here.
- **Older-works scoring cost**: each newly discovered older paper triggers one Claude score (unlike citation refresh, which is free). For a large sub-domain taxonomy this could be a meaningful one-time cost on first enable. Should the older-works track be rate-limited per ingest (e.g. max N new older papers per cycle)? Proposed: yes, cap at `citations.batch_size` new older scores per ingest; flagged as a task detail to confirm during implementation.
