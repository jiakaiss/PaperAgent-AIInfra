"""arXiv paper fetcher with multi-query support."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

import arxiv

from paper_agent.models import Paper

logger = logging.getLogger(__name__)


class ArxivFetcher:
    """Fetches papers from arXiv API.

    Uses multiple targeted queries instead of one giant OR query
    to avoid arXiv rate limiting (HTTP 429).
    """

    def __init__(
        self,
        categories: list[str] | None = None,
        keywords: list[str] | None = None,
    ):
        self.categories = categories or ["cs.DC", "cs.LG", "cs.AI", "cs.PF"]
        self.keywords = keywords or []

    def _build_queries(self) -> list[str]:
        """Build a list of targeted queries instead of one giant OR.

        Strategy:
        - Query 1: category-based (broad)
        - Query 2-N: keyword-based, grouped in small batches
        """
        queries = []

        # Category query: only use specific AI-infra categories (not cs.LG/cs.AI which are too broad)
        infra_categories = [c for c in self.categories if c in ("cs.DC", "cs.PF", "cs.NI", "cs.AR")]
        if infra_categories:
            cat_query = " OR ".join(f"cat:{cat}" for cat in infra_categories)
            queries.append(("categories", cat_query))

        # Keyword queries: split into groups of ~8 keywords each
        if self.keywords:
            group_size = 8
            for i in range(0, len(self.keywords), group_size):
                group = self.keywords[i : i + group_size]
                kw_query = " OR ".join(f'all:"{kw}"' for kw in group)
                queries.append((f"keywords_{i//group_size}", kw_query))

        return queries

    def _fetch_query(
        self, query: str, max_results: int, cutoff: datetime
    ) -> list[Paper]:
        """Fetch papers for a single query."""
        client = arxiv.Client(
            page_size=100,
            delay_seconds=5.0,
            num_retries=5,
        )

        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )

        papers: list[Paper] = []
        try:
            for result in client.results(search):
                if result.published < cutoff:
                    continue

                paper = Paper(
                    arxiv_id=result.entry_id.split("/abs/")[-1],
                    title=result.title.strip().replace("\n", " "),
                    authors=[a.name for a in result.authors],
                    abstract=result.summary.strip().replace("\n", " "),
                    published=result.published,
                    categories=list(result.categories),
                    pdf_url=result.pdf_url,
                    abs_url=result.entry_id,
                )
                papers.append(paper)
        except arxiv.HTTPError as e:
            logger.warning(f"arXiv HTTP error: {e}")
        except Exception as e:
            logger.warning(f"arXiv fetch error: {e}")

        return papers

    def fetch(self, max_results: int = 200, days_back: int = 2) -> list[Paper]:
        """Fetch recent papers from arXiv using multiple targeted queries."""
        cutoff = datetime.now().astimezone() - timedelta(days=days_back)
        queries = self._build_queries()

        logger.info(f"Searching arXiv with {len(queries)} queries (last {days_back} days)")

        # Collect papers from all queries, dedup by arxiv_id
        seen_ids: set[str] = set()
        all_papers: list[Paper] = []

        per_query_limit = max_results // max(len(queries), 1)

        for name, query in queries:
            logger.debug(f"  Query [{name}]: {query[:120]}...")
            papers = self._fetch_query(query, per_query_limit, cutoff)

            new_count = 0
            for p in papers:
                if p.arxiv_id not in seen_ids:
                    seen_ids.add(p.arxiv_id)
                    all_papers.append(p)
                    new_count += 1

            logger.info(f"  [{name}] got {len(papers)} papers, {new_count} new")

            # Delay between queries to avoid rate limiting
            time.sleep(3.0)

        # Sort by published date (newest first)
        all_papers.sort(key=lambda p: p.published, reverse=True)

        logger.info(f"Total: {len(all_papers)} unique papers from arXiv")
        return all_papers
