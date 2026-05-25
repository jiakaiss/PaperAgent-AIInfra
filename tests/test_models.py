"""Tests for data models."""

from datetime import datetime

from paper_agent.models import Paper, ScoredPaper, sort_by_score


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
    sp = ScoredPaper(paper=p, relevance_score=8.0, quality_score=7.0, summary_zh="测试论文")
    # 0.6 * 8 + 0.4 * 7 = 4.8 + 2.8 = 7.6
    assert sp.total_score == 7.6


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


def test_paper_frozen():
    p = _make_paper()
    try:
        p.title = "new"
        assert False, "Should raise FrozenInstanceError"
    except Exception:
        pass
