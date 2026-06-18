"""Tests for citation-aware ranking (sort_by_score + citation_component)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from paper_agent.models import (
    Paper,
    ScoredPaper,
    ScoreWeights,
    citation_component,
    compute_total_score,
    sort_by_score,
)


def _paper(arxiv_id: str = "p") -> Paper:
    return Paper(
        arxiv_id=arxiv_id,
        title="t",
        authors=[],
        abstract="",
        published=datetime(2024, 1, 1, tzinfo=UTC),
        categories=[],
        pdf_url="",
        abs_url="",
    )


def _sp(arxiv_id: str, *, rel=7.0, qual=6.0, tier="solid", citations=0) -> ScoredPaper:
    return ScoredPaper(
        paper=_paper(arxiv_id),
        relevance_score=rel,
        quality_score=qual,
        summary_zh="",
        impact_tier=tier,
        citation_count=citations,
    )


# ─── citation_component shape ───


def test_citation_component_zero_for_zero_count():
    assert citation_component(_sp("p", citations=0), ceiling=1000) == 0.0


def test_citation_component_at_ceiling_is_ten():
    """citation_count == ceiling → ~10/10."""
    assert citation_component(_sp("p", citations=1000), ceiling=1000) == pytest.approx(10.0)


def test_citation_component_monotonic():
    a = citation_component(_sp("a", citations=10), ceiling=1000)
    b = citation_component(_sp("b", citations=100), ceiling=1000)
    c = citation_component(_sp("c", citations=1000), ceiling=1000)
    assert 0 < a < b < c


def test_citation_component_equal_for_equal_counts():
    """Two papers with same citations → same component (no zero penalty between peers)."""
    a = citation_component(_sp("a", citations=0), ceiling=1000)
    b = citation_component(_sp("b", citations=0), ceiling=1000)
    assert a == b


def test_citation_component_handles_zero_ceiling():
    """Defensive: avoid log(1) division by zero."""
    assert citation_component(_sp("p", citations=100), ceiling=0) == 0.0


# ─── sort_by_score: backward-compat by default ───


def test_zero_citation_weight_preserves_old_order():
    """Default weights → ranking identical to pre-change behavior."""
    p_high_cit = _sp("a", rel=7.0, qual=6.0, citations=5000)
    p_low_cit = _sp("b", rel=7.0, qual=6.0, citations=0)
    weights = ScoreWeights()  # citation=0.0

    ordered = sort_by_score([p_high_cit, p_low_cit], weights=weights)
    # Equal tier+score → original input order preserved (Python sorted is stable)
    assert [s.paper.arxiv_id for s in ordered] == ["a", "b"]


def test_sort_without_weights_skips_citation_key():
    """Calling sort_by_score with weights=None never sorts by citations."""
    p_high = _sp("a", rel=7.0, qual=6.0, citations=5000)
    p_low = _sp("b", rel=7.0, qual=6.0, citations=0)

    ordered = sort_by_score([p_low, p_high])  # no weights at all
    assert [s.paper.arxiv_id for s in ordered] == ["b", "a"]


def test_sort_with_weights_but_no_ceiling_skips_citation_key():
    """citation_weight>0 alone is not enough — need citation_ceiling too."""
    p_high = _sp("a", rel=7.0, qual=6.0, citations=5000)
    p_low = _sp("b", rel=7.0, qual=6.0, citations=0)
    weights = ScoreWeights(citation=0.3)

    ordered = sort_by_score([p_low, p_high], weights=weights)  # no ceiling
    assert [s.paper.arxiv_id for s in ordered] == ["b", "a"]  # original order


# ─── citation tiebreaker activates correctly ───


def test_higher_citations_win_equal_tier_equal_score_tie():
    p_high = _sp("a", rel=7.0, qual=6.0, citations=200, tier="solid")
    p_low = _sp("b", rel=7.0, qual=6.0, citations=5, tier="solid")
    weights = ScoreWeights(relevance=0.5, quality=0.3, citation=0.2)

    ordered = sort_by_score([p_low, p_high], weights=weights, citation_ceiling=1000)
    assert [s.paper.arxiv_id for s in ordered] == ["a", "b"]


def test_tier_dominates_citation():
    """A breakthrough with 0 citations still outranks a solid with 5000."""
    breakthrough = _sp("bt", rel=7.0, qual=6.0, citations=0, tier="breakthrough")
    solid_high_cit = _sp("solid", rel=9.0, qual=9.0, citations=5000, tier="solid")
    weights = ScoreWeights(citation=0.5)

    ordered = sort_by_score([solid_high_cit, breakthrough], weights=weights, citation_ceiling=1000)
    assert [s.paper.arxiv_id for s in ordered] == ["bt", "solid"]


def test_score_dominates_citation_within_tier():
    """Within a tier, total_score still beats citation count."""
    high_score_low_cit = _sp("hs", rel=9.0, qual=9.0, citations=0)
    low_score_high_cit = _sp("hc", rel=4.0, qual=4.0, citations=5000)
    weights = ScoreWeights(citation=0.3)

    ordered = sort_by_score(
        [low_score_high_cit, high_score_low_cit], weights=weights, citation_ceiling=1000
    )
    # hs has total_score 5.4, hc has 4.0 → hs wins despite 0 citations
    assert [s.paper.arxiv_id for s in ordered] == ["hs", "hc"]


def test_brand_new_paper_not_penalized_below_equal_citation_peer():
    """Two 0-citation papers with equal score must not be reordered by citation."""
    a = _sp("a", rel=7.0, qual=6.0, citations=0)
    b = _sp("b", rel=7.0, qual=6.0, citations=0)
    weights = ScoreWeights(citation=0.5)

    # Both citation_components are 0 → tertiary key tied → input order kept
    ordered = sort_by_score([a, b], weights=weights, citation_ceiling=1000)
    assert [s.paper.arxiv_id for s in ordered] == ["a", "b"]


# ─── compute_total_score has no citation term ───


def test_compute_total_score_ignores_citation_count():
    """Citation must NEVER appear in the total_score formula."""
    p_no_cit = _sp("a", rel=8.0, qual=6.0, citations=0)
    p_high_cit = _sp("b", rel=8.0, qual=6.0, citations=5000)
    weights = ScoreWeights(relevance=0.5, quality=0.3, citation=0.2)

    # Despite citation=0.2 weight, total_score is just relevance*0.5 + quality*0.3
    expected = 8.0 * 0.5 + 6.0 * 0.3
    assert compute_total_score(p_no_cit, weights) == pytest.approx(expected)
    assert compute_total_score(p_high_cit, weights) == pytest.approx(expected)
