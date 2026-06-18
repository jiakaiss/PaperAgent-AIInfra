"""Older-works discovery via Semantic Scholar's paper-search endpoint.

The arXiv API can't filter or sort by citation count, so the older-works
track sources its candidates from S2 instead. We then map each result back
to a :class:`Paper` (skipping anything without an arXiv ID, since the cache
is arXiv-keyed) and let the existing pipeline score + cache them.

This module is HTTP-bound but never crashes the caller — like the citation
provider, it logs and returns an empty list on any failure.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

import requests

from paper_agent.models import SUB_DOMAINS, Paper

if TYPE_CHECKING:
    from paper_agent.config import CitationsConfig, ThresholdsConfig

logger = logging.getLogger(__name__)


_S2_SEARCH_PATH = "/paper/search"
_S2_FIELDS = ",".join(
    [
        "paperId",
        "title",
        "abstract",
        "authors",
        "year",
        "externalIds",
        "citationCount",
        "openAccessPdf",
    ]
)


def _s2_to_paper(entry: dict) -> Paper | None:
    """Convert a Semantic Scholar search result to a :class:`Paper`.

    Returns ``None`` if the entry has no arXiv ID — those papers can't be
    stored in the arXiv-keyed cache, so they're silently skipped.
    """
    external = entry.get("externalIds") or {}
    arxiv_id = external.get("ArXiv") if isinstance(external, dict) else None
    if not arxiv_id:
        return None

    title = (entry.get("title") or "").strip()
    if not title:
        return None
    abstract = entry.get("abstract") or ""
    if not abstract:
        # Without an abstract, the LLM scorer can't do its job. Skip rather
        # than ship a low-information row to Claude.
        return None

    authors_raw = entry.get("authors") or []
    authors = [a.get("name", "") for a in authors_raw if isinstance(a, dict)]

    year = entry.get("year")
    # S2 only gives us a year. Synthesize a sortable ISO datetime — Jan 1 of
    # the year. Downstream consumers only use it for "older than X" filters.
    if isinstance(year, int):
        published = datetime(year, 1, 1)
    else:
        published = datetime(1900, 1, 1)

    return Paper(
        arxiv_id=arxiv_id,
        title=title,
        authors=authors,
        abstract=abstract,
        published=published,
        categories=["cs.LG"],  # S2 fieldOfStudy filter already pinned this
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        abs_url=f"https://arxiv.org/abs/{arxiv_id}",
    )


def _search_one_keyword(
    base_url: str,
    headers: dict,
    timeout: float,
    keyword: str,
    *,
    min_citations: int,
    year_min: int,
    year_max: int,
    page_size: int,
) -> list[tuple[Paper, int, int]]:
    """One S2 search call. Returns ``(paper, citation_count, influential_count)``.

    The citation counts ride along through the pipeline so we don't have
    to re-query S2 batch later just to learn what we already know — that
    second round-trip used to silently drop counts to 0 when S2 batch was
    rate-limited mid-ingest.

    Filters: ``year_min <= year <= year_max`` and ``citationCount >=
    min_citations``. Sorted by citation count descending so the citation
    floor doesn't waste a page on low-citation noise.
    """
    url = f"{base_url}{_S2_SEARCH_PATH}"
    params = {
        "query": keyword,
        "fields": _S2_FIELDS,
        "fieldsOfStudy": "Computer Science",
        # S2 range syntax: "YYYY-YYYY" includes both endpoints.
        "year": f"{year_min}-{year_max}",
        # Sort by citations descending so the citation floor doesn't waste
        # a page on low-citation noise.
        "sort": "citationCount:desc",
        "limit": page_size,
    }
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    except requests.RequestException as e:
        logger.warning("S2 search failed for keyword=%r: %s", keyword, e)
        return []

    if resp.status_code != 200:
        logger.warning(
            "S2 search HTTP %s for keyword=%r (body: %s)",
            resp.status_code,
            keyword,
            resp.text[:200],
        )
        return []

    try:
        data = resp.json()
    except ValueError:
        logger.warning("S2 search returned invalid JSON for keyword=%r", keyword)
        return []

    out: list[tuple[Paper, int, int]] = []
    for entry in data.get("data") or []:
        cc = int(entry.get("citationCount") or 0)
        if cc < min_citations:
            continue
        paper = _s2_to_paper(entry)
        if paper is not None:
            ic = int(entry.get("influentialCitationCount") or 0)
            out.append((paper, cc, ic))
    return out


def discover_older_works(
    citations_config: CitationsConfig,
    thresholds: ThresholdsConfig,
    sub_domains: list[str] | None = None,
) -> tuple[list[Paper], dict[str, str], dict[str, tuple[int, int]]]:
    """Find highly-cited older papers across the configured sub-domains.

    Returns ``(candidates, source_map, citation_map)`` where:

    - ``candidates`` — deduped list of :class:`Paper`
    - ``source_map`` — ``{arxiv_id: sub_domain}`` capturing which
      sub-domain's search surfaced each paper. Caller forces the
      originating sub-domain into ``sub_domain_tags`` after scoring,
      so a paper found via "quantization" but tagged "compiler" by the
      LLM still appears in quantization subscribers' digests.
    - ``citation_map`` — ``{arxiv_id: (citation_count, influential)}``
      from the same search response. Carrying these forward avoids a
      second S2 round-trip; that re-query was racy under rate-limit and
      silently produced 0-citation older works in production.

    For each sub-domain we issue up to
    ``citations.older_works_keywords_per_sub_domain`` queries (one per
    keyword variant from ``models.SUB_DOMAINS``), so synonyms like
    "speculative decoding" / "draft model" / "assisted generation" all
    contribute candidates. Results are sorted by citation count, so the
    most-cited classics are the first to land.

    Both age and citation thresholds come from config — no hardcoded
    literals, so operators can re-tune without code edits.
    """
    if not citations_config.enabled:
        return [], {}, {}
    if thresholds.older_works_per_digest <= 0:
        return [], {}, {}

    sd_list = sub_domains if sub_domains is not None else list(SUB_DOMAINS.keys())
    base_url = citations_config.base_url.rstrip("/")
    headers = {"Accept": "application/json"}
    if citations_config.api_key:
        headers["x-api-key"] = citations_config.api_key

    current_year = datetime.now().year
    # The window is defined relative to today: a paper qualifies as "older
    # work" when it's at least min_age_years old, but no more than
    # max_age_years old. The latter exists so 1990s/2000s papers (e.g.
    # MapReduce, Dryad) don't hijack the digest with classics that aren't
    # relevant to today's AI Infra reader.
    year_max = current_year - citations_config.older_works_min_age_years
    year_min = current_year - citations_config.older_works_max_age_years
    n_kw = citations_config.older_works_keywords_per_sub_domain

    logger.info(
        "Older-works discovery: %d sub-domain(s), year %d-%d, "
        "min_citations=%d, %d keyword(s)/sub-domain",
        len(sd_list),
        year_min,
        year_max,
        thresholds.min_citations_for_older_works,
        n_kw,
    )

    seen: set[str] = set()
    out: list[Paper] = []
    source_map: dict[str, str] = {}
    citation_map: dict[str, tuple[int, int]] = {}
    for sd in sd_list:
        # Build the keyword list for this sub-domain: prefer the rich
        # synonym list from models.SUB_DOMAINS (e.g. quantization →
        # ["quantization", "PTQ", "QAT", "INT8", "GPTQ", ...]), capped at
        # n_kw entries. Fall back to the bare sd name if SUB_DOMAINS doesn't
        # know about this key (e.g. a custom sub-domain passed by tests).
        variants = SUB_DOMAINS.get(sd) or [sd.replace("_", " ")]
        for keyword in variants[:n_kw]:
            results = _search_one_keyword(
                base_url,
                headers,
                citations_config.request_timeout,
                keyword,
                min_citations=thresholds.min_citations_for_older_works,
                year_min=year_min,
                year_max=year_max,
                page_size=citations_config.older_works_search_page_size,
            )
            for paper, cc, ic in results:
                if paper.arxiv_id in seen:
                    continue
                seen.add(paper.arxiv_id)
                out.append(paper)
                # Stamp the source sub-domain on first sighting so later
                # tagging can guarantee the paper appears in this domain's
                # subscribers' digests, even if Claude tags it differently.
                source_map[paper.arxiv_id] = sd
                # Carry citation counts forward so the pipeline doesn't
                # need a second S2 round-trip (which was racy under
                # rate-limit and silently zeroed counts in production).
                citation_map[paper.arxiv_id] = (cc, ic)

    logger.info(
        "Older-works discovery: %d unique candidate(s) before cache-dedup",
        len(out),
    )
    return out, source_map, citation_map
