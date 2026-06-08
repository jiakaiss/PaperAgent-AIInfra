"""Tests for data models."""

from datetime import datetime

from paper_agent.models import (
    IMPACT_TIERS,
    SUB_DOMAINS,
    Paper,
    ScoredPaper,
    ScoreWeights,
    compute_total_score,
    sort_by_score,
    tier_rank,
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


# ─── Impact tier tests ───


def test_impact_tiers_constant():
    """IMPACT_TIERS lists the three categorical tiers in descending priority."""
    assert IMPACT_TIERS == ("breakthrough", "solid", "incremental")


def test_tier_rank_known_tiers():
    assert tier_rank("breakthrough") == 0
    assert tier_rank("solid") == 1
    assert tier_rank("incremental") == 2


def test_tier_rank_unknown_falls_back_to_solid():
    """Unknown / empty / None values fall back to the default tier (solid)."""
    solid_rank = tier_rank("solid")
    assert tier_rank("amazing") == solid_rank
    assert tier_rank("") == solid_rank
    assert tier_rank(None) == solid_rank


def test_scored_paper_defaults_for_new_fields():
    """Legacy callers can omit the new fields; defaults populate them."""
    sp = ScoredPaper(
        paper=_make_paper(),
        relevance_score=8.0,
        quality_score=7.0,
        summary_zh="测试",
    )
    assert sp.key_contributions == ()
    assert sp.problem_statement_zh == ""
    assert sp.methods_zh == ""
    assert sp.impact_tier == "solid"


def test_scored_paper_accepts_structured_insights():
    sp = ScoredPaper(
        paper=_make_paper(),
        relevance_score=8.0,
        quality_score=7.0,
        summary_zh="测试",
        key_contributions=("贡献 1", "贡献 2"),
        problem_statement_zh="解决了某问题",
        methods_zh="使用了某方法",
        impact_tier="breakthrough",
    )
    assert sp.key_contributions == ("贡献 1", "贡献 2")
    assert sp.problem_statement_zh == "解决了某问题"
    assert sp.methods_zh == "使用了某方法"
    assert sp.impact_tier == "breakthrough"


def test_sort_by_score_breakthrough_outranks_higher_solid():
    """A breakthrough paper sorts before a higher-scoring solid paper."""
    breakthrough = ScoredPaper(
        paper=_make_paper("a"),
        relevance_score=7.0,
        quality_score=7.0,  # total = 7.0
        summary_zh="x",
        impact_tier="breakthrough",
    )
    higher_solid = ScoredPaper(
        paper=_make_paper("b"),
        relevance_score=9.0,
        quality_score=9.0,  # total = 9.0
        summary_zh="y",
        impact_tier="solid",
    )
    sorted_papers = sort_by_score([higher_solid, breakthrough])
    assert sorted_papers[0].paper.arxiv_id == "a"
    assert sorted_papers[1].paper.arxiv_id == "b"


def test_sort_by_score_same_tier_uses_score():
    """Within a tier, descending total_score wins."""
    low = ScoredPaper(
        paper=_make_paper("low"),
        relevance_score=6.0,
        quality_score=6.0,
        summary_zh="x",
        impact_tier="solid",
    )
    high = ScoredPaper(
        paper=_make_paper("high"),
        relevance_score=8.5,
        quality_score=8.5,
        summary_zh="y",
        impact_tier="solid",
    )
    sorted_papers = sort_by_score([low, high])
    assert sorted_papers[0].paper.arxiv_id == "high"
    assert sorted_papers[1].paper.arxiv_id == "low"


def test_sort_by_score_full_tier_ordering():
    """Mixed-tier list orders breakthrough → solid → incremental, then by score."""
    papers = [
        ScoredPaper(
            paper=_make_paper("inc-hi"),
            relevance_score=9.5,
            quality_score=9.5,
            summary_zh="x",
            impact_tier="incremental",
        ),
        ScoredPaper(
            paper=_make_paper("sol-lo"),
            relevance_score=5.0,
            quality_score=5.0,
            summary_zh="x",
            impact_tier="solid",
        ),
        ScoredPaper(
            paper=_make_paper("brk-lo"),
            relevance_score=4.0,
            quality_score=4.0,
            summary_zh="x",
            impact_tier="breakthrough",
        ),
        ScoredPaper(
            paper=_make_paper("sol-hi"),
            relevance_score=8.0,
            quality_score=8.0,
            summary_zh="x",
            impact_tier="solid",
        ),
    ]
    ordered = [p.paper.arxiv_id for p in sort_by_score(papers)]
    assert ordered == ["brk-lo", "sol-hi", "sol-lo", "inc-hi"]


def test_sort_by_score_unknown_tier_treated_as_solid():
    """A paper with an unknown impact_tier sorts as if it were solid."""
    unknown = ScoredPaper(
        paper=_make_paper("u"),
        relevance_score=9.0,
        quality_score=9.0,
        summary_zh="x",
        impact_tier="bogus",
    )
    incremental = ScoredPaper(
        paper=_make_paper("i"),
        relevance_score=10.0,
        quality_score=10.0,
        summary_zh="x",
        impact_tier="incremental",
    )
    sorted_papers = sort_by_score([incremental, unknown])
    # unknown is treated as solid → comes before incremental regardless of score
    assert sorted_papers[0].paper.arxiv_id == "u"
    assert sorted_papers[1].paper.arxiv_id == "i"
