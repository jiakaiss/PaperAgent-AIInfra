"""Tests for older-works delivery in the digest path."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from paper_agent.config import (
    AppConfig,
    CitationsConfig,
    FetchConfig,
    ScheduleConfig,
    ScoringConfig,
    StorageConfig,
    SubscriptionConfig,
    ThresholdsConfig,
    UserConfig,
    UserNotifyConfig,
    UserThresholdsConfig,
)
from paper_agent.formatter.templates import format_email_html
from paper_agent.models import Paper, ScoredPaper
from paper_agent.pipeline import Pipeline


def _paper(arxiv_id: str) -> Paper:
    return Paper(
        arxiv_id=arxiv_id,
        title=f"Title {arxiv_id}",
        authors=["Alice"],
        abstract="abstract",
        published=datetime(2024, 1, 1, tzinfo=UTC),
        categories=["cs.LG"],
        pdf_url=f"p/{arxiv_id}",
        abs_url=f"a/{arxiv_id}",
    )


def _sp(
    arxiv_id: str,
    *,
    rel=8.0,
    qual=7.0,
    tier="solid",
    citations=0,
    paper_kind="fresh",
    tags=("quantization",),
) -> ScoredPaper:
    return ScoredPaper(
        paper=_paper(arxiv_id),
        relevance_score=rel,
        quality_score=qual,
        summary_zh="测试",
        sub_domain_tags=tags,
        impact_tier=tier,
        citation_count=citations,
        paper_kind=paper_kind,
    )


# ─── format_email_html splits by paper_kind ───


def test_email_renders_separate_older_section():
    """Older papers go in their own section, after the tier groups."""
    fresh = _sp("2401.001", paper_kind="fresh", tier="solid")
    older = _sp("2201.001", paper_kind="older", tier="breakthrough", citations=2000)

    html = format_email_html([fresh, older])

    assert "重要老作" in html
    assert "Important Older Works" in html
    # Fresh paper's title appears, older paper's title appears
    assert "Title 2401.001" in html
    assert "Title 2201.001" in html
    # The older section appears AFTER the tier-section markers — verify
    # ordering by checking position in the string.
    older_pos = html.index("重要老作")
    fresh_title_pos = html.index("Title 2401.001")
    assert fresh_title_pos < older_pos


def test_email_no_older_section_when_no_older_papers():
    """No older papers → no older section header."""
    fresh = _sp("2401.001", paper_kind="fresh")
    html = format_email_html([fresh])
    assert "重要老作" not in html


def test_email_citation_badge_only_when_count_positive():
    fresh_zero = _sp("a", citations=0)
    html = format_email_html([fresh_zero])
    assert "📈" not in html

    fresh_with = _sp("b", citations=120)
    html = format_email_html([fresh_with])
    assert "📈 120 citations" in html


# ─── pipeline _run_for_user picks older works additively ───


def _make_pipeline(
    *,
    cached_papers: list[ScoredPaper],
    citations_enabled: bool = True,
    older_per_digest: int = 2,
) -> tuple[Pipeline, str]:
    """Build a pipeline backed by a real on-disk DB with seeded papers."""
    tmp = tempfile.mkdtemp()
    db_path = str(Path(tmp) / "test.db")

    cfg = AppConfig(
        fetch=FetchConfig(max_results=10, days_back=3),
        scoring=ScoringConfig(batch_size=5),
        thresholds=ThresholdsConfig(
            min_relevance=6.0,
            min_quality=5.0,
            top_n=5,
            older_works_per_digest=older_per_digest,
            min_citations_for_older_works=100,
        ),
        citations=CitationsConfig(enabled=citations_enabled),
        users=[
            UserConfig(
                user_id="alice",
                subscriptions=SubscriptionConfig(sub_domains=["quantization"]),
                notify=UserNotifyConfig(),
                thresholds=UserThresholdsConfig(
                    min_relevance=6.0,
                    min_quality=5.0,
                    top_n=5,
                    older_works_per_digest=older_per_digest,
                ),
            )
        ],
        schedule=ScheduleConfig(enabled=False),
        storage=StorageConfig(db_path=db_path),
    )

    with patch("paper_agent.pipeline.ArxivFetcher"), patch("paper_agent.pipeline.ClaudeScorer"):
        pipeline = Pipeline(cfg)

    pipeline.db.cache_papers(cached_papers)
    return pipeline, db_path


def test_older_works_additive_to_top_n():
    """top_n=2, older_per_digest=2 → user gets up to 4 papers (2 + 2)."""
    fresh_papers = [_sp(f"2401.00{i}", paper_kind="fresh") for i in range(5)]
    older_papers = [_sp(f"2201.00{i}", paper_kind="older", citations=1000) for i in range(3)]
    pipeline, _ = _make_pipeline(cached_papers=fresh_papers + older_papers, older_per_digest=2)
    pipeline.config.users[0].thresholds.top_n = 2
    # Stub a notifier that just records what it sees
    seen: list[ScoredPaper] = []
    fake_notifier = MagicMock()
    fake_notifier.name = "fake"

    def _capture(papers):
        seen.extend(papers)
        return True

    fake_notifier.notify.side_effect = _capture
    pipeline.user_notifiers["alice"] = [fake_notifier]

    pipeline._run_for_user(
        pipeline.config.users[0],
        all_scored=fresh_papers + older_papers,
        dry_run=False,
    )

    fresh_count = sum(1 for sp in seen if sp.paper_kind == "fresh")
    older_count = sum(1 for sp in seen if sp.paper_kind == "older")
    assert fresh_count == 2  # respects top_n=2
    assert older_count == 2  # additive, capped at older_works_per_digest


def test_older_works_disabled_when_count_zero():
    """older_works_per_digest=0 → no older papers in digest."""
    fresh_papers = [_sp(f"2401.00{i}", paper_kind="fresh") for i in range(3)]
    older_papers = [_sp(f"2201.00{i}", paper_kind="older", citations=1000) for i in range(3)]
    pipeline, _ = _make_pipeline(cached_papers=fresh_papers + older_papers, older_per_digest=0)
    pipeline.config.users[0].thresholds.older_works_per_digest = 0

    seen: list[ScoredPaper] = []
    fake = MagicMock()
    fake.name = "fake"
    fake.notify.side_effect = lambda papers: (seen.extend(papers), True)[1]
    pipeline.user_notifiers["alice"] = [fake]

    pipeline._run_for_user(
        pipeline.config.users[0],
        all_scored=fresh_papers + older_papers,
        dry_run=False,
    )

    assert all(sp.paper_kind == "fresh" for sp in seen)


def test_older_works_disabled_when_citations_off():
    """citations.enabled=false → no older works in digest even if cached."""
    fresh_papers = [_sp(f"2401.00{i}", paper_kind="fresh") for i in range(3)]
    older_papers = [_sp(f"2201.00{i}", paper_kind="older", citations=1000) for i in range(3)]
    pipeline, _ = _make_pipeline(
        cached_papers=fresh_papers + older_papers,
        citations_enabled=False,
        older_per_digest=2,
    )

    seen: list[ScoredPaper] = []
    fake = MagicMock()
    fake.name = "fake"
    fake.notify.side_effect = lambda papers: (seen.extend(papers), True)[1]
    pipeline.user_notifiers["alice"] = [fake]

    pipeline._run_for_user(
        pipeline.config.users[0],
        all_scored=fresh_papers + older_papers,
        dry_run=False,
    )

    assert all(sp.paper_kind == "fresh" for sp in seen)


def test_older_works_not_double_sent():
    """An older paper marked sent for a user is excluded next run."""
    fresh = _sp("2401.001", paper_kind="fresh")
    older = _sp("2201.001", paper_kind="older", citations=1000)
    pipeline, _ = _make_pipeline(cached_papers=[fresh, older], older_per_digest=5)

    seen_runs: list[list[ScoredPaper]] = []
    fake = MagicMock()
    fake.name = "fake"

    def _capture(papers):
        seen_runs.append(list(papers))
        return True

    fake.notify.side_effect = _capture
    pipeline.user_notifiers["alice"] = [fake]

    # Run twice
    pipeline._run_for_user(pipeline.config.users[0], all_scored=[fresh, older], dry_run=False)
    pipeline._run_for_user(pipeline.config.users[0], all_scored=[fresh, older], dry_run=False)

    # First run: both papers
    assert len(seen_runs[0]) == 2
    # Second run: nothing new — pipeline returns early without calling notify.
    assert len(seen_runs) == 1
