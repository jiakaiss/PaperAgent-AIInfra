"""One-off backfill: inject classic AI Infra older works into the cache.

Why this exists: the older-works auto-discovery path uses Semantic Scholar's
``paper/search`` endpoint, which is heavily rate-limited for anonymous
clients. arXiv's API is also aggressive about rate-limiting bursts. So
this script bypasses both: it hand-picks a list of high-citation classics
and pulls their metadata + citation counts via the S2 ``paper/batch``
endpoint (which returns ``title``/``abstract``/``authors``/``year``
alongside ``citationCount`` and is NOT subject to the same rate limits).

Then it runs them through the existing scorer with citation context, so
Claude assigns a tier with the real-world impact evidence visible.

Safe to re-run: papers already in the cache are skipped.
"""

from __future__ import annotations

import logging
import sys
import time
from dataclasses import replace as _replace
from datetime import datetime

import requests

from paper_agent.config import load_config
from paper_agent.models import Paper, ScoredPaper
from paper_agent.scorer.claude_scorer import ClaudeScorer
from paper_agent.storage.database import PaperDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("seed_older_works")

CLASSIC_IDS: list[str] = [
    "2205.14135",  # FlashAttention
    "2307.08691",  # FlashAttention-2
    "2309.06180",  # vLLM / PagedAttention
    "2306.00978",  # AWQ
    "2210.17323",  # GPTQ
    "2208.07339",  # LLM.int8()
    "2305.14314",  # QLoRA
    "1909.08053",  # Megatron-LM
    "1910.02054",  # ZeRO
    "2401.04088",  # Mixtral 8x7B
    "2101.03961",  # Switch Transformer
    "2211.17192",  # Speculative decoding
    "2401.10774",  # Medusa
    "2106.09685",  # LoRA
]

_S2_FIELDS = (
    "externalIds,title,abstract,authors.name,year,"
    "citationCount,influentialCitationCount,openAccessPdf"
)


def fetch_s2_metadata(cfg, arxiv_ids: list[str]) -> dict[str, dict]:
    """Pull title/abstract/authors/year/citations for each arXiv ID via S2 batch.

    Returns a dict keyed by bare arXiv ID. Missing IDs are silently dropped.
    """
    url = f"{cfg.citations.base_url.rstrip('/')}/paper/batch"
    headers = {"Content-Type": "application/json"}
    if cfg.citations.api_key:
        headers["x-api-key"] = cfg.citations.api_key
    body = {"ids": [f"ArXiv:{aid}" for aid in arxiv_ids]}
    r = requests.post(
        url,
        params={"fields": _S2_FIELDS},
        json=body,
        headers=headers,
        timeout=cfg.citations.request_timeout,
    )
    if r.status_code != 200:
        logger.error("S2 batch HTTP %s: %s", r.status_code, r.text[:300])
        return {}
    data = r.json()
    if not isinstance(data, list):
        logger.error("S2 batch unexpected shape: %r", type(data))
        return {}

    out: dict[str, dict] = {}
    for i, entry in enumerate(data):
        if entry is None:
            logger.warning("S2 has no record for %s", arxiv_ids[i])
            continue
        ext = entry.get("externalIds") or {}
        aid = ext.get("ArXiv") if isinstance(ext, dict) else None
        if not aid:
            aid = arxiv_ids[i]
        out[aid] = entry
    return out


def s2_to_paper(arxiv_id: str, entry: dict) -> Paper | None:
    """Convert a S2 batch response entry to our :class:`Paper`."""
    title = (entry.get("title") or "").strip()
    abstract = (entry.get("abstract") or "").strip()
    if not title or not abstract:
        logger.warning("Skipping %s: missing title or abstract", arxiv_id)
        return None
    authors = [a.get("name", "") for a in (entry.get("authors") or []) if isinstance(a, dict)]
    year = entry.get("year") or 1970
    pdf = entry.get("openAccessPdf") or {}
    pdf_url = (pdf.get("url") if isinstance(pdf, dict) else None) or f"https://arxiv.org/pdf/{arxiv_id}"
    return Paper(
        arxiv_id=arxiv_id,  # bare; that becomes the cache PK for this seeding
        title=title,
        authors=authors,
        abstract=abstract,
        published=datetime(year, 1, 1),  # S2 only gives a year
        categories=["cs.LG"],  # best guess for AI Infra classics
        pdf_url=pdf_url,
        abs_url=f"https://arxiv.org/abs/{arxiv_id}",
    )


def main() -> int:
    cfg = load_config("config.yaml")
    if not cfg.citations.enabled:
        logger.error("citations.enabled=false; enable it before seeding older works.")
        return 1

    db = PaperDatabase(cfg.storage.db_path)
    scorer = ClaudeScorer(config=cfg.scoring)

    # Step 1: which classics aren't already in the cache?
    needed = []
    for aid in CLASSIC_IDS:
        # Cache PK may carry version suffix; check several common variants.
        if any(db.is_cached(aid + v) for v in ("", "v1", "v2", "v3", "v4")):
            continue
        needed.append(aid)
    logger.info(
        "Older-works seed: %d classics, %d to fetch",
        len(CLASSIC_IDS),
        len(needed),
    )
    if not needed:
        logger.info("Nothing to do.")
        return 0

    # Step 2: pull metadata + citations from S2 in one batch call.
    logger.info("Fetching metadata + citations from Semantic Scholar (1 batch)...")
    s2_data = fetch_s2_metadata(cfg, needed)
    logger.info("  → got %d/%d records", len(s2_data), len(needed))
    if not s2_data:
        logger.error("S2 returned nothing — aborting.")
        return 1

    # Step 3: convert to Paper + remember citations.
    papers: list[Paper] = []
    citations: dict[str, tuple[int, int]] = {}  # arxiv_id → (cit, infl)
    for aid in needed:
        entry = s2_data.get(aid)
        if entry is None:
            continue
        p = s2_to_paper(aid, entry)
        if p is None:
            continue
        papers.append(p)
        cc = int(entry.get("citationCount") or 0)
        ic = int(entry.get("influentialCitationCount") or 0)
        citations[aid] = (cc, ic)
        logger.info("  • %s — cit=%d infl=%d  %s", aid, cc, ic, p.title[:55])

    if not papers:
        logger.error("No usable papers after filtering — aborting.")
        return 1

    # Step 4: score with citation context. Claude sees the citation count
    # in the prompt and is more likely to assign breakthrough/solid.
    logger.info("Scoring %d papers with Claude (citation context attached)...", len(papers))
    scored = scorer.score(papers, citation_context=citations)
    if not scored:
        logger.error("Scorer returned 0 papers — aborting.")
        return 1
    logger.info("  → scored %d papers", len(scored))

    # Step 5: enrich with citation columns + paper_kind="older" before caching.
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S")
    enriched: list[ScoredPaper] = []
    for sp in scored:
        cc, ic = citations.get(sp.paper.arxiv_id, (0, 0))
        enriched.append(
            _replace(
                sp,
                citation_count=cc,
                influential_citation_count=ic,
                citations_updated_at=now_iso,
                paper_kind="older",
                citation_count_at_score=cc,
            )
        )

    # Step 6: write. cache_papers handles the all-22-column INSERT OR REPLACE.
    db.cache_papers(enriched)
    logger.info("✅ Cached %d older works.", len(enriched))

    # Summary: tier distribution + cite range, so the operator can see
    # whether Claude actually used the citation evidence.
    from collections import Counter

    tiers = Counter(sp.impact_tier for sp in enriched)
    logger.info("Tier distribution: %s", dict(tiers))
    return 0


if __name__ == "__main__":
    sys.exit(main())
