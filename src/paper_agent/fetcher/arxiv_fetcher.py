"""arXiv paper fetcher with multi-query support."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Literal

import arxiv

from paper_agent.models import Paper

logger = logging.getLogger(__name__)


class ArxivFetcher:
    """Fetches papers from arXiv API.

    Uses multiple targeted queries instead of one giant OR query
    to avoid arXiv rate limiting (HTTP 429).

    When ``quality_floor_strategy="per_keyword_cap"`` is enabled, runs the
    dual-track fetch described in the design doc:

    - Track 1 (keyword): one query per individual keyword, each capped at
      ``max(min_per_keyword, max_results // num_queries)`` so no single
      keyword can dominate the budget.
    - Track 2 (cross-list): one query per category in ``cross_list_categories``
      for recent papers. Catches papers whose terminology doesn't match any
      subscribed keyword.

    Both tracks deduplicate by ``arxiv_id``; Track-1 records are inserted
    first so they win on conflict (keyword provenance preserved for
    debugging).
    """

    def __init__(
        self,
        categories: list[str] | None = None,
        keywords: list[str] | None = None,
        *,
        quality_floor_strategy: Literal["none", "per_keyword_cap"] = "none",
        min_per_keyword: int = 10,
        cross_list_categories: list[str] | None = None,
    ):
        self.categories = categories or ["cs.DC", "cs.LG", "cs.AI", "cs.PF"]
        self.keywords = keywords or []
        self.quality_floor_strategy = quality_floor_strategy
        self.min_per_keyword = min_per_keyword
        self.cross_list_categories = cross_list_categories or []

    def _build_queries(self) -> list[tuple[str, str]]:
        """Build the Track-1 query list.

        Legacy mode (``quality_floor_strategy="none"``) groups keywords into
        batches of 8 sharing one ``max_results`` budget — the historical
        behavior, preserved for configs that haven't opted in.

        Dual-track mode (``quality_floor_strategy="per_keyword_cap"``) emits
        one query per individual keyword so the per-keyword cap is enforced
        per-keyword rather than per-batch.
        """
        queries: list[tuple[str, str]] = []

        # Category query: only use specific AI-infra categories
        # (not cs.LG/cs.AI which are too broad).
        infra_categories = [c for c in self.categories if c in ("cs.DC", "cs.PF", "cs.NI", "cs.AR")]
        if infra_categories:
            cat_query = " OR ".join(f"cat:{cat}" for cat in infra_categories)
            queries.append(("categories", cat_query))

        if not self.keywords:
            return queries

        if self.quality_floor_strategy == "per_keyword_cap":
            for kw in self.keywords:
                queries.append((f"kw:{kw}", f'all:"{kw}"'))
        else:
            group_size = 8
            for i in range(0, len(self.keywords), group_size):
                group = self.keywords[i : i + group_size]
                kw_query = " OR ".join(f'all:"{kw}"' for kw in group)
                queries.append((f"keywords_{i // group_size}", kw_query))

        return queries

    def _build_cross_list_queries(self) -> list[tuple[str, str]]:
        """Queries for Track 2 (recent papers per cross-list category)."""
        return [(f"cross:{cat}", f"cat:{cat}") for cat in self.cross_list_categories]

    def _per_query_limit(self, max_results: int, num_queries: int) -> int:
        """Compute the per-query result cap.

        In legacy mode this is the simple even split. In ``per_keyword_cap``
        mode we apply ``min_per_keyword`` as a floor so unlucky keywords with
        few hits don't propagate a tiny budget to the others.
        """
        even_split = max_results // max(num_queries, 1)
        if self.quality_floor_strategy == "per_keyword_cap":
            return max(self.min_per_keyword, even_split)
        return even_split

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

    def _run_queries(
        self,
        queries: list[tuple[str, str]],
        per_query_limit: int,
        cutoff: datetime,
        seen_ids: set[str],
        all_papers: list[Paper],
    ) -> None:
        """Issue each query in order, appending new (deduped) papers to ``all_papers``."""
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
            time.sleep(5.0)

    def fetch(self, max_results: int = 200, days_back: int = 2) -> list[Paper]:
        """Fetch recent papers from arXiv via Track 1 (and optionally Track 2)."""
        cutoff = datetime.now().astimezone() - timedelta(days=days_back)
        keyword_queries = self._build_queries()
        cross_list_queries = (
            self._build_cross_list_queries()
            if self.quality_floor_strategy == "per_keyword_cap"
            else []
        )

        total_queries = len(keyword_queries) + len(cross_list_queries)
        logger.info(
            f"Searching arXiv with {len(keyword_queries)} track-1 + "
            f"{len(cross_list_queries)} track-2 queries (last {days_back} days)"
        )

        seen_ids: set[str] = set()
        all_papers: list[Paper] = []
        per_query_limit = self._per_query_limit(max_results, total_queries)

        # Track 1 first so its records win on dedup against Track 2.
        self._run_queries(keyword_queries, per_query_limit, cutoff, seen_ids, all_papers)
        self._run_queries(cross_list_queries, per_query_limit, cutoff, seen_ids, all_papers)

        # Sort by published date (newest first)
        all_papers.sort(key=lambda p: p.published, reverse=True)

        logger.info(f"Total: {len(all_papers)} unique papers from arXiv")
        return all_papers
