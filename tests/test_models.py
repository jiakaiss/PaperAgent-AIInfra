"""Tests for data models."""

from datetime import datetime

from paper_agent.models import (
    SUB_DOMAINS,
    Paper,
    ScoredPaper,
    ScoreWeights,
    compute_total_score,
    get_all_sub_domain_keywords,
    sort_by_score,
)


def _make_paper(arxiv_id: str = "2401.00001v1") -> Paper:
    return Paper(
        arxiv_id=arxiv_id,
        title="Test Paper",
        authors=["Alice", "Bob"],
        abstract="A test abstract about distributed training.",
        published=datetime(2024, 1, 15),
        categories=["cs.DC", "cs.LG"],
        pdf_url="https://arxiv.org/pdf/2401.00001v1",
        abs_url="https://arxiv.org/abs/2401.00001v1",
    )


def test_paper_primary_category():
    p = _make_paper()
    assert p.primary_category == "cs.DC"


def test_scored_paper_total_score():
    p = _make_paper()
    sp = ScoredPaper(
        paper=p,
        relevance_score=8.0,
        quality_score=7.0,
        summary_zh="测试论文",
        sub_domain_tags=("quantization", "pruning"),
    )
    # 0.6 * 8 + 0.4 * 7 = 4.8 + 2.8 = 7.6
    assert sp.total_score == 7.6


def test_scored_paper_sub_domain_display():
    p = _make_paper()
    sp = ScoredPaper(
        paper=p,
        relevance_score=8.0,
        quality_score=7.0,
        summary_zh="测试",
        sub_domain_tags=("quantization", "sparsity"),
    )
    assert sp.sub_domain_display == "quantization, sparsity"


def test_scored_paper_no_tags():
    p = _make_paper()
    sp = ScoredPaper(paper=p, relevance_score=8.0, quality_score=7.0, summary_zh="测试")
    assert sp.sub_domain_tags == ()
    assert sp.sub_domain_display == "general"


def test_sort_by_score():
    papers = [
        ScoredPaper(paper=_make_paper("1"), relevance_score=5.0, quality_score=5.0, summary_zh="a"),
        ScoredPaper(paper=_make_paper("2"), relevance_score=9.0, quality_score=9.0, summary_zh="b"),
        ScoredPaper(paper=_make_paper("3"), relevance_score=7.0, quality_score=6.0, summary_zh="c"),
    ]
    sorted_papers = sort_by_score(papers)
    assert sorted_papers[0].paper.arxiv_id == "2"
    assert sorted_papers[1].paper.arxiv_id == "3"
    assert sorted_papers[2].paper.arxiv_id == "1"


def test_sub_domains_taxonomy():
    """Verify SUB_DOMAINS has expected structure."""
    assert "quantization" in SUB_DOMAINS
    assert "distillation" in SUB_DOMAINS
    assert "pruning" in SUB_DOMAINS
    assert "sparsity" in SUB_DOMAINS
    assert isinstance(SUB_DOMAINS["quantization"], list)
    assert len(SUB_DOMAINS["quantization"]) > 0


def test_get_all_sub_domain_keywords():
    keywords = get_all_sub_domain_keywords()
    assert isinstance(keywords, list)
    assert len(keywords) > 50  # Should have many keywords across all sub-domains
    assert "quantization" in keywords


def test_paper_frozen():
    p = _make_paper()
    try:
        p.title = "new"
        assert False, "Should raise FrozenInstanceError"
    except Exception:
        pass


# ─── ScoreWeights tests ───


def test_score_weights_defaults():
    w = ScoreWeights()
    assert w.relevance == 0.6
    assert w.quality == 0.4


def test_score_weights_custom():
    w = ScoreWeights(relevance=0.8, quality=0.2)
    assert w.relevance == 0.8
    assert w.quality == 0.2


def test_score_weights_from_scoring_config():
    from paper_agent.config import ScoringConfig

    cfg = ScoringConfig(relevance_weight=0.7, quality_weight=0.3)
    w = ScoreWeights.from_scoring_config(cfg)
    assert w.relevance == 0.7
    assert w.quality == 0.3


def test_compute_total_score():
    p = _make_paper()
    sp = ScoredPaper(
        paper=p,
        relevance_score=8.0,
        quality_score=6.0,
        summary_zh="test",
    )
    # 8*0.8 + 6*0.2 = 6.4 + 1.2 = 7.6
    assert abs(compute_total_score(sp, ScoreWeights(0.8, 0.2)) - 7.6) < 1e-9


def test_compute_total_score_default_weights_match_property():
    """compute_total_score with default weights equals ScoredPaper.total_score."""
    p = _make_paper()
    sp = ScoredPaper(
        paper=p,
        relevance_score=8.0,
        quality_score=7.0,
        summary_zh="test",
    )
    assert compute_total_score(sp, ScoreWeights()) == sp.total_score


def test_sort_by_score_with_custom_weights():
    papers = [
        ScoredPaper(
            paper=_make_paper("1"),
            relevance_score=10.0,
            quality_score=2.0,
            summary_zh="a",
        ),
        ScoredPaper(
            paper=_make_paper("2"),
            relevance_score=5.0,
            quality_score=10.0,
            summary_zh="b",
        ),
    ]
    # With relevance-only weights, paper 1 (rel=10) should come first
    sorted_papers = sort_by_score(papers, ScoreWeights(1.0, 0.0))
    assert sorted_papers[0].paper.arxiv_id == "1"

    # With quality-only weights, paper 2 (qual=10) should come first
    sorted_papers = sort_by_score(papers, ScoreWeights(0.0, 1.0))
    assert sorted_papers[0].paper.arxiv_id == "2"


def test_sort_by_score_no_weights_uses_defaults():
    """Backward compat: sort_by_score without weights uses ScoredPaper.total_score."""
    papers = [
        ScoredPaper(paper=_make_paper("1"), relevance_score=5.0, quality_score=5.0, summary_zh="a"),
        ScoredPaper(paper=_make_paper("2"), relevance_score=9.0, quality_score=9.0, summary_zh="b"),
    ]
    sorted_papers = sort_by_score(papers)
    assert sorted_papers[0].paper.arxiv_id == "2"
