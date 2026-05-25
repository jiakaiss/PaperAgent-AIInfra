"""arXiv paper fetcher."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import arxiv

from paper_agent.models import Paper

logger = logging.getLogger(__name__)


class ArxivFetcher:
    """Fetches papers from arXiv API."""

    def __init__(
        self,
        categories: list[str] | None = None,
        keywords: list[str] | None = None,
    ):
        self.categories = categories or ["cs.DC", "cs.LG", "cs.AI", "cs.PF"]
        self.keywords = keywords or []

    def _build_query(self) -> str:
        """Build arXiv search query combining categories and keywords."""
        cat_query = " OR ".join(f"cat:{cat}" for cat in self.categories)

        if self.keywords:
            kw_query = " OR ".join(f'all:"{kw}"' for kw in self.keywords)
            # Papers in target categories OR keyword matches in any category
            return f"({cat_query}) OR ({kw_query})"

        return cat_query

    def fetch(self, max_results: int = 200, days_back: int = 2) -> list[Paper]:
        """Fetch recent papers from arXiv."""
        query = self._build_query()
        cutoff = datetime.now().astimezone() - timedelta(days=days_back)

        logger.info(f"Searching arXiv: query={query!r}, max_results={max_results}")

        client = arxiv.Client(
            page_size=100,
            delay_seconds=3.0,
            num_retries=3,
        )

        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )

        papers: list[Paper] = []
        for result in client.results(search):
            # Filter by date
            if result.published < cutoff:
                continue

            paper = Paper(
                arxiv_id=result.entry_id.split("/abs/")[-1],
                title=result.title.strip().replace("\n", " "),
                authors=[a.name for a in result.authors],
                abstract=result.summary.strip().replace("\n", " "),
                published=result.published,
                categories=[c for c in result.categories],
                pdf_url=result.pdf_url,
                abs_url=result.entry_id,
            )
            papers.append(paper)

        logger.info(f"Fetched {len(papers)} papers from arXiv (last {days_back} days)")
        return papers
