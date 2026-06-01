"""Tests for PaperDatabase web query methods: list_papers, count_papers, get_sub_domain_counts."""

import os
import tempfile
from datetime import datetime

from paper_agent.models import Paper, ScoredPaper
from paper_agent.storage.database import PaperDatabase


def _make_scored_paper(
    arxiv_id: str = "2401.00001v1",
    title: str = "Test Paper",
    tags: tuple[str, ...] = ("quantization",),
    relevance: float = 8.0,
    quality: float = 7.0,
) -> ScoredPaper:
    paper = Paper(
        arxiv_id=arxiv_id,
        title=title,
        authors=["Alice", "Bob"],
        abstract="Test abstract",
        published=datetime(2024, 1, 15),
        categories=["cs.DC"],
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        abs_url=f"https://arxiv.org/abs/{arxiv_id}",
    )
    return ScoredPaper(
        paper=paper,
        relevance_score=relevance,
        quality_score=quality,
        summary_zh="测试论文",
        sub_domain_tags=tags,
    )


def _seed_db(db: PaperDatabase) -> list[ScoredPaper]:
    """Insert a handful of papers with different tags and scores."""
    papers = [
        _make_scored_paper("2401.00001v1", "Quantization for LLMs", ("quantization",), 9.0, 8.0),
        _make_scored_paper(
            "2401.00002v1",
            "Sparse Attention Patterns",
            ("sparsity", "kv_cache"),
            7.0,
            6.0,
        ),
        _make_scored_paper("2401.00003v1", "Mixture of Experts Routing", ("moe",), 8.5, 7.5),
        _make_scored_paper(
            "2401.00004v1",
            "FlashAttention and Compiler Optimizations",
            ("compiler", "memory_optimization"),
            6.0,
            9.0,
        ),
        _make_scored_paper(
            "2401.00005v1", "KV Cache Quantization", ("quantization", "kv_cache"), 8.0, 7.0
        ),
    ]
    db.cache_papers(papers)
    return papers


def test_list_papers_no_filter_returns_all_sorted():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = PaperDatabase(db_path)
        _seed_db(db)

        papers = db.list_papers(limit=10)
        assert len(papers) == 5
        # Highest total score first: 2401.00001v1 (9*0.6+8*0.4=8.6)
        assert papers[0].paper.arxiv_id == "2401.00001v1"
        # Verify descending order
        scores = [p.total_score for p in papers]
        assert scores == sorted(scores, reverse=True)
    finally:
        os.unlink(db_path)


def test_list_papers_sub_domain_filter():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = PaperDatabase(db_path)
        _seed_db(db)

        papers = db.list_papers(sub_domains={"quantization"}, limit=10)
        assert len(papers) == 2
        ids = {p.paper.arxiv_id for p in papers}
        assert ids == {"2401.00001v1", "2401.00005v1"}
    finally:
        os.unlink(db_path)


def test_list_papers_sub_domain_multi_tag_union():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = PaperDatabase(db_path)
        _seed_db(db)

        # moe OR quantization
        papers = db.list_papers(sub_domains={"moe", "quantization"}, limit=10)
        ids = {p.paper.arxiv_id for p in papers}
        assert ids == {"2401.00001v1", "2401.00003v1", "2401.00005v1"}
    finally:
        os.unlink(db_path)


def test_list_papers_search_filter():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = PaperDatabase(db_path)
        _seed_db(db)

        papers = db.list_papers(search="flashattention", limit=10)
        assert len(papers) == 1
        assert papers[0].paper.arxiv_id == "2401.00004v1"
    finally:
        os.unlink(db_path)


def test_list_papers_search_case_insensitive():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = PaperDatabase(db_path)
        _seed_db(db)

        papers = db.list_papers(search="QUANTIZATION", limit=10)
        ids = {p.paper.arxiv_id for p in papers}
        assert ids == {"2401.00001v1", "2401.00005v1"}
    finally:
        os.unlink(db_path)


def test_list_papers_combined_filter():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = PaperDatabase(db_path)
        _seed_db(db)

        # sub_domain=quantization AND title contains "kv"
        papers = db.list_papers(sub_domains={"quantization"}, search="kv", limit=10)
        assert len(papers) == 1
        assert papers[0].paper.arxiv_id == "2401.00005v1"
    finally:
        os.unlink(db_path)


def test_list_papers_pagination():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = PaperDatabase(db_path)
        _seed_db(db)

        page1 = db.list_papers(limit=2, offset=0)
        page2 = db.list_papers(limit=2, offset=2)
        page3 = db.list_papers(limit=2, offset=4)

        assert len(page1) == 2
        assert len(page2) == 2
        assert len(page3) == 1

        # No overlap
        all_ids = [p.paper.arxiv_id for p in page1 + page2 + page3]
        assert len(all_ids) == len(set(all_ids))
    finally:
        os.unlink(db_path)


def test_count_papers_no_filter():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = PaperDatabase(db_path)
        _seed_db(db)
        assert db.count_papers() == 5
    finally:
        os.unlink(db_path)


def test_count_papers_with_filter():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = PaperDatabase(db_path)
        _seed_db(db)

        assert db.count_papers(sub_domains={"quantization"}) == 2
        assert db.count_papers(sub_domains={"moe"}) == 1
        assert db.count_papers(search="attention") == 2
        assert db.count_papers(sub_domains={"quantization"}, search="kv") == 1
        assert db.count_papers(sub_domains={"pruning"}) == 0
    finally:
        os.unlink(db_path)


def test_count_matches_list_across_pagination():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = PaperDatabase(db_path)
        _seed_db(db)

        total = db.count_papers(sub_domains={"quantization"})
        collected = []
        offset = 0
        while offset < total:
            page = db.list_papers(sub_domains={"quantization"}, limit=2, offset=offset)
            collected.extend(page)
            offset += 2
        assert len(collected) == total
    finally:
        os.unlink(db_path)


def test_get_sub_domain_counts():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = PaperDatabase(db_path)
        _seed_db(db)

        counts = db.get_sub_domain_counts()
        # quantization: 00001, 00005
        assert counts["quantization"] == 2
        # sparsity: 00002
        assert counts["sparsity"] == 1
        # kv_cache: 00002, 00005
        assert counts["kv_cache"] == 2
        # moe: 00003
        assert counts["moe"] == 1
        # compiler: 00004
        assert counts["compiler"] == 1
        # memory_optimization: 00004
        assert counts["memory_optimization"] == 1
        # Tags with no papers
        assert counts["pruning"] == 0
        assert counts["distillation"] == 0
    finally:
        os.unlink(db_path)


def test_get_sub_domain_counts_empty_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = PaperDatabase(db_path)
        counts = db.get_sub_domain_counts()
        # All 14 sub-domains present, all zero
        assert all(v == 0 for v in counts.values())
        assert len(counts) == 14
    finally:
        os.unlink(db_path)


def _make_scored_paper_with_date(
    arxiv_id: str,
    title: str,
    published: datetime,
    tags: tuple[str, ...] = ("quantization",),
) -> ScoredPaper:
    """Helper to create a ScoredPaper with a specific publication date."""
    paper = Paper(
        arxiv_id=arxiv_id,
        title=title,
        authors=["Alice"],
        abstract="Test abstract",
        published=published,
        categories=["cs.DC"],
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        abs_url=f"https://arxiv.org/abs/{arxiv_id}",
    )
    return ScoredPaper(
        paper=paper,
        relevance_score=8.0,
        quality_score=7.0,
        summary_zh="测试论文",
        sub_domain_tags=tags,
    )


def test_list_papers_published_after_filter():
    """Time range filter returns only papers published on or after the given date."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = PaperDatabase(db_path)
        papers = [
            _make_scored_paper_with_date("2401.00001v1", "Old Paper", datetime(2023, 6, 1)),
            _make_scored_paper_with_date("2401.00002v1", "Mid Paper", datetime(2024, 1, 15)),
            _make_scored_paper_with_date("2401.00003v1", "Recent Paper", datetime(2024, 6, 1)),
        ]
        db.cache_papers(papers)

        # Filter to papers from 2024-01-01 onwards
        result = db.list_papers(published_after="2024-01-01", limit=10)
        assert len(result) == 2
        ids = {p.paper.arxiv_id for p in result}
        assert ids == {"2401.00002v1", "2401.00003v1"}
    finally:
        os.unlink(db_path)


def test_list_papers_published_after_combined_with_sub_domain():
    """Time range combines with sub-domain using AND logic."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = PaperDatabase(db_path)
        papers = [
            _make_scored_paper_with_date(
                "2401.00001v1", "Old Quantization", datetime(2023, 6, 1), ("quantization",)
            ),
            _make_scored_paper_with_date(
                "2401.00002v1", "Recent MoE", datetime(2024, 3, 1), ("moe",)
            ),
            _make_scored_paper_with_date(
                "2401.00003v1", "Recent Quantization", datetime(2024, 6, 1), ("quantization",)
            ),
        ]
        db.cache_papers(papers)

        # Filter: quantization AND published >= 2024-01-01
        result = db.list_papers(
            sub_domains={"quantization"}, published_after="2024-01-01", limit=10
        )
        assert len(result) == 1
        assert result[0].paper.arxiv_id == "2401.00003v1"
    finally:
        os.unlink(db_path)


def test_count_papers_published_after_matches_list():
    """count_papers with time range matches total from paginating list_papers."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = PaperDatabase(db_path)
        papers = [
            _make_scored_paper_with_date("2401.00001v1", "Paper 1", datetime(2023, 1, 1)),
            _make_scored_paper_with_date("2401.00002v1", "Paper 2", datetime(2023, 6, 1)),
            _make_scored_paper_with_date("2401.00003v1", "Paper 3", datetime(2024, 1, 1)),
            _make_scored_paper_with_date("2401.00004v1", "Paper 4", datetime(2024, 6, 1)),
            _make_scored_paper_with_date("2401.00005v1", "Paper 5", datetime(2024, 12, 1)),
        ]
        db.cache_papers(papers)

        # Filter to 2024 onwards
        total = db.count_papers(published_after="2024-01-01")
        assert total == 3

        # Paginate through all results
        collected = []
        offset = 0
        while offset < total:
            page = db.list_papers(published_after="2024-01-01", limit=2, offset=offset)
            collected.extend(page)
            offset += 2
        assert len(collected) == total
    finally:
        os.unlink(db_path)


def test_list_papers_published_after_combined_with_search():
    """Time range combines with search using AND logic."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = PaperDatabase(db_path)
        papers = [
            _make_scored_paper_with_date("2401.00001v1", "Old Attention", datetime(2023, 6, 1)),
            _make_scored_paper_with_date("2401.00002v1", "Recent MoE", datetime(2024, 3, 1)),
            _make_scored_paper_with_date("2401.00003v1", "Recent Attention", datetime(2024, 6, 1)),
        ]
        db.cache_papers(papers)

        # Filter: title contains "attention" AND published >= 2024-01-01
        result = db.list_papers(search="attention", published_after="2024-01-01", limit=10)
        assert len(result) == 1
        assert result[0].paper.arxiv_id == "2401.00003v1"
    finally:
        os.unlink(db_path)
