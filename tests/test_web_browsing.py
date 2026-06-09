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
        db.cache_papers(
            [
                _make_scored_paper("2401.10001v1", "High Quality", quality=8.0),
                _make_scored_paper("2401.10002v1", "Low Quality", quality=3.0),
            ]
        )
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
        db.cache_papers(
            [
                _make_scored_paper("2401.10001v1", "High Quality", quality=8.0),
                _make_scored_paper("2401.10002v1", "Low Quality", quality=3.0),
            ]
        )
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
        db.cache_papers(
            [
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
            ]
        )
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


# ─── Tier filtering tests ───


def _make_tiered_paper(
    arxiv_id: str,
    title: str,
    impact_tier: str = "solid",
    tags: tuple[str, ...] = ("quantization",),
    relevance: float = 8.0,
    quality: float = 7.0,
) -> ScoredPaper:
    paper = Paper(
        arxiv_id=arxiv_id,
        title=title,
        authors=["Alice"],
        abstract="abs",
        published=datetime(2024, 1, 15),
        categories=["cs.DC"],
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        abs_url=f"https://arxiv.org/abs/{arxiv_id}",
    )
    return ScoredPaper(
        paper=paper,
        relevance_score=relevance,
        quality_score=quality,
        summary_zh="摘要",
        sub_domain_tags=tags,
        impact_tier=impact_tier,
    )


def test_tier_filter_breakthrough_only():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    try:
        db = PaperDatabase(path)
        db.cache_papers(
            [
                _make_tiered_paper("000", "Breakthrough Paper", impact_tier="breakthrough"),
                _make_tiered_paper("001", "Solid Paper", impact_tier="solid"),
                _make_tiered_paper("002", "Incremental Paper", impact_tier="incremental"),
            ]
        )
        cfg = AppConfig(storage=StorageConfig(db_path=path))
        app = create_app(cfg)
        tc = TestClient(app)

        resp = tc.get("/_paper_list?tier=breakthrough")
        assert resp.status_code == 200
        assert "Breakthrough Paper" in resp.text
        assert "Solid Paper" not in resp.text
        assert "Incremental Paper" not in resp.text
    finally:
        os.unlink(path)


def test_tier_filter_multiple_tiers():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    try:
        db = PaperDatabase(path)
        db.cache_papers(
            [
                _make_tiered_paper("000", "Breakthrough Paper", impact_tier="breakthrough"),
                _make_tiered_paper("001", "Solid Paper", impact_tier="solid"),
                _make_tiered_paper("002", "Incremental Paper", impact_tier="incremental"),
            ]
        )
        cfg = AppConfig(storage=StorageConfig(db_path=path))
        app = create_app(cfg)
        tc = TestClient(app)

        resp = tc.get("/_paper_list?tier=breakthrough&tier=solid")
        assert resp.status_code == 200
        assert "Breakthrough Paper" in resp.text
        assert "Solid Paper" in resp.text
        assert "Incremental Paper" not in resp.text
    finally:
        os.unlink(path)


def test_tier_default_excludes_incremental():
    """No ?tier= param defaults to breakthrough + solid."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    try:
        db = PaperDatabase(path)
        db.cache_papers(
            [
                _make_tiered_paper("000", "Breakthrough Paper", impact_tier="breakthrough"),
                _make_tiered_paper("001", "Solid Paper", impact_tier="solid"),
                _make_tiered_paper("002", "Incremental Paper", impact_tier="incremental"),
            ]
        )
        cfg = AppConfig(storage=StorageConfig(db_path=path))
        app = create_app(cfg)
        tc = TestClient(app)

        resp = tc.get("/_paper_list")
        assert resp.status_code == 200
        assert "Breakthrough Paper" in resp.text
        assert "Solid Paper" in resp.text
        assert "Incremental Paper" not in resp.text
    finally:
        os.unlink(path)


def test_tier_unknown_tier_ignored_uses_default():
    """Unknown ?tier= values fall back to DEFAULT_TIERS."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    try:
        db = PaperDatabase(path)
        db.cache_papers(
            [
                _make_tiered_paper("000", "Solid Paper", impact_tier="solid"),
                _make_tiered_paper("001", "Incremental Paper", impact_tier="incremental"),
            ]
        )
        cfg = AppConfig(storage=StorageConfig(db_path=path))
        app = create_app(cfg)
        tc = TestClient(app)

        resp = tc.get("/_paper_list?tier=legendary")
        assert resp.status_code == 200
        assert "Solid Paper" in resp.text
        assert "Incremental Paper" not in resp.text
    finally:
        os.unlink(path)


def test_tier_combined_with_sub_domain_and_search():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    try:
        db = PaperDatabase(path)
        db.cache_papers(
            [
                _make_tiered_paper(
                    "000",
                    "Breakthrough MoE",
                    impact_tier="breakthrough",
                    tags=("moe",),
                ),
                _make_tiered_paper(
                    "001",
                    "Solid MoE",
                    impact_tier="solid",
                    tags=("moe",),
                ),
                _make_tiered_paper(
                    "002",
                    "Solid Quantization",
                    impact_tier="solid",
                    tags=("quantization",),
                ),
            ]
        )
        cfg = AppConfig(storage=StorageConfig(db_path=path))
        app = create_app(cfg)
        tc = TestClient(app)

        # AND logic across sub_domain=moe and tier=breakthrough
        resp = tc.get("/_paper_list?sub_domain=moe&tier=breakthrough")
        assert resp.status_code == 200
        assert "Breakthrough MoE" in resp.text
        assert "Solid MoE" not in resp.text
        assert "Solid Quantization" not in resp.text
    finally:
        os.unlink(path)


def test_tier_legacy_paper_appears_under_default():
    """A paper scored before the upgrade (NULL impact_tier) counts as solid
    and appears on the default page."""
    import sqlite3

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    try:
        db = PaperDatabase(path)
        db.cache_papers([_make_tiered_paper("000", "Legacy Friendly", impact_tier="solid")])
        # Inject a legacy row with NULL impact_tier
        conn = sqlite3.connect(path)
        try:
            conn.execute(
                """
                INSERT INTO papers (arxiv_id, title, authors, abstract, published,
                  categories, pdf_url, abs_url, relevance_score, quality_score,
                  summary_zh, sub_domain_tags, scored_at)
                VALUES ('legacy-1', 'Legacy Paper', 'A', 'abs', '2024-01-01',
                        'cs.DC', 'p', 'a', 8.0, 7.0, 'sum', '[]', '2024-01-02')
                """
            )
            conn.commit()
        finally:
            conn.close()

        cfg = AppConfig(storage=StorageConfig(db_path=path))
        app = create_app(cfg)
        tc = TestClient(app)

        resp = tc.get("/_paper_list")
        assert resp.status_code == 200
        # Legacy paper with NULL impact_tier appears as solid on the default page
        assert "Legacy Paper" in resp.text
    finally:
        os.unlink(path)


def test_tier_badge_appears_in_card():
    """The tier badge HTML fragment renders for a breakthrough paper."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    try:
        db = PaperDatabase(path)
        db.cache_papers([_make_tiered_paper("000", "Great Paper", impact_tier="breakthrough")])
        cfg = AppConfig(storage=StorageConfig(db_path=path))
        app = create_app(cfg)
        tc = TestClient(app)

        resp = tc.get("/_paper_list?tier=breakthrough")
        assert resp.status_code == 200
        # Badge
        assert "tier-badge-breakthrough" in resp.text
        assert "重磅突破" in resp.text
        # Card class
        assert "tier-breakthrough" in resp.text
    finally:
        os.unlink(path)


def test_key_contributions_renders_when_present():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    try:
        db = PaperDatabase(path)
        sp = _make_tiered_paper("000", "Paper With Contributions", impact_tier="solid")
        # Override to add contributions
        db.cache_papers(
            [
                ScoredPaper(
                    paper=sp.paper,
                    relevance_score=sp.relevance_score,
                    quality_score=sp.quality_score,
                    summary_zh=sp.summary_zh,
                    sub_domain_tags=sp.sub_domain_tags,
                    key_contributions=("贡献 A", "贡献 B"),
                    problem_statement_zh="问题描述",
                    methods_zh="使用某某方法",
                    impact_tier="solid",
                )
            ]
        )
        cfg = AppConfig(storage=StorageConfig(db_path=path))
        app = create_app(cfg)
        tc = TestClient(app)

        resp = tc.get("/_paper_list")
        assert resp.status_code == 200
        assert "关键贡献" in resp.text
        assert "贡献 A" in resp.text
        assert "贡献 B" in resp.text
        assert "问题" in resp.text
        assert "方法" in resp.text
    finally:
        os.unlink(path)


def test_key_contributions_hidden_when_empty():
    """Legacy papers (empty key_contributions) don't show contribution section."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    try:
        db = PaperDatabase(path)
        db.cache_papers([_make_tiered_paper("000", "Old Paper", impact_tier="solid")])
        cfg = AppConfig(storage=StorageConfig(db_path=path))
        app = create_app(cfg)
        tc = TestClient(app)

        resp = tc.get("/_paper_list")
        assert resp.status_code == 200
        assert "Old Paper" in resp.text
        assert "关键贡献" not in resp.text
    finally:
        os.unlink(path)


# ── 偏好设置 button placement (relocated from header to chip-filter row) ──


def test_preferences_toggle_present_on_index(client):
    """The 偏好设置 button SHALL be rendered on the main page."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert 'id="preferences-toggle"' in resp.text


def test_preferences_toggle_inside_chip_filter_row(client):
    """The 偏好设置 toggle SHALL be co-located with 领域筛选 (not in the header).

    The toggle is implemented as a clickable variant of the 领域筛选 label itself
    (the same element renders both the label text and a gear icon), so we assert
    the toggle button contains the 领域筛选 text.
    """
    resp = client.get("/")
    body = resp.text
    # The toggle button is the chip-filter label. Find the button element and
    # check that its inner text includes 领域筛选.
    btn_pos = body.find('id="preferences-toggle"')
    assert btn_pos != -1
    # Find the closing </button> after the toggle; the inner text must contain 领域筛选.
    btn_close = body.find("</button>", btn_pos)
    assert btn_close != -1
    btn_html = body[btn_pos:btn_close]
    assert "领域筛选" in btn_html, (
        "preferences-toggle should contain 领域筛选 text — it IS the label"
    )


def test_preferences_toggle_absent_on_subscribe(client):
    """No dead button on pages without the preferences panel."""
    resp = client.get("/subscribe")
    assert resp.status_code == 200
    assert 'id="preferences-toggle"' not in resp.text
