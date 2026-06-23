"""Main pipeline orchestrator with multi-user support.

Architecture:
  Shared phase:  fetch → dedup(cache) → score → cache results
  Per-user phase: filter(sub-domain + thresholds) → dedup(sent) → notify → mark_sent
"""

from __future__ import annotations

import logging
from datetime import datetime

from paper_agent.config import AppConfig, UserConfig
from paper_agent.fetcher.arxiv_fetcher import ArxivFetcher
from paper_agent.models import (
    SUB_DOMAINS,
    ScoredPaper,
    ScoreWeights,
    sort_by_score,
    tier_rank,
)
from paper_agent.notifier import Notifier, create_notifiers_for_user
from paper_agent.scorer.claude_scorer import ClaudeScorer
from paper_agent.storage.database import PaperDatabase

logger = logging.getLogger(__name__)


class Pipeline:
    """Orchestrates the fetch → dedup → score → filter → notify pipeline."""

    def __init__(self, config: AppConfig):
        self.config = config

        # Build superset of keywords from global fetch keywords + all sub-domain names
        all_keywords = self._build_superset_keywords(config)

        self.fetcher = ArxivFetcher(
            categories=config.fetch.categories,
            keywords=all_keywords,
            quality_floor_strategy=config.fetch.quality_floor_strategy,
            min_per_keyword=config.fetch.min_per_keyword,
            cross_list_categories=config.fetch.cross_list_categories,
        )
        self.scorer = ClaudeScorer(config=config.scoring)
        self.db = PaperDatabase(config.storage.db_path)
        self.score_weights = ScoreWeights.from_scoring_config(config.scoring)
        # Citation tiebreaker activates only when both citations.enabled AND
        # scoring.citation_weight > 0. Pre-change behavior (one of those is
        # off) collapses to citation_ceiling=None, which sort_by_score treats
        # as "no citation key" — preserves old ordering bit-for-bit.
        self._citation_ceiling: int | None = (
            config.citations.normalization_ceiling
            if config.citations.enabled and config.scoring.citation_weight > 0
            else None
        )

        # Per-user notifiers: {user_id: [Notifier, ...]}
        self.user_notifiers: dict[str, list[Notifier]] = {}
        for user in config.users:
            notifiers = create_notifiers_for_user(user.notify)
            if notifiers:
                self.user_notifiers[user.user_id] = notifiers
            else:
                logger.warning(
                    f"User '{user.user_id}' has no enabled notifiers. Check their notify config."
                )

    def refresh_users(self) -> dict[str, int]:
        """Reconcile in-memory users with the active subscriptions table.

        Daemon processes load subscriptions once at startup; web subscriptions
        added afterwards are invisible to them until restart. Calling this at
        the top of each scheduled job fixes that: rows in the database but
        not in :attr:`config.users` are appended (with new notifiers), and
        users in :attr:`config.users` that have no matching active subscription
        are dropped (their notifier entry is removed too).

        Users present in both are left untouched — we deliberately do NOT
        rebuild notifiers for existing users, so any SMTP connection state
        snapshotted at process start survives the refresh. Changes to
        ``config.email`` still require a daemon restart, as documented in
        CLAUDE.md.

        Database read failures degrade gracefully: a warning is logged and
        the previously-loaded user list is left intact so the scheduled job
        can still run.

        Returns a small dict ``{"added": N, "removed": M, "active": K}`` for
        logging / tests.
        """
        from paper_agent.subscriptions import build_user_config_for_subscription

        try:
            subscriptions = self.db.load_active_subscriptions()
        except Exception as exc:
            logger.warning(
                "Subscription refresh failed; using previous user list "
                f"({len(self.config.users)} users): {exc}"
            )
            return {"added": 0, "removed": 0, "active": len(self.config.users)}

        active_ids = {sub["email"] for sub in subscriptions}
        existing_ids = {u.user_id for u in self.config.users}

        # Drop departed users (unsubscribed since last tick).
        removed = 0
        if existing_ids - active_ids:
            kept: list[UserConfig] = []
            for user in self.config.users:
                if user.user_id in active_ids:
                    kept.append(user)
                else:
                    self.user_notifiers.pop(user.user_id, None)
                    removed += 1
                    logger.info(f"refresh_users: dropped subscription user '{user.user_id}'")
            self.config.users = kept

        # Append new users (subscribed since last tick).
        added = 0
        for sub in subscriptions:
            email = sub["email"]
            if email in existing_ids:
                continue
            user_cfg = build_user_config_for_subscription(sub, self.config)
            self.config.users.append(user_cfg)
            notifiers = create_notifiers_for_user(user_cfg.notify)
            if notifiers:
                self.user_notifiers[email] = notifiers
            else:
                logger.warning(
                    f"User '{email}' has no enabled notifiers. Check their notify config."
                )
            added += 1
            logger.info(f"refresh_users: added subscription user '{email}'")

        if added or removed:
            logger.info(
                f"refresh_users: +{added} added, -{removed} removed, "
                f"{len(self.config.users)} active"
            )
        return {"added": added, "removed": removed, "active": len(self.config.users)}

    def _build_superset_keywords(self, config: AppConfig) -> list[str]:
        """Build keywords for arXiv search.

        Uses global fetch keywords + all sub-domain names (not all sub-domain keywords).
        The scorer handles precise sub-domain tagging; we just need broad recall.
        """
        keywords = set(config.fetch.keywords)

        # Add all sub-domain names as keywords (e.g., "quantization", "distillation")
        # but NOT all their associated keywords (that would make the query too long).
        # This ensures broad coverage regardless of which specific sub-domains users
        # are subscribed to.
        for sd_name in SUB_DOMAINS:
            keywords.add(sd_name.replace("_", " "))

        logger.debug(f"Superset keywords ({len(keywords)}): {sorted(keywords)}")
        return list(keywords)

    def ingest(self, days_back: int | None = None) -> list[ScoredPaper]:
        """Fetch, score, and cache papers without notifying users."""
        days = days_back or self.config.fetch.days_back

        logger.info(f"Ingest: Fetching papers from arXiv (last {days} days)...")
        papers = self.fetcher.fetch(
            max_results=self.config.fetch.max_results,
            days_back=days,
        )

        if not papers:
            logger.info("Ingest: No papers found.")
            scored_new: list[ScoredPaper] = []
            cached_papers: list = []
        else:
            logger.info(f"Ingest: Checking cache ({len(papers)} papers)...")
            paper_ids = [p.arxiv_id for p in papers]
            uncached_ids = set(self.db.filter_uncached(paper_ids))
            cached_papers = [p for p in papers if p.arxiv_id not in uncached_ids]
            new_papers = [p for p in papers if p.arxiv_id in uncached_ids]

            logger.info(f"  → {len(new_papers)} new, {len(cached_papers)} already cached")

            scored_new = []
            if new_papers:
                logger.info(f"Ingest: Scoring with Claude ({len(new_papers)} papers)...")
                scored_new = self.scorer.score(new_papers)
                self.db.cache_papers(scored_new)
                logger.info(f"  → Cached {len(scored_new)} scored papers")
            else:
                logger.info("Ingest: No new papers to score.")

        # Older-works track: discover highly-cited older papers via Semantic
        # Scholar, score the new ones, and tag them with paper_kind="older".
        # Only runs when both citations are enabled AND someone wants older
        # works in their digest (older_works_per_digest > 0). Capped per
        # ingest to bound one-time Claude cost on first enable.
        scored_older: list[ScoredPaper] = []
        if self.config.citations.enabled and self.config.thresholds.older_works_per_digest > 0:
            scored_older = self._ingest_older_works()

        scored_cached = self.db.load_cached_papers([p.arxiv_id for p in cached_papers])
        all_scored = scored_new + scored_older + scored_cached
        logger.info(
            f"Ingest complete. {len(scored_new)} new fresh, "
            f"{len(scored_older)} new older, "
            f"{len(all_scored)} total scored papers."
        )
        return all_scored

    def _ingest_older_works(self) -> list[ScoredPaper]:
        """Discover and score highly-cited older papers (citation-aware-scoring).

        Three behaviours that distinguish this from a "find + score new"
        loop:

        1. **Already-cached classics get promoted.** When S2 search surfaces
           a paper that we already have as ``paper_kind="fresh"``, we don't
           silently skip it — if its citation_count crosses
           ``older_works_promote_min_citations`` we flip its ``paper_kind``
           to ``"older"`` (preserving every other column). Without this, a
           deployment that ran for months would have the best classics
           stuck in fresh and invisible to the older-works section.

        2. **Claude sees the citation count when scoring new older works.**
           We pull the count via the citation provider and pass it as
           ``citation_context`` to the scorer — a 5000-cite paper isn't
           judged blind on its abstract alone.

        3. **The originating sub-domain is force-tagged.** If S2's
           ``quantization`` query surfaced the paper but Claude tagged it
           ``compiler``, quantization subscribers wouldn't see it. We merge
           the source sub-domain into ``sub_domain_tags`` after scoring.
        """
        from dataclasses import replace as _replace

        from paper_agent.fetcher.older_works_fetcher import discover_older_works

        candidates, source_map, citation_map = discover_older_works(
            self.config.citations,
            self.config.thresholds,
        )
        if not candidates:
            return []

        candidate_ids = [p.arxiv_id for p in candidates]
        new_ids = set(self.db.filter_uncached(candidate_ids))
        already_cached_ids = [aid for aid in candidate_ids if aid not in new_ids]

        # Path A: promote already-cached classics from fresh → older.
        promote_threshold = self.config.citations.older_works_promote_min_citations
        if already_cached_ids:
            self._promote_cached_to_older(already_cached_ids, promote_threshold)

        # Path B: score brand-new older candidates.
        new_candidates = [p for p in candidates if p.arxiv_id in new_ids]
        cap = self.config.citations.older_works_max_new_per_ingest
        if cap > 0 and len(new_candidates) > cap:
            logger.info(
                "Older-works: %d candidates exceed per-ingest cap (%d), deferring %d to next tick",
                len(new_candidates),
                cap,
                len(new_candidates) - cap,
            )
            new_candidates = new_candidates[:cap]

        if not new_candidates:
            logger.info("Older-works: no new (uncached) candidates this run.")
            return []

        # Citation context comes straight from discovery — no second S2
        # round-trip, which used to silently zero out counts when batch
        # endpoint was rate-limited mid-ingest.
        citation_context: dict[str, tuple[int, int]] = {
            p.arxiv_id: citation_map[p.arxiv_id]
            for p in new_candidates
            if p.arxiv_id in citation_map
        }

        logger.info(
            "Older-works: scoring %d new paper(s) with citation context...",
            len(new_candidates),
        )
        scored = self.scorer.score(new_candidates, citation_context=citation_context)

        # Tag every newly scored older paper before caching: paper_kind +
        # source sub-domain (so subscribers in that sub-domain see it).
        scored_older: list[ScoredPaper] = []
        for sp in scored:
            aid = sp.paper.arxiv_id
            cc, ic = citation_context.get(aid, (0, 0))
            tags = set(sp.sub_domain_tags or ())
            src = source_map.get(aid)
            if src:
                tags.add(src)
            scored_older.append(
                _replace(
                    sp,
                    paper_kind="older",
                    citation_count=cc,
                    influential_citation_count=ic,
                    citations_updated_at=(datetime.now().isoformat() if cc > 0 else None),
                    citation_count_at_score=cc,
                    sub_domain_tags=tuple(sorted(tags)),
                )
            )
        self.db.cache_papers(scored_older)
        logger.info("Older-works: cached %d older paper(s).", len(scored_older))
        return scored_older

    def _promote_cached_to_older(
        self,
        arxiv_ids: list[str],
        promote_threshold: int,
    ) -> None:
        """Flip cached papers from paper_kind='fresh' → 'older' when warranted.

        Called by ``_ingest_older_works`` for arxiv_ids that S2 search
        surfaced AND that are already in our cache. We only promote when
        the cached citation_count is at or above ``promote_threshold`` —
        promotion is a stronger claim than discovery, so the bar is
        higher than ``min_citations_for_older_works`` (which only governs
        the S2 search funnel). Existing scores, summaries, and the
        ``citation_count_at_score`` snapshot are preserved — we touch
        only ``paper_kind``.
        """
        if not arxiv_ids:
            return
        with self.db._connect() as conn:
            placeholders = ",".join("?" * len(arxiv_ids))
            cursor = conn.execute(
                f"""UPDATE papers
                    SET paper_kind = 'older'
                    WHERE arxiv_id IN ({placeholders})
                      AND COALESCE(paper_kind, 'fresh') = 'fresh'
                      AND COALESCE(citation_count, 0) >= ?""",
                [*arxiv_ids, promote_threshold],
            )
            promoted = cursor.rowcount
        if promoted > 0:
            logger.info(
                "Older-works: promoted %d already-cached classic(s) "
                "from fresh → older (≥%d citations)",
                promoted,
                promote_threshold,
            )

    def run(
        self,
        dry_run: bool = False,
        days_back: int | None = None,
        user_ids: list[str] | None = None,
    ) -> dict[str, list[ScoredPaper]]:
        """Execute the full fetch → score → notify pipeline."""
        all_scored = self.ingest(days_back=days_back)
        if not all_scored:
            return {}
        return self._run_digest(all_scored, dry_run=dry_run, user_ids=user_ids)

    def run_cached_digest(
        self,
        dry_run: bool = False,
        user_ids: list[str] | None = None,
    ) -> dict[str, list[ScoredPaper]]:
        """Send user digests using cached scored papers only."""
        total_cached = self.db.count_papers()
        if total_cached == 0:
            logger.info("No cached papers available for digest.")
            return {}
        all_scored = self.db.list_papers(limit=total_cached)
        return self._run_digest(all_scored, dry_run=dry_run, user_ids=user_ids)

    def _run_digest(
        self,
        all_scored: list[ScoredPaper],
        dry_run: bool = False,
        user_ids: list[str] | None = None,
    ) -> dict[str, list[ScoredPaper]]:
        """Filter cached/scored papers and notify selected users."""
        users = self.config.users
        if user_ids:
            users = [u for u in users if u.user_id in user_ids]

        if not users:
            logger.warning("No users to process.")
            return {}

        logger.info(f"Digest: Filtering for {len(users)} user(s)...")
        results: dict[str, list[ScoredPaper]] = {}
        for user in users:
            try:
                user_papers = self._run_for_user(user, all_scored, dry_run=dry_run)
            except Exception:
                logger.error(
                    f"  [{user.display_name or user.user_id}] Failed, skipping",
                    exc_info=True,
                )
                user_papers = []
            results[user.user_id] = user_papers

        total_sent = sum(len(v) for v in results.values())
        logger.info(f"Digest complete. {total_sent} papers across {len(users)} user(s).")
        return results

    def run_cached_for_user(
        self,
        user_id: str,
        dry_run: bool = False,
    ) -> dict[str, list[ScoredPaper]]:
        """Send an immediate digest to one user using already cached papers only."""
        users = [u for u in self.config.users if u.user_id == user_id]
        if not users:
            logger.warning(f"No user found for cached digest: {user_id}")
            return {}

        total_cached = self.db.count_papers()
        if total_cached == 0:
            logger.info(f"No cached papers available for initial digest: {user_id}")
            return {user_id: []}

        all_scored = self.db.list_papers(limit=total_cached)
        return {user_id: self._run_for_user(users[0], all_scored, dry_run=dry_run)}

    def _run_for_user(
        self,
        user: UserConfig,
        all_scored: list[ScoredPaper],
        dry_run: bool,
    ) -> list[ScoredPaper]:
        """Filter and notify for a single user."""
        uid = user.user_id
        display = user.display_name or uid

        sub_domains = user.subscriptions.sub_domains
        min_rel = user.thresholds.min_relevance
        min_qual = user.thresholds.min_quality
        min_tier_rank = tier_rank(user.thresholds.min_tier)
        weights = self.score_weights

        # Tier + score thresholds first — defines the eligibility pool.
        # Older-works papers are excluded here; they go through their own
        # selection path below so they're additive to top_n.
        eligible = [
            sp
            for sp in all_scored
            if sp.paper_kind != "older"
            and tier_rank(sp.impact_tier) <= min_tier_rank
            and sp.relevance_score >= min_rel
            and sp.quality_score >= min_qual
        ]

        # Drop already-sent papers BEFORE bucketing/top-N. Doing this last
        # (the previous design) let high-scoring historical papers occupy the
        # per-domain top-N slots every day and then get filtered out, leaving
        # the digest with only a handful of new papers regardless of how big
        # per_sub_domain_top_n was. Filtering here means buckets allocate
        # their N slots to papers the user has never seen.
        if eligible:
            eligible_ids = [sp.paper.arxiv_id for sp in eligible]
            unsent_ids = set(self.db.filter_unsent_for_user(uid, eligible_ids))
            eligible = [sp for sp in eligible if sp.paper.arxiv_id in unsent_ids]

        if "all" in sub_domains:
            # "all" subscribers: no per-domain bucketing — just sort and cap.
            filtered = sort_by_score(
                eligible, weights=weights, citation_ceiling=self._citation_ceiling
            )[: user.thresholds.top_n]
        else:
            # Per-sub-domain top-N (over unsent only), then merge + dedup,
            # then apply user-level top_n as cap.
            per_domain_top = user.thresholds.per_sub_domain_top_n
            bucket_sizes: list[str] = []
            seen: set[str] = set()
            merged: list = []
            for sd in sub_domains:
                bucket = [sp for sp in eligible if sd in sp.sub_domain_tags]
                bucket = sort_by_score(
                    bucket, weights=weights, citation_ceiling=self._citation_ceiling
                )[:per_domain_top]
                bucket_sizes.append(f"{sd}={len(bucket)}")
                for sp in bucket:
                    if sp.paper.arxiv_id not in seen:
                        seen.add(sp.paper.arxiv_id)
                        merged.append(sp)
            # Re-sort the deduped union and apply the overall cap.
            filtered = sort_by_score(
                merged, weights=weights, citation_ceiling=self._citation_ceiling
            )[: user.thresholds.top_n]
            logger.info(f"  [{display}] per-domain buckets: {', '.join(bucket_sizes)}")

        if not filtered:
            logger.info(f"  [{display}] No new papers to send")
            return []

        # ── Older-works track: additive to top_n, separate selection pool ──
        older_papers: list[ScoredPaper] = []
        older_n = getattr(user.thresholds, "older_works_per_digest", 0)
        if older_n > 0 and self.config.citations.enabled:
            older_pool = [
                sp
                for sp in all_scored
                if sp.paper_kind == "older"
                and tier_rank(sp.impact_tier) <= min_tier_rank
                and sp.relevance_score >= min_rel
                and sp.quality_score >= min_qual
                # Subscribed sub-domain match (or "all")
                and ("all" in sub_domains or any(sd in sp.sub_domain_tags for sd in sub_domains))
            ]
            if older_pool:
                # De-dup against this user's sent_papers so the same older
                # work isn't shipped twice.
                older_ids = [sp.paper.arxiv_id for sp in older_pool]
                unsent_older_ids = set(self.db.filter_unsent_for_user(uid, older_ids))
                # Also exclude anything already chosen in `filtered` (a paper
                # tagged as "older" that also matched the fresh path — rare
                # but possible if paper_kind got flipped in storage).
                fresh_chosen_ids = {sp.paper.arxiv_id for sp in filtered}
                older_pool = [
                    sp
                    for sp in older_pool
                    if sp.paper.arxiv_id in unsent_older_ids
                    and sp.paper.arxiv_id not in fresh_chosen_ids
                ]
                older_papers = sort_by_score(
                    older_pool, weights=weights, citation_ceiling=self._citation_ceiling
                )[:older_n]

        if older_papers:
            logger.info(f"  [{display}] +{len(older_papers)} older work(s) (additive to top_n)")

        logger.info(
            f"  [{display}] {len(filtered)} fresh + {len(older_papers)} older "
            f"(sub_domains={sub_domains})"
        )

        # The notifier sees fresh + older as a single list; the formatter
        # splits them by paper_kind to render distinct sections.
        to_send = filtered + older_papers

        # Notify
        notifiers = self.user_notifiers.get(uid, [])
        if not notifiers:
            logger.warning(f"  [{display}] No notifiers configured, skipping")
            return to_send

        if dry_run:
            logger.info(f"  [{display}] [DRY RUN] Would send {len(to_send)} papers")
            self._print_results(display, to_send)
        else:
            any_success = False
            for notifier in notifiers:
                logger.info(f"  [{display}] Sending via {notifier.name}...")
                success = notifier.notify(to_send)
                if success:
                    logger.info(f"    ✓ {notifier.name} sent")
                    any_success = True
                else:
                    logger.error(f"    ✗ {notifier.name} failed")

            if any_success:
                # Mark as sent only when at least one notifier succeeded,
                # so failed deliveries can be retried on the next digest.
                # Both fresh and older papers are marked so neither gets
                # re-sent next cycle.
                self.db.mark_sent(uid, to_send)
                logger.info(f"  [{display}] Marked {len(to_send)} papers as sent")
            else:
                logger.warning(
                    f"  [{display}] All notifiers failed; papers NOT marked as sent "
                    f"(will retry next digest)"
                )

        return to_send

    def _print_results(self, user_display: str, papers: list[ScoredPaper]) -> None:
        """Print results to console (for dry-run mode)."""
        print(f"\n{'=' * 80}")
        print(f"📊 DRY RUN for {user_display}: {len(papers)} papers")
        print("=" * 80)
        for i, sp in enumerate(papers, 1):
            print(f"\n{i}. {sp.paper.title}")
            print(f"   Relevance: {sp.relevance_score:.1f}/10  Quality: {sp.quality_score:.1f}/10")
            print(f"   Tags: {sp.sub_domain_display}")
            print(f"   {sp.summary_zh}")
            print(f"   {sp.paper.abs_url}")
        print("\n" + "=" * 80)
