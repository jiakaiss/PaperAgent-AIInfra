"""Periodic citation refresh + dynamic re-scoring (citation-aware-scoring).

Two responsibilities live here, both intentionally decoupled from the
per-user digest path so they can run as their own daemon job:

1. ``refresh_citations()`` — fetch fresh citation counts from the configured
   :class:`CitationProvider` for stale rows in the ``papers`` cache. Updates
   ``citation_count`` / ``influential_citation_count`` / ``citations_updated_at``
   in place. Free (no Claude tokens).

2. ``rescore_dynamic()`` — for papers whose citation count grew significantly
   since the last Claude score, re-run the scorer with the current citation
   counts as input context. Updates the scored fields + ``scored_at`` +
   resets the ``citation_count_at_score`` snapshot. Bounded by config knobs
   (``rescore_max_per_run`` etc).

Both functions are safe to interrupt and idempotent on re-run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from paper_agent.config import CitationsConfig
    from paper_agent.scorer.citation_provider import CitationProvider
    from paper_agent.scorer.claude_scorer import ClaudeScorer
    from paper_agent.storage.database import PaperDatabase

logger = logging.getLogger(__name__)


def _is_old_enough(sp, min_age_years: int) -> bool:
    """True when the paper's published date is at least ``min_age_years`` ago.

    Defensive against missing or naive ``published`` values (legacy rows or
    rows seeded by ``scripts/seed_older_works.py`` which only knew a year):
    naive datetimes are coerced to UTC for the comparison.
    """
    pub = sp.paper.published
    if pub is None:
        return False
    if pub.tzinfo is None:
        pub = pub.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    age_years = (now - pub).days / 365.25
    return age_years >= min_age_years


@dataclass(frozen=True)
class RefreshResult:
    """Outcome of a single refresh tick (citation fetch + optional re-score)."""

    candidates_selected: int
    citations_updated: int
    rescored: int


def refresh_citations(
    db: PaperDatabase,
    provider: CitationProvider,
    config: CitationsConfig,
    *,
    force_all: bool = False,
    stale_after_hours: float | None = None,
) -> int:
    """Fetch fresh citation counts for stale (or all, when ``force_all``) papers.

    Returns the number of rows whose citation columns were updated.

    Knobs:
      * ``force_all``: ignore staleness, refresh every cached paper. Used by
        ``paper-agent refresh-citations --all``.
      * ``stale_after_hours``: override the default
        ``config.refresh_interval_hours`` cutoff (used by
        ``--stale-days``).

    Selection is capped at ``config.refresh_candidate_limit`` so a single
    tick can't drown the provider; remaining stale rows are picked up next
    tick.
    """
    if force_all:
        # We still go through get_stale_citations with hours=0 so the LIMIT
        # protection applies; force-all callers can paginate by re-running.
        threshold = 0.0
    else:
        threshold = (
            stale_after_hours
            if stale_after_hours is not None
            else float(config.refresh_interval_hours)
        )

    candidates = db.get_stale_citations(
        limit=config.refresh_candidate_limit,
        stale_after_hours=threshold,
    )
    if not candidates:
        logger.info("Citation refresh: no stale candidates.")
        return 0

    logger.info(
        "Citation refresh: fetching %d papers from provider (threshold=%.1fh)...",
        len(candidates),
        threshold,
    )
    fetched = provider.get_citations(candidates)
    if not fetched:
        logger.info("Citation refresh: provider returned no data.")
        return 0

    updates = [
        (arxiv_id, info.citation_count, info.influential_citation_count)
        for arxiv_id, info in fetched.items()
    ]
    rowcount = db.update_citations(updates)
    logger.info(
        "Citation refresh: updated %d/%d rows (%d ids unknown to provider)",
        rowcount,
        len(candidates),
        len(candidates) - len(fetched),
    )
    return rowcount


def rescore_dynamic(
    db: PaperDatabase,
    scorer: ClaudeScorer,
    config: CitationsConfig,
) -> int:
    """Re-score papers whose citation growth crossed the configured threshold.

    Skipped entirely (returns 0) when ``rescore_max_per_run == 0`` or
    ``citations.enabled == false`` — those switches are how the operator
    fully disables Claude calls from the refresh path while still collecting
    citation data.

    For each candidate we feed the scorer the *current* citation counts as
    context so Claude can re-judge relevance/quality/tier. We then merge the
    new score fields with the existing citation columns and write back via
    :meth:`PaperDatabase.cache_papers`. Critically, ``cache_papers`` uses
    ``INSERT OR REPLACE`` which would clobber the citation columns to NULL
    if we didn't pass them through — that merge is the load-bearing step.

    Returns the number of papers re-scored.
    """
    if not config.enabled:
        return 0
    if config.rescore_max_per_run <= 0:
        logger.debug("Dynamic rescore disabled (rescore_max_per_run=0).")
        return 0

    candidates = db.get_rescore_candidates(
        min_delta=config.rescore_min_delta,
        min_ratio=config.rescore_min_ratio,
        min_interval_days=config.rescore_min_interval_days,
        limit=config.rescore_max_per_run,
    )
    if not candidates:
        logger.info("Dynamic rescore: no eligible candidates.")
        return 0

    logger.info(
        "Dynamic rescore: re-scoring %d paper(s) with citation context (growth-largest-first)...",
        len(candidates),
    )

    citation_context: dict[str, tuple[int, int]] = {
        sp.paper.arxiv_id: (sp.citation_count, sp.influential_citation_count) for sp in candidates
    }
    raw_papers = [sp.paper for sp in candidates]

    rescored = scorer.score(raw_papers, citation_context=citation_context)
    if not rescored:
        logger.warning("Dynamic rescore: scorer returned no results.")
        return 0

    # Merge back: keep the citation fields from the cached row, take the
    # newly-judged scored fields. The snapshot field is reset to the current
    # citation_count by cache_papers (its INSERT OR REPLACE writes
    # citation_count_at_score = sp.citation_count), so the next growth
    # comparison measures from this fresh baseline.
    #
    # Auto-promotion to paper_kind="older": if rescoring detected enough
    # citation growth that the paper crossed the promote threshold AND it's
    # been published long enough to qualify as "older", flip its kind so it
    # surfaces in the older-works section. This is how a fresh paper that
    # quietly accumulates citations over a year or two earns its place
    # alongside the manually-discovered classics — without it, the
    # discovery-only path would forever miss naturally-emerging classics.
    promote_threshold = config.older_works_promote_min_citations
    min_age_years = config.older_works_min_age_years
    by_arxiv = {sp.paper.arxiv_id: sp for sp in candidates}
    merged: list = []
    promoted_count = 0
    for sp_new in rescored:
        prior = by_arxiv.get(sp_new.paper.arxiv_id)
        if prior is None:
            # Defensive: scorer returned a paper we didn't ask about.
            continue
        new_kind = prior.paper_kind
        if (
            prior.paper_kind == "fresh"
            and prior.citation_count >= promote_threshold
            and _is_old_enough(prior, min_age_years)
        ):
            new_kind = "older"
            promoted_count += 1
        merged.append(
            replace(
                sp_new,
                citation_count=prior.citation_count,
                influential_citation_count=prior.influential_citation_count,
                citations_updated_at=prior.citations_updated_at,
                paper_kind=new_kind,
                # citation_count_at_score is overwritten by cache_papers to
                # the current citation_count; passing the prior value here
                # is harmless and documents intent.
                citation_count_at_score=prior.citation_count,
            )
        )

    db.cache_papers(merged)
    if promoted_count > 0:
        logger.info(
            "Dynamic rescore: promoted %d fresh paper(s) → older "
            "(citation_count ≥ %d, age ≥ %d years)",
            promoted_count,
            promote_threshold,
            min_age_years,
        )
    logger.info("Dynamic rescore: updated %d paper(s).", len(merged))
    return len(merged)


def refresh_and_rescore(
    db: PaperDatabase,
    provider: CitationProvider,
    scorer: ClaudeScorer,
    config: CitationsConfig,
    *,
    force_all: bool = False,
    stale_after_hours: float | None = None,
) -> RefreshResult:
    """Run the full refresh tick: fetch citations, then dynamic re-score.

    Used by both the scheduler job and the ``refresh-citations`` CLI so
    they share the exact same sequencing (refresh-then-rescore) and
    cost-control behavior.
    """
    updated = refresh_citations(
        db,
        provider,
        config,
        force_all=force_all,
        stale_after_hours=stale_after_hours,
    )
    rescored = rescore_dynamic(db, scorer, config)
    return RefreshResult(
        candidates_selected=updated,
        citations_updated=updated,
        rescored=rescored,
    )
