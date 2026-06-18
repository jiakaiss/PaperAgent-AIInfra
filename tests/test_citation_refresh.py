"""Tests for citation refresh + dynamic re-scoring."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from paper_agent.citation_refresh import (
    refresh_and_rescore,
    refresh_citations,
    rescore_dynamic,
)
from paper_agent.config import CitationsConfig
from paper_agent.models import Paper, ScoredPaper
from paper_agent.scorer.citation_provider import CitationInfo
from paper_agent.storage.database import PaperDatabase


@pytest.fixture
def db():
    """Fresh on-disk DB per test (mirrors how WAL behaves in production)."""
    with tempfile.TemporaryDirectory() as tmp:
        yield PaperDatabase(Path(tmp) / "test.db")


def _paper(arxiv_id: str = "2401.00001") -> Paper:
    return Paper(
        arxiv_id=arxiv_id,
        title=f"Title {arxiv_id}",
        authors=["Alice"],
        abstract="abstract " * 20,
        published=datetime(2024, 1, 1, tzinfo=UTC),
        categories=["cs.LG"],
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        abs_url=f"https://arxiv.org/abs/{arxiv_id}",
    )


def _scored(arxiv_id: str = "2401.00001", **overrides) -> ScoredPaper:
    defaults = dict(
        relevance_score=7.0,
        quality_score=6.0,
        summary_zh="测试",
        sub_domain_tags=("quantization",),
        impact_tier="solid",
        citation_count=0,
    )
    defaults.update(overrides)
    return ScoredPaper(paper=_paper(arxiv_id), **defaults)


def _stub_provider(payload: dict[str, CitationInfo]):
    p = MagicMock()
    p.get_citations.return_value = payload
    return p


# ─── refresh_citations ───


def test_refresh_updates_only_stale_rows(db):
    """Just-fetched rows should be skipped at threshold > 0."""
    db.cache_papers([_scored("2401.00001", citation_count=10)])
    db.update_citations([("2401.00001", 50, 5)])  # mark as just-refreshed

    provider = _stub_provider({"2401.00001": CitationInfo(999, 99)})
    config = CitationsConfig(enabled=True, refresh_interval_hours=24)

    n = refresh_citations(db, provider, config)
    assert n == 0
    provider.get_citations.assert_not_called()


def test_refresh_picks_up_never_fetched_rows(db):
    """NULL citations_updated_at always counts as stale."""
    db.cache_papers([_scored("2401.00001")])  # citation_count=0, never refreshed

    provider = _stub_provider({"2401.00001": CitationInfo(120, 8)})
    config = CitationsConfig(enabled=True)

    n = refresh_citations(db, provider, config)
    assert n == 1
    sp = db.load_cached_papers(["2401.00001"])[0]
    assert sp.citation_count == 120
    assert sp.influential_citation_count == 8
    assert sp.citations_updated_at is not None


def test_refresh_all_flag_ignores_freshness(db):
    """--all forces refresh of even just-fetched rows."""
    db.cache_papers([_scored("2401.00001")])
    db.update_citations([("2401.00001", 50, 5)])

    provider = _stub_provider({"2401.00001": CitationInfo(200, 20)})
    config = CitationsConfig(enabled=True)

    n = refresh_citations(db, provider, config, force_all=True)
    assert n == 1


def test_refresh_caps_at_candidate_limit(db):
    """refresh_candidate_limit is the hard cap per tick."""
    for i in range(5):
        db.cache_papers([_scored(f"2401.{i:05d}")])

    provider = _stub_provider({})
    config = CitationsConfig(enabled=True, refresh_candidate_limit=3)

    refresh_citations(db, provider, config)
    asked = provider.get_citations.call_args.args[0]
    assert len(asked) == 3


def test_refresh_resumable_after_interruption(db):
    """Stale set shrinks naturally — re-running picks up the rest."""
    for i in range(5):
        db.cache_papers([_scored(f"2401.{i:05d}")])

    # First run: only refresh 2 of 5
    provider1 = _stub_provider(
        {
            "2401.00000": CitationInfo(10, 1),
            "2401.00001": CitationInfo(20, 2),
        }
    )
    config = CitationsConfig(enabled=True, refresh_candidate_limit=2)
    refresh_citations(db, provider1, config)

    # Second run: the 3 untouched rows should be the new candidates
    provider2 = _stub_provider({})
    refresh_citations(db, provider2, config)
    asked = provider2.get_citations.call_args.args[0]
    assert "2401.00000" not in asked
    assert "2401.00001" not in asked
    assert len(asked) == 2  # capped at refresh_candidate_limit


# ─── rescore_dynamic ───


def _scorer_returning(arxiv_id: str, **fields) -> MagicMock:
    """Build a stub scorer whose .score() returns a re-scored paper."""
    scorer = MagicMock()
    new_scored = _scored(arxiv_id, **fields)
    scorer.score.return_value = [new_scored]
    return scorer


def test_rescore_disabled_when_max_per_run_zero(db):
    db.cache_papers([_scored("2401.00001", citation_count=200)])
    db.update_citations([("2401.00001", 500, 50)])  # huge growth

    scorer = MagicMock()
    config = CitationsConfig(enabled=True, rescore_max_per_run=0)

    n = rescore_dynamic(db, scorer, config)
    assert n == 0
    scorer.score.assert_not_called()


def test_rescore_disabled_when_citations_disabled(db):
    db.cache_papers([_scored("2401.00001", citation_count=200)])
    db.update_citations([("2401.00001", 500, 50)])

    scorer = MagicMock()
    config = CitationsConfig(enabled=False)

    n = rescore_dynamic(db, scorer, config)
    assert n == 0
    scorer.score.assert_not_called()


def test_rescore_skips_small_growth(db):
    db.cache_papers([_scored("2401.00001", citation_count=100)])
    db.update_citations([("2401.00001", 110, 10)])  # delta=10, ratio=0.1

    scorer = MagicMock()
    config = CitationsConfig(
        enabled=True,
        rescore_min_delta=50,
        rescore_min_ratio=0.2,
        rescore_min_interval_days=0,
    )
    n = rescore_dynamic(db, scorer, config)
    assert n == 0


def test_rescore_triggers_on_growth_and_preserves_citations(db):
    """The merge step must keep the freshly-fetched citation_count alive."""
    sp_old = _scored(
        "2401.00001",
        relevance_score=6.0,
        quality_score=5.0,
        impact_tier="solid",
        citation_count=10,
    )
    db.cache_papers([sp_old])
    db.update_citations([("2401.00001", 350, 30)])  # huge growth

    # Scorer produces a "promoted" version — but with citation_count=0 (it
    # doesn't know about citations). The merge must restore them.
    scorer = _scorer_returning(
        "2401.00001",
        relevance_score=9.0,
        quality_score=8.0,
        impact_tier="breakthrough",
        citation_count=0,  # scorer returns default; should be overwritten
    )
    config = CitationsConfig(
        enabled=True,
        rescore_min_delta=50,
        rescore_max_per_run=10,
        rescore_min_interval_days=0,
    )

    n = rescore_dynamic(db, scorer, config)
    assert n == 1

    # The scorer was called with citation context.
    call = scorer.score.call_args
    assert call.kwargs["citation_context"] == {"2401.00001": (350, 30)}

    # Round-trip the row: tier promoted, score updated, citations preserved.
    sp = db.load_cached_papers(["2401.00001"])[0]
    assert sp.impact_tier == "breakthrough"
    assert sp.relevance_score == 9.0
    assert sp.citation_count == 350  # ★ NOT clobbered to 0
    assert sp.influential_citation_count == 30
    # Snapshot now equals current count → small future growth won't re-trigger.
    assert sp.citation_count_at_score == 350


def test_rescore_total_score_recomputed_from_new_relevance_quality(db):
    """total_score has no citation term — it just falls out of relevance/quality."""
    db.cache_papers([_scored("2401.00001", relevance_score=6.0, quality_score=5.0)])
    db.update_citations([("2401.00001", 1000, 100)])

    scorer = _scorer_returning(
        "2401.00001",
        relevance_score=9.0,
        quality_score=8.0,
    )
    config = CitationsConfig(enabled=True, rescore_max_per_run=10, rescore_min_interval_days=0)
    rescore_dynamic(db, scorer, config)

    sp = db.load_cached_papers(["2401.00001"])[0]
    # Default weights 0.6 / 0.4
    assert sp.total_score == pytest.approx(9.0 * 0.6 + 8.0 * 0.4)


def test_rescore_per_run_cap_picks_largest_growth_first(db):
    """When more candidates than the cap, biggest movers go first."""
    for i, growth in enumerate([20, 500, 100, 800]):
        aid = f"2401.0000{i}"
        db.cache_papers([_scored(aid, citation_count=10)])
        db.update_citations([(aid, 10 + growth, growth // 10)])

    config = CitationsConfig(
        enabled=True,
        rescore_min_delta=50,
        rescore_max_per_run=2,
        rescore_min_interval_days=0,
    )
    cands = db.get_rescore_candidates(
        config.rescore_min_delta,
        config.rescore_min_ratio,
        config.rescore_min_interval_days,
        config.rescore_max_per_run,
    )
    ids = [sp.paper.arxiv_id for sp in cands]
    # Top-2 by growth: 800 (idx 3), 500 (idx 1)
    assert ids == ["2401.00003", "2401.00001"]


# ─── auto-promotion: fresh → older when citations cross threshold ───


def test_rescore_promotes_aged_high_citation_paper_to_older(db):
    """A fresh paper old enough + cited enough flips to paper_kind='older'.

    This is the natural-emergence path: a 2-year-old paper that quietly
    accumulated citations beyond ``promote_min_citations`` is auto-tagged
    so the older-works section picks it up — without it, the older-works
    track only ever has manually-discovered classics.
    """
    from datetime import UTC, datetime, timedelta

    paper = Paper(
        arxiv_id="2401.99999",
        title="Quietly emerging classic",
        authors=["A"],
        abstract="abs",
        # Published 3 years ago — comfortably past the 2-year minimum age.
        published=datetime.now(UTC) - timedelta(days=365 * 3),
        categories=["cs.LG"],
        pdf_url="p",
        abs_url="a",
    )
    sp_old = ScoredPaper(
        paper=paper,
        relevance_score=7.0,
        quality_score=6.0,
        summary_zh="测试",
        sub_domain_tags=("kv_cache",),
        impact_tier="solid",
        citation_count=100,
        paper_kind="fresh",
    )
    db.cache_papers([sp_old])
    # Citations grew to 1000 — well past promote_min_citations=500.
    db.update_citations([("2401.99999", 1000, 80)])

    scorer = _scorer_returning(
        "2401.99999",
        relevance_score=8.0,
        quality_score=8.0,
        impact_tier="breakthrough",
    )
    config = CitationsConfig(
        enabled=True,
        rescore_min_delta=50,
        rescore_max_per_run=10,
        rescore_min_interval_days=0,
        older_works_promote_min_citations=500,
        older_works_min_age_years=2,
    )

    rescore_dynamic(db, scorer, config)

    sp = db.load_cached_papers(["2401.99999"])[0]
    assert sp.paper_kind == "older"
    assert sp.impact_tier == "breakthrough"
    assert sp.citation_count == 1000


def test_rescore_does_not_promote_too_young_paper(db):
    """High citations alone don't promote — paper must also be old enough."""
    from datetime import UTC, datetime, timedelta

    paper = Paper(
        arxiv_id="2606.00001",
        title="Fresh viral hit",
        authors=["A"],
        abstract="abs",
        # Only 6 months old.
        published=datetime.now(UTC) - timedelta(days=180),
        categories=["cs.LG"],
        pdf_url="p",
        abs_url="a",
    )
    sp_old = ScoredPaper(
        paper=paper,
        relevance_score=7.0,
        quality_score=6.0,
        summary_zh="测试",
        sub_domain_tags=("kv_cache",),
        impact_tier="solid",
        citation_count=100,
        paper_kind="fresh",
    )
    db.cache_papers([sp_old])
    db.update_citations([("2606.00001", 1000, 80)])  # citation way past threshold

    scorer = _scorer_returning(
        "2606.00001", relevance_score=9.0, quality_score=9.0, impact_tier="breakthrough"
    )
    config = CitationsConfig(
        enabled=True,
        rescore_min_delta=50,
        rescore_max_per_run=10,
        rescore_min_interval_days=0,
        older_works_promote_min_citations=500,
        older_works_min_age_years=2,
    )

    rescore_dynamic(db, scorer, config)

    sp = db.load_cached_papers(["2606.00001"])[0]
    # Citations triggered rescore, tier got promoted by Claude — but
    # paper_kind stays fresh because 6 months < 2 years.
    assert sp.paper_kind == "fresh"
    assert sp.impact_tier == "breakthrough"


def test_rescore_does_not_promote_already_older(db):
    """A paper that's already paper_kind='older' is left alone (idempotent)."""
    from datetime import UTC, datetime, timedelta

    paper = Paper(
        arxiv_id="2010.99999",
        title="Already classic",
        authors=["A"],
        abstract="abs",
        published=datetime.now(UTC) - timedelta(days=365 * 5),
        categories=["cs.LG"],
        pdf_url="p",
        abs_url="a",
    )
    db.cache_papers(
        [
            ScoredPaper(
                paper=paper,
                relevance_score=8.0,
                quality_score=8.0,
                summary_zh="测试",
                sub_domain_tags=("kv_cache",),
                impact_tier="breakthrough",
                citation_count=2000,
                paper_kind="older",  # already older
            )
        ]
    )
    db.update_citations([("2010.99999", 3000, 200)])

    scorer = _scorer_returning(
        "2010.99999", relevance_score=9.0, quality_score=9.0, impact_tier="breakthrough"
    )
    config = CitationsConfig(
        enabled=True,
        rescore_min_delta=50,
        rescore_max_per_run=10,
        rescore_min_interval_days=0,
        older_works_promote_min_citations=500,
        older_works_min_age_years=2,
    )

    rescore_dynamic(db, scorer, config)

    sp = db.load_cached_papers(["2010.99999"])[0]
    assert sp.paper_kind == "older"  # stayed older


# ─── refresh_and_rescore (the combined entrypoint) ───


def test_combined_flow_refreshes_then_rescores(db):
    sp_old = _scored("2401.00001", impact_tier="solid", citation_count=0)
    db.cache_papers([sp_old])

    provider = _stub_provider({"2401.00001": CitationInfo(500, 50)})
    scorer = _scorer_returning(
        "2401.00001",
        relevance_score=9.0,
        quality_score=8.0,
        impact_tier="breakthrough",
    )
    config = CitationsConfig(
        enabled=True,
        rescore_min_delta=50,
        rescore_max_per_run=10,
        rescore_min_interval_days=0,
    )

    result = refresh_and_rescore(db, provider, scorer, config)
    assert result.citations_updated == 1
    assert result.rescored == 1

    sp = db.load_cached_papers(["2401.00001"])[0]
    assert sp.citation_count == 500
    assert sp.impact_tier == "breakthrough"
