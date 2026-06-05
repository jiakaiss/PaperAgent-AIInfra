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

    def _build_queries(self) -> list[tuple[str, str]]:
        """Build a list of targeted queries instead of one giant OR.

        Strategy:
        - Query 1: category-based (broad)
        - Query 2-N: keyword-based, grouped in small batches
        """
        queries: list[tuple[str, str]] = []

        # Category query: only use specific AI-infra categories
        # (not cs.LG/cs.AI which are too broad).
        infra_categories = [
            c for c in self.categories if c in ("cs.DC", "cs.PF", "cs.NI", "cs.AR")
        ]
        if infra_categories:
            cat_query = " OR ".join(f"cat:{cat}" for cat in infra_categories)
            queries.append(("categories", cat_query))

        # Keyword queries: split into groups of ~8 keywords each
        if self.keywords:
            group_size = 8
            for i in range(0, len(self.keywords), group_size):
                group = self.keywords[i : i + group_size]
                kw_query = " OR ".join(f'all:"{kw}"' for kw in group)
                queries.append((f"keywords_{i // group_size}", kw_query))

        return queries

    def _fetch_query(self, query: str, max_results: int, cutoff: datetime) -> list[Paper]:
        """Fetch papers for a single query with exponential backoff."""
        # Use main API endpoint (export.arxiv.org is deprecated and rate-limited more aggressively)
        client = arxiv.Client(
            page_size=100,
            delay_seconds=3.5,
            num_retries=3,
        )
        # Override the deprecated export endpoint with the main API
        client.query_url_format = "https://arxiv.org/api/query?{}"

        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )

        papers: list[Paper] = []
        max_attempts = 3

        for attempt in range(max_attempts):
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
                break  # Success, exit retry loop

            except arxiv.HTTPError as e:
                if "429" in str(e) and attempt < max_attempts - 1:
                    # Exponential backoff: 30s, 60s, 120s
                    wait_time = 30 * (2**attempt)
                    logger.warning(
                        f"arXiv rate limited, waiting {wait_time}s "
                        f"(attempt {attempt + 1}/{max_attempts})"
                    )
                    time.sleep(wait_time)
                else:
                    logger.warning(f"arXiv HTTP error: {e}")
                    break
            except Exception as e:
                logger.warning(f"arXiv fetch error: {e}")
                break

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

            # Delay between queries to stay under rate limit
            time.sleep(5.0)

        # Sort by published date (newest first)
        all_papers.sort(key=lambda p: p.published, reverse=True)

        logger.info(f"Total: {len(all_papers)} unique papers from arXiv")
        return all_papers
