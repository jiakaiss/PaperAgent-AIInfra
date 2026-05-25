"""Main pipeline orchestrator."""

from __future__ import annotations

import logging

from paper_agent.config import AppConfig
from paper_agent.fetcher.arxiv_fetcher import ArxivFetcher
from paper_agent.models import ScoredPaper, sort_by_score
from paper_agent.notifier import Notifier, create_notifiers
from paper_agent.scorer.claude_scorer import ClaudeScorer
from paper_agent.storage.database import PaperDatabase

logger = logging.getLogger(__name__)


class Pipeline:
    """Orchestrates the fetch → dedup → score → filter → notify pipeline."""

    def __init__(self, config: AppConfig):
        self.config = config

        self.fetcher = ArxivFetcher(
            categories=config.fetch.categories,
            keywords=config.fetch.keywords,
        )
        self.scorer = ClaudeScorer(
            model=config.scoring.model,
            batch_size=config.scoring.batch_size,
        )
        self.db = PaperDatabase(config.storage.db_path)
        self.notifiers = create_notifiers(config.notify)

    def run(
        self,
        dry_run: bool = False,
        days_back: int | None = None,
        top_n: int | None = None,
    ) -> list[ScoredPaper]:
        """Execute the full pipeline.

        Args:
            dry_run: If True, skip notification step
            days_back: Override fetch.days_back config
            top_n: Override scoring.top_n config

        Returns:
            List of scored papers that passed filters
        """
        days = days_back or self.config.fetch.days_back
        max_papers = top_n or self.config.scoring.top_n

        # Step 1: Fetch
        logger.info(f"Step 1/5: Fetching papers from arXiv (last {days} days)...")
        papers = self.fetcher.fetch(
            max_results=self.config.fetch.max_results,
            days_back=days,
        )

        if not papers:
            logger.info("No papers found. Pipeline complete.")
            return []

        # Step 2: Dedup
        logger.info(f"Step 2/5: Deduplicating ({len(papers)} papers)...")
        paper_ids = [p.arxiv_id for p in papers]
        new_ids = set(self.db.filter_new(paper_ids))
        papers = [p for p in papers if p.arxiv_id in new_ids]
        logger.info(f"  → {len(papers)} new papers (filtered {len(paper_ids) - len(papers)} duplicates)")

        if not papers:
            logger.info("All papers already sent. Pipeline complete.")
            return []

        # Step 3: Score
        logger.info(f"Step 3/5: Scoring with Claude ({len(papers)} papers)...")
        scored = self.scorer.score(papers)

        # Step 4: Filter
        logger.info("Step 4/5: Filtering by score thresholds...")
        filtered = [
            sp
            for sp in scored
            if sp.relevance_score >= self.config.scoring.min_relevance
            and sp.quality_score >= self.config.scoring.min_quality
        ]
        filtered = sort_by_score(filtered)[:max_papers]

        logger.info(
            f"  → {len(filtered)} papers passed filters "
            f"(relevance>={self.config.scoring.min_relevance}, "
            f"quality>={self.config.scoring.min_quality})"
        )

        if not filtered:
            logger.info("No papers passed quality filters. Pipeline complete.")
            return []

        # Step 5: Notify
        if dry_run:
            logger.info("Step 5/5: [DRY RUN] Skipping notification")
            self._print_results(filtered)
        else:
            logger.info(f"Step 5/5: Sending to {len(self.notifiers)} notifier(s)...")
            self._notify(filtered)

        return filtered

    def _notify(self, papers: list[ScoredPaper]) -> None:
        """Send notifications and mark sent papers on success."""
        for notifier in self.notifiers:
            logger.info(f"  → Sending via {notifier.name}...")
            success = notifier.notify(papers)
            if success:
                logger.info(f"    ✓ {notifier.name} sent successfully")
            else:
                logger.error(f"    ✗ {notifier.name} failed")

        # Mark as sent after all notifiers attempted
        # (even if some failed, to avoid duplicate sends on retry)
        self.db.mark_sent(papers)
        logger.info(f"  → Marked {len(papers)} papers as sent")

    def _print_results(self, papers: list[ScoredPaper]) -> None:
        """Print results to console (for dry-run mode)."""
        print("\n" + "=" * 80)
        print(f"📊 DRY RUN: {len(papers)} papers would be sent")
        print("=" * 80)
        for i, sp in enumerate(papers, 1):
            print(f"\n{i}. {sp.paper.title}")
            print(f"   Relevance: {sp.relevance_score:.1f}/10  Quality: {sp.quality_score:.1f}/10")
            print(f"   {sp.summary_zh}")
            print(f"   Categories: {', '.join(sp.paper.categories)}")
            print(f"   {sp.paper.abs_url}")
        print("\n" + "=" * 80)
