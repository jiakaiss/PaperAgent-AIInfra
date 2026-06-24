## Context

`_paper_list.html` was last touched by the citation-aware-scoring change. Its header markup is a flat `flex` row of (title, tier-badge, optional older-works-badge, optional citation-badge) using `space-between` justification — meaning the badges spread out across whatever space the title leaves. Citation badges are conditionally rendered only when `citation_count > 0`, so a fresh paper looks the same as a paper whose citation data simply hasn't been refreshed yet. Published date is on `Paper.published` but never shown in the UI (it only appears as a sort key in the database).

User feedback: badges look misaligned across cards; "0 citations" is a real, informative state; the publication date is a basic piece of triage context that's missing.

## Goals / Non-Goals

**Goals:**
- Always render the citation badge (including `0`) — uniform visual rhythm across cards, and `0` is itself a signal.
- Render the publication date (date precision, no time) on each card.
- Tighten the header so the badge cluster (tier + older + citation) is one right-aligned group with consistent inter-badge spacing, independent of title length.

**Non-Goals:**
- No backend / database / API changes.
- No new config knob — this is a pure presentation change.
- No change to digest email rendering (email layout is governed by a separate template and a separate spec — `email-digest-header` — and is out of scope here).
- No change to scoring, sorting, filtering, or the `count_papers` / `list_papers` contract.

## Decisions

### Decision: Always render the citation badge, even at zero

Today: `{% if sp.citation_count and sp.citation_count > 0 %}` hides the badge at `0`. Change to unconditional render. The badge text becomes `📈 0 citations` when the count is zero. Style stays the same; arguably we'll add a subtle visual de-emphasis at zero (lower contrast) so it doesn't compete with high-citation badges, but it's still present.

**Why** — three reasons:
1. `0` is a real data point ("we've refreshed citations and there are none yet"), not a gap.
2. Uniform card layout: every card's right-side cluster occupies the same vertical real estate, which is what the user is asking for.
3. Distinguishing "0" from "unknown" would need a separate state on `citation_count` (currently both legacy and refreshed-zero look like `0`). We accept that conflation — for legacy rows the citation refresh job will fill in the real value within one refresh cycle.

**Alternative considered**: keep "no badge at zero" but reserve fixed-width space for badges so cards still align. Rejected — the empty space looks broken and doesn't give the user any information.

### Decision: Wrap header badges in a single `.paper-card-header-badges` flex cluster

Today: badges are loose children of `.paper-card-header` (which is `justify-content: space-between`), so they spread out. New structure:

```
<div class="paper-card-header">
  <h3 class="paper-title">…</h3>
  <div class="paper-card-header-badges">
    <span class="tier-badge …">…</span>
    {% if older %}<span class="paper-kind-badge …">…</span>{% endif %}
    <span class="citation-badge">…</span>
  </div>
</div>
```

The badges div is `display: inline-flex; gap: 0.25rem; align-items: center; flex-shrink: 0;`. The outer `paper-card-header` keeps `justify-content: space-between` so the title takes the left side and the badge cluster pins right. Existing per-badge `margin-left: 4px` rules are removed (the cluster gap supersedes them) so spacing is consistent regardless of which badges are present.

**Why** — declaring the badges as a single layout unit makes them respond as a group to title length, and removes the per-badge margin patchwork that drifted out of alignment.

### Decision: Render `published` as `YYYY-MM-DD` in the authors row

Today: authors line is `<p class="paper-authors">Author1, Author2, Author3 et al.</p>`. Change to:

```
<p class="paper-authors">
  Author1, Author2, Author3 et al.
  <span class="paper-published">· 2026-03-14</span>
</p>
```

`.paper-published` is muted (same color as `.paper-authors`, slightly smaller), separator is a middle dot. Formatting uses Jinja's `strftime` filter (available via the existing FastAPI/Jinja2 setup — verify; if absent, format in the route or add a tiny custom filter).

**Why** date format — `YYYY-MM-DD` is unambiguous, locale-free, and matches the rest of the codebase's date displays (admin daily-totals table uses the same format).

**Why** authors row over a dedicated row — keeping it on the same line keeps the card compact (no new vertical space), and "who + when" is a natural grouping for paper triage.

**Alternative**: putting the date in the bottom `.paper-meta` row next to scores. Rejected — that row already feels crowded with tags + R/Q/Total, and date-near-authors is a stronger habit from reading academic papers.

### Decision: No new template helper / data plumbing

`sp.paper.published` is already a `datetime`. Jinja can format it inline via `{{ sp.paper.published.strftime('%Y-%m-%d') }}` (or `.date().isoformat()`). No need for a new computed property on `ScoredPaper`.

## Risks / Trade-offs

- **[Risk]** Always-on citation badge will read as noise on cards with truly unknown citation status (e.g. immediately after a fresh ingest, before the refresh job runs). → **Mitigation**: accepted; the refresh job runs within the cadence configured by `citations.refresh_interval_hours` (24h default). Optional follow-up: a `citations_updated_at IS NULL` check could render `📈 — citations` instead of `📈 0 citations`, but we're not doing it in this change to keep scope tight.
- **[Risk]** Long titles + 3 badges may still wrap on narrow screens. → **Mitigation**: title is `flex: 1; min-width: 0;` and badges cluster has `flex-shrink: 0`; on overflow the title wraps below or truncates per existing line-height. We're not adding mobile-specific stacking; if needed it would be a follow-up.
- **[Risk]** Snapshot / golden tests of `_paper_list.html` will diff. → **Mitigation**: update the relevant tests in this change; the proposal lists them in Impact.

## Migration Plan

Pure template + CSS change. No deploy ordering, no migration. Deploy in one push; rollback = revert the commit.

## Open Questions

None — all decisions above are firm.
