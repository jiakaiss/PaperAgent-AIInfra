"""Tests for paper browsing: filtering, search, pagination, empty state, mode passthrough."""

import os
import tempfile
from datetime import datetime

import pytest
from starlette.testclient import TestClient

from paper_agent.config import AppConfig, StorageConfig
from paper_agent.models import Paper, ScoredPaper
from paper_agent.storage.database import PaperDatabase
from paper_agent.web.app import create_app


def _make_scored_paper(
    arxiv_id: str,
    title: str,
    tags: tuple[str, ...] = ("quantization",),
    relevance: float = 8.0,
    quality: float = 7.0,
) -> ScoredPaper:
    paper = Paper(
        arxiv_id=arxiv_id,
        title=title,
        authors=["Alice", "Bob", "Charlie", "Dave"],
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


def _seed_db(db: PaperDatabase) -> None:
    papers = [
        _make_scored_paper("2401.00001v1", "Quantization for LLMs", ("quantization",), 9.0, 8.0),
        _make_scored_paper("2401.00002v1", "Sparse Attention", ("sparsity", "kv_cache"), 7.0, 6.0),
        _make_scored_paper("2401.00003v1", "Mixture of Experts", ("moe",), 8.5, 7.5),
        _make_scored_paper("2401.00004v1", "FlashAttention Compiler", ("compiler",), 6.0, 9.0),
        _make_scored_paper(
            "2401.00005v1", "KV Cache Quantization", ("quantization", "kv_cache"), 8.0, 7.0
        ),
    ]
    # Add 30 more for pagination testing
    for i in range(6, 36):
        papers.append(
            _make_scored_paper(
                f"2401.{i:05d}v1",
                f"Paper Number {i}",
                ("quantization",),
                5.0,
                5.0,
            )
        )
    db.cache_papers(papers)


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    db = PaperDatabase(path)
    _seed_db(db)
    yield path
    os.unlink(path)


@pytest.fixture
def client(db_path):
    cfg = AppConfig(storage=StorageConfig(db_path=db_path))
    app = create_app(cfg)
    return TestClient(app)


# ── Sub-domain filter tests ──


def test_sub_domain_filter_single(client):
    resp = client.get("/_paper_list?sub_domain=moe")
    assert resp.status_code == 200
    assert "Mixture of Experts" in resp.text
    assert "Quantization for LLMs" not in resp.text


def test_sub_domain_filter_multiple(client):
    resp = client.get("/_paper_list?sub_domain=moe&sub_domain=sparsity")
    assert resp.status_code == 200
    assert "Mixture of Experts" in resp.text
    assert "Sparse Attention" in resp.text
    assert "Quantization for LLMs" not in resp.text


def test_sub_domain_unknown_ignored(client):
    resp = client.get("/_paper_list?sub_domain=not_a_real_tag")
    assert resp.status_code == 200
    # Unknown tag is ignored → all papers shown
    assert "Quantization for LLMs" in resp.text


# ── Search tests ──


def test_search_filter(client):
    resp = client.get("/_paper_list?q=flashattention")
    assert resp.status_code == 200
    assert "FlashAttention Compiler" in resp.text
    assert "Mixture of Experts" not in resp.text


def test_search_combined_with_sub_domain(client):
    resp = client.get("/_paper_list?sub_domain=quantization&q=kv")
    assert resp.status_code == 200
    assert "KV Cache Quantization" in resp.text
    assert "Quantization for LLMs" not in resp.text


# ── Pagination tests ──


def test_pagination_first_page(client):
    resp = client.get("/_paper_list?sub_domain=quantization")
    assert resp.status_code == 200
    assert "下一页" in resp.text


def test_pagination_middle_page(client):
    resp = client.get("/_paper_list?sub_domain=quantization&page=2")
    assert resp.status_code == 200
    assert "← 上一页" in resp.text
    assert "下一页" in resp.text


def test_pagination_clamps_past_last_page(client):
    resp = client.get("/_paper_list?sub_domain=quantization&page=999")
    assert resp.status_code == 200
    # Should show the last page, not error
    assert "Paper Number" in resp.text or "Quantization" in resp.text


def test_total_count_displayed(client):
    resp = client.get("/_paper_list?sub_domain=moe")
    assert resp.status_code == 200
    assert "共 1 篇论文" in resp.text


# ── Empty state tests ──


def test_empty_state_filter_no_match(client):
    resp = client.get("/_paper_list?sub_domain=pruning")
    assert resp.status_code == 200
    assert "没有匹配的论文" in resp.text


def test_empty_state_empty_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        cfg = AppConfig(storage=StorageConfig(db_path=path))
        app = create_app(cfg)
        tc = TestClient(app)
        resp = tc.get("/_paper_list")
        assert resp.status_code == 200
        assert "暂无论文" in resp.text
    finally:
        os.unlink(path)


# ── Mode passthrough tests ──


def test_mode_all_query_param(client):
    resp = client.get("/?mode=all")
    assert resp.status_code == 200
    assert "Paper Agent" in resp.text


def test_mode_custom_query_param(client):
    resp = client.get("/?mode=custom")
    assert resp.status_code == 200
    assert "Paper Agent" in resp.text


def test_mode_invalid_ignored(client):
    resp = client.get("/?mode=banana")
    assert resp.status_code == 200
    assert "Paper Agent" in resp.text


# ── Paper card content ──


def test_paper_card_shows_authors_et_al(client):
    resp = client.get("/_paper_list?q=Quantization for LLMs")
    assert resp.status_code == 200
    # 4 authors → first 3 + "et al."
    assert "et al." in resp.text


def test_paper_card_shows_scores(client):
    resp = client.get("/_paper_list?sub_domain=moe")
    assert resp.status_code == 200
    assert "R: 8.5" in resp.text
    assert "Q: 7.5" in resp.text


def test_paper_card_shows_tag_chips(client):
    resp = client.get("/_paper_list?sub_domain=moe")
    assert resp.status_code == 200
    assert "moe" in resp.text


# ── Time range filter tests ──


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


def test_time_range_filter_past_month():
    """GET /?since=1m returns only papers from the past month."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        db = PaperDatabase(path)
        now = datetime.now()
        papers = [
            _make_scored_paper_with_date(
                "2401.00001v1", "Old Paper", datetime(2020, 1, 1), ("quantization",)
            ),
            _make_scored_paper_with_date(
                "2401.00002v1",
                "Recent Paper",
                datetime(now.year, now.month, max(1, now.day - 5)),
                ("moe",),
            ),
        ]
        db.cache_papers(papers)

        cfg = AppConfig(storage=StorageConfig(db_path=path))
        app = create_app(cfg)
        tc = TestClient(app)

        resp = tc.get("/_paper_list?since=1m")
        assert resp.status_code == 200
        assert "Recent Paper" in resp.text
        assert "Old Paper" not in resp.text
    finally:
        os.unlink(path)


def test_time_range_invalid_ignored():
    """GET /?since=invalid ignores the filter and shows all papers."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        db = PaperDatabase(path)
        papers = [
            _make_scored_paper_with_date("2401.00001v1", "Old Paper", datetime(2020, 1, 1)),
            _make_scored_paper_with_date("2401.00002v1", "Recent Paper", datetime(2024, 6, 1)),
        ]
        db.cache_papers(papers)

        cfg = AppConfig(storage=StorageConfig(db_path=path))
        app = create_app(cfg)
        tc = TestClient(app)

        resp = tc.get("/_paper_list?since=invalid")
        assert resp.status_code == 200
        # Both papers should be shown since invalid filter is ignored
        assert "Old Paper" in resp.text
        assert "Recent Paper" in resp.text
    finally:
        os.unlink(path)


def test_time_range_combined_with_sub_domain():
    """GET /?since=6m&sub_domain=quantization combines filters with AND logic."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        db = PaperDatabase(path)
        now = datetime.now()
        papers = [
            _make_scored_paper_with_date(
                "2401.00001v1", "Old Quantization", datetime(2020, 1, 1), ("quantization",)
            ),
            _make_scored_paper_with_date(
                "2401.00002v1", "Recent MoE", datetime(now.year, now.month, 1), ("moe",)
            ),
            _make_scored_paper_with_date(
                "2401.00003v1",
                "Recent Quantization",
                datetime(now.year, now.month, 2),
                ("quantization",),
            ),
        ]
        db.cache_papers(papers)

        cfg = AppConfig(storage=StorageConfig(db_path=path))
        app = create_app(cfg)
        tc = TestClient(app)

        resp = tc.get("/_paper_list?since=6m&sub_domain=quantization")
        assert resp.status_code == 200
        assert "Recent Quantization" in resp.text
        assert "Old Quantization" not in resp.text
        assert "Recent MoE" not in resp.text
    finally:
        os.unlink(path)


def test_time_range_combined_with_search():
    """GET /?since=1y&q=attention combines time range and search with AND logic."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        db = PaperDatabase(path)
        now = datetime.now()
        papers = [
            _make_scored_paper_with_date(
                "2401.00001v1", "Old Attention", datetime(2020, 1, 1), ("quantization",)
            ),
            _make_scored_paper_with_date(
                "2401.00002v1", "Recent MoE", datetime(now.year, now.month, 1), ("moe",)
            ),
            _make_scored_paper_with_date(
                "2401.00003v1",
                "Recent Attention",
                datetime(now.year, now.month, 2),
                ("quantization",),
            ),
        ]
        db.cache_papers(papers)

        cfg = AppConfig(storage=StorageConfig(db_path=path))
        app = create_app(cfg)
        tc = TestClient(app)

        resp = tc.get("/_paper_list?since=1y&q=attention")
        assert resp.status_code == 200
        assert "Recent Attention" in resp.text
        assert "Old Attention" not in resp.text
        assert "Recent MoE" not in resp.text
    finally:
        os.unlink(path)


def test_quality_filter_hides_low_quality_papers():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        db = PaperDatabase(path)
        db.cache_papers([
            _make_scored_paper("2401.10001v1", "High Quality", quality=8.0),
            _make_scored_paper("2401.10002v1", "Low Quality", quality=3.0),
        ])
        cfg = AppConfig(storage=StorageConfig(db_path=path))
        app = create_app(cfg)
        tc = TestClient(app)

        resp = tc.get("/_paper_list")
        assert resp.status_code == 200
        assert "High Quality" in resp.text
        assert "Low Quality" not in resp.text
    finally:
        os.unlink(path)


def test_quality_filter_disabled_shows_low_quality_papers():
    from paper_agent.config import WebConfig

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        db = PaperDatabase(path)
        db.cache_papers([
            _make_scored_paper("2401.10001v1", "High Quality", quality=8.0),
            _make_scored_paper("2401.10002v1", "Low Quality", quality=3.0),
        ])
        cfg = AppConfig(storage=StorageConfig(db_path=path), web=WebConfig(min_quality=0))
        app = create_app(cfg)
        tc = TestClient(app)

        resp = tc.get("/_paper_list")
        assert resp.status_code == 200
        assert "High Quality" in resp.text
        assert "Low Quality" in resp.text
    finally:
        os.unlink(path)


def test_quality_filter_combines_with_sub_domain_and_search():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        db = PaperDatabase(path)
        db.cache_papers([
            _make_scored_paper(
                "2401.10001v1",
                "LLM Quantization High",
                ("quantization",),
                quality=8.0,
            ),
            _make_scored_paper(
                "2401.10002v1",
                "LLM Quantization Low",
                ("quantization",),
                quality=3.0,
            ),
            _make_scored_paper("2401.10003v1", "LLM MoE High", ("moe",), quality=8.0),
        ])
        cfg = AppConfig(storage=StorageConfig(db_path=path))
        app = create_app(cfg)
        tc = TestClient(app)

        resp = tc.get("/_paper_list?sub_domain=quantization&q=llm")
        assert resp.status_code == 200
        assert "LLM Quantization High" in resp.text
        assert "LLM Quantization Low" not in resp.text
        assert "LLM MoE High" not in resp.text
        assert "共 1 篇论文" in resp.text
    finally:
        os.unlink(path)
