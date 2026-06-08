"""Tests for the dual-track fetcher logic (query building, cap math, dedup)."""

from datetime import UTC, datetime

from paper_agent.fetcher.arxiv_fetcher import ArxivFetcher
from paper_agent.models import Paper

# ─── Legacy mode (quality_floor_strategy="none") ───


def test_legacy_groups_keywords_in_batches_of_8():
    fetcher = ArxivFetcher(
        keywords=[f"kw{i}" for i in range(20)],
        quality_floor_strategy="none",
    )
    queries = fetcher._build_queries()
    # categories query + 3 keyword-group queries (8+8+4)
    kw_queries = [q for name, q in queries if name.startswith("keywords_")]
    assert len(kw_queries) == 3


def test_legacy_per_query_limit_is_even_split():
    fetcher = ArxivFetcher(quality_floor_strategy="none")
    # 4 queries, max_results=200 → 50 each
    assert fetcher._per_query_limit(200, 4) == 50


# ─── Dual-track mode (quality_floor_strategy="per_keyword_cap") ───


def test_per_keyword_cap_emits_one_query_per_keyword():
    fetcher = ArxivFetcher(
        keywords=["quantization", "distillation", "pruning"],
        quality_floor_strategy="per_keyword_cap",
    )
    queries = fetcher._build_queries()
    # 1 category query + 3 individual keyword queries
    kw_queries = [(n, q) for n, q in queries if n.startswith("kw:")]
    assert len(kw_queries) == 3
    names = [n for n, _ in kw_queries]
    assert "kw:quantization" in names
    assert "kw:distillation" in names
    assert "kw:pruning" in names


def test_per_keyword_cap_respects_min_per_keyword():
    """When max_results // num_queries < min_per_keyword, the floor wins."""
    fetcher = ArxivFetcher(
        quality_floor_strategy="per_keyword_cap",
        min_per_keyword=10,
    )
    # 200 // 30 = 6 < 10 → should return 10
    assert fetcher._per_query_limit(200, 30) == 10


def test_per_keyword_cap_even_split_when_above_floor():
    """When max_results // num_queries > min_per_keyword, even split wins."""
    fetcher = ArxivFetcher(
        quality_floor_strategy="per_keyword_cap",
        min_per_keyword=10,
    )
    # 200 // 2 = 100 > 10 → should return 100
    assert fetcher._per_query_limit(200, 2) == 100


def test_cross_list_queries_built_from_categories():
    fetcher = ArxivFetcher(
        quality_floor_strategy="per_keyword_cap",
        cross_list_categories=["cs.LG", "cs.DC"],
    )
    queries = fetcher._build_cross_list_queries()
    assert len(queries) == 2
    assert queries[0][0] == "cross:cs.LG"
    assert queries[1][0] == "cross:cs.DC"


def test_cross_list_queries_empty_when_no_categories():
    fetcher = ArxivFetcher(
        quality_floor_strategy="per_keyword_cap",
        cross_list_categories=[],
    )
    assert fetcher._build_cross_list_queries() == []


def test_cross_list_queries_not_built_in_legacy_mode():
    """In legacy mode, _build_cross_list_queries still works but fetch()
    won't call it (the strategy check gates it)."""
    fetcher = ArxivFetcher(
        quality_floor_strategy="none",
        cross_list_categories=["cs.LG"],
    )
    # The method itself still returns queries, but fetch() won't invoke it.
    assert fetcher._build_cross_list_queries() == [("cross:cs.LG", "cat:cs.LG")]


def test_dedup_keyword_wins_over_cross_list():
    """When the same arxiv_id appears in both tracks, the keyword-pass
    record (inserted first) wins. We verify the dedup algorithm directly
    without hitting the arXiv API.
    """
    seen_ids: set[str] = set()
    all_papers: list[Paper] = []

    # Simulate Track 1 adding its result first
    kw_paper = Paper(
        arxiv_id="2401.00001",
        title="From keyword",
        authors=["A"],
        abstract="abs",
        published=datetime(2024, 1, 15, tzinfo=UTC),
        categories=["cs.DC"],
        pdf_url="https://arxiv.org/pdf/2401.00001",
        abs_url="https://arxiv.org/abs/2401.00001",
    )
    seen_ids.add(kw_paper.arxiv_id)
    all_papers.append(kw_paper)

    # Track 2 tries to add a paper with the same ID → should be dropped
    cross_dup = Paper(
        arxiv_id="2401.00001",
        title="From cross-list (should be dropped)",
        authors=["B"],
        abstract="abs2",
        published=datetime(2024, 1, 15, tzinfo=UTC),
        categories=["cs.LG"],
        pdf_url="https://arxiv.org/pdf/2401.00001",
        abs_url="https://arxiv.org/abs/2401.00001",
    )
    cross_unique = Paper(
        arxiv_id="2401.00002",
        title="From cross-list (unique)",
        authors=["C"],
        abstract="abs3",
        published=datetime(2024, 1, 16, tzinfo=UTC),
        categories=["cs.LG"],
        pdf_url="https://arxiv.org/pdf/2401.00002",
        abs_url="https://arxiv.org/abs/2401.00002",
    )
    for p in [cross_dup, cross_unique]:
        if p.arxiv_id not in seen_ids:
            seen_ids.add(p.arxiv_id)
            all_papers.append(p)

    # kw_paper wins; only 2 unique papers total
    assert len(all_papers) == 2
    assert all_papers[0].title == "From keyword"
    assert all_papers[1].title == "From cross-list (unique)"
