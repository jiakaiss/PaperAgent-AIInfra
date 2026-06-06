"""Main pipeline orchestrator with multi-user support.

Architecture:
  Shared phase:  fetch → dedup(cache) → score → cache results
  Per-user phase: filter(sub-domain + thresholds) → dedup(sent) → notify → mark_sent
"""

from __future__ import annotations

import logging

from paper_agent.config import AppConfig, UserConfig
from paper_agent.fetcher.arxiv_fetcher import ArxivFetcher
from paper_agent.models import SUB_DOMAINS, ScoredPaper, ScoreWeights, sort_by_score
from paper_agent.notifier import Notifier, create_notifiers_for_user
from paper_agent.scorer.claude_scorer import ClaudeScorer
from paper_agent.storage.database import PaperDatabase

logger = logging.getLogger(__name__)


class Pipeline:
    """Orchestrates the fetch → dedup → score → filter → notify pipeline."""

    def __init__(self, config: AppConfig):
        self.config = config

        # Build superset of keywords from all users' subscriptions + global fetch keywords
        all_keywords = self._build_superset_keywords(config)

        self.fetcher = ArxivFetcher(
            categories=config.fetch.categories,
            keywords=all_keywords,
        )
        self.scorer = ClaudeScorer(config=config.scoring)
        self.db = PaperDatabase(config.storage.db_path)
        self.score_weights = ScoreWeights.from_scoring_config(config.scoring)

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

    def _build_superset_keywords(self, config: AppConfig) -> list[str]:
        """Build keywords for arXiv search.

        Uses global fetch keywords + sub-domain names (not all sub-domain keywords).
        The scorer handles precise sub-domain tagging; we just need broad recall.
        """
        keywords = set(config.fetch.keywords)

        # Add sub-domain names as keywords (e.g., "quantization", "distillation")
        # but NOT all their associated keywords (that would make the query too long)
        for user in config.users:
            sub_domains = user.subscriptions.sub_domains
            if "all" in sub_domains:
                sub_domains = list(SUB_DOMAINS.keys())
            for sd in sub_domains:
                # Just add the sub-domain name itself, formatted for search
                keywords.add(sd.replace("_", " "))

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
            return []

        logger.info(f"Ingest: Checking cache ({len(papers)} papers)...")
        paper_ids = [p.arxiv_id for p in papers]
        uncached_ids = set(self.db.filter_uncached(paper_ids))
        cached_papers = [p for p in papers if p.arxiv_id not in uncached_ids]
        new_papers = [p for p in papers if p.arxiv_id in uncached_ids]

        logger.info(f"  → {len(new_papers)} new, {len(cached_papers)} already cached")

        scored_new: list[ScoredPaper] = []
        if new_papers:
            logger.info(f"Ingest: Scoring with Claude ({len(new_papers)} papers)...")
            scored_new = self.scorer.score(new_papers)
            self.db.cache_papers(scored_new)
            logger.info(f"  → Cached {len(scored_new)} scored papers")
        else:
            logger.info("Ingest: No new papers to score.")

        scored_cached = self.db.load_cached_papers([p.arxiv_id for p in cached_papers])
        all_scored = scored_new + scored_cached
        logger.info(
            f"Ingest complete. {len(scored_new)} new, "
            f"{len(all_scored)} fetched scored papers."
        )
        return all_scored

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
            user_papers = self._run_for_user(user, all_scored, dry_run=dry_run)
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
        weights = self.score_weights

        if "all" in sub_domains:
            # "all" subscribers: filter by thresholds and take user-level top_n.
            # Per-domain limit doesn't apply because there's no sub-domain to bucket by.
            filtered = [
                sp for sp in all_scored
                if sp.relevance_score >= min_rel and sp.quality_score >= min_qual
            ]
            filtered = sort_by_score(filtered, weights=weights)[: user.thresholds.top_n]
        else:
            # Per-sub-domain top-N then merge + dedup, then apply user-level top_n as cap.
            per_domain_top = user.thresholds.per_sub_domain_top_n
            bucket_sizes: list[str] = []
            seen: set[str] = set()
            merged: list = []
            for sd in sub_domains:
                bucket = [
                    sp for sp in all_scored
                    if sd in sp.sub_domain_tags
                    and sp.relevance_score >= min_rel
                    and sp.quality_score >= min_qual
                ]
                bucket = sort_by_score(bucket, weights=weights)[:per_domain_top]
                bucket_sizes.append(f"{sd}={len(bucket)}")
                for sp in bucket:
                    if sp.paper.arxiv_id not in seen:
                        seen.add(sp.paper.arxiv_id)
                        merged.append(sp)
            # Re-sort the deduped union and apply the overall cap.
            filtered = sort_by_score(merged, weights=weights)[: user.thresholds.top_n]
            logger.info(f"  [{display}] per-domain buckets: {', '.join(bucket_sizes)}")

        # Dedup per user
        ids = [sp.paper.arxiv_id for sp in filtered]
        new_ids = set(self.db.filter_unsent_for_user(uid, ids))
        filtered = [sp for sp in filtered if sp.paper.arxiv_id in new_ids]

        if not filtered:
            logger.info(f"  [{display}] No new papers to send")
            return []

        logger.info(f"  [{display}] {len(filtered)} papers matched (sub_domains={sub_domains})")

        # Notify
        notifiers = self.user_notifiers.get(uid, [])
        if not notifiers:
            logger.warning(f"  [{display}] No notifiers configured, skipping")
            return filtered

        if dry_run:
            logger.info(f"  [{display}] [DRY RUN] Would send {len(filtered)} papers")
            self._print_results(display, filtered)
        else:
            for notifier in notifiers:
                logger.info(f"  [{display}] Sending via {notifier.name}...")
                success = notifier.notify(filtered)
                if success:
                    logger.info(f"    ✓ {notifier.name} sent")
                else:
                    logger.error(f"    ✗ {notifier.name} failed")

            # Mark as sent for this user
            self.db.mark_sent(uid, filtered)
            logger.info(f"  [{display}] Marked {len(filtered)} papers as sent")

        return filtered

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
