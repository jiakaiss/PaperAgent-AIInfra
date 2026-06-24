"""Tests for the citation/older-works web filter and badges."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime

import pytest
from starlette.testclient import TestClient

from paper_agent.config import AppConfig, StorageConfig
from paper_agent.models import Paper, ScoredPaper
from paper_agent.storage.database import PaperDatabase
from paper_agent.web.app import create_app


def _scored(arxiv_id: str, *, citations=0, paper_kind="fresh", published=None) -> ScoredPaper:
    paper = Paper(
        arxiv_id=arxiv_id,
        title=f"Title {arxiv_id}",
        authors=["A"],
        abstract="abs",
        published=published or datetime(2024, 1, 1),
        categories=["cs.LG"],
        pdf_url=f"p/{arxiv_id}",
        abs_url=f"a/{arxiv_id}",
    )
    return ScoredPaper(
        paper=paper,
        relevance_score=8.0,
        quality_score=7.0,
        summary_zh="测试",
        sub_domain_tags=("quantization",),
        citation_count=citations,
        paper_kind=paper_kind,
    )


@pytest.fixture
def client_two_papers():
    """Yield a client whose DB has 1 fresh + 1 older paper."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    db = PaperDatabase(path)
    db.cache_papers(
        [
            _scored("2401.001", citations=0, paper_kind="fresh"),
            _scored("2201.001", citations=1500, paper_kind="older"),
        ]
    )
    cfg = AppConfig(storage=StorageConfig(db_path=path))
    app = create_app(cfg)
    yield TestClient(app)
    os.unlink(path)


# ─── ?older= routing ───


def test_older_only_returns_only_older(client_two_papers):
    resp = client_two_papers.get("/_paper_list?older=only")
    assert resp.status_code == 200
    assert "2201.001" in resp.text
    assert "2401.001" not in resp.text


def test_older_exclude_returns_only_fresh(client_two_papers):
    resp = client_two_papers.get("/_paper_list?older=exclude")
    assert resp.status_code == 200
    assert "2401.001" in resp.text
    assert "2201.001" not in resp.text


def test_older_default_includes_both(client_two_papers):
    """No ?older= param → both fresh and older are visible (preserves bookmarks)."""
    resp = client_two_papers.get("/_paper_list")
    assert resp.status_code == 200
    assert "2401.001" in resp.text
    assert "2201.001" in resp.text


def test_older_invalid_value_treated_as_include(client_two_papers):
    resp = client_two_papers.get("/_paper_list?older=banana")
    assert resp.status_code == 200
    assert "2401.001" in resp.text
    assert "2201.001" in resp.text


# ─── card-level badges ───


def test_older_paper_card_shows_both_badges(client_two_papers):
    """An older paper with citations renders both 重要老作 and 📈 N citations."""
    resp = client_two_papers.get("/_paper_list?older=only")
    assert "🔖 重要老作" in resp.text
    assert "📈 1500 citations" in resp.text


def test_zero_citation_paper_still_shows_citation_badge(client_two_papers):
    """A fresh paper with citation_count=0 now ALWAYS shows the citation badge.

    Per `paper-browsing` spec (`web-paper-meta-display` change): the badge is
    unconditional so every card has the same right-side cluster, and `0` is
    itself a real data point ("we've refreshed and there are none yet").
    """
    resp = client_two_papers.get("/_paper_list?older=exclude")
    assert "🔖 重要老作" not in resp.text  # not an older paper
    assert "📈 0 citations" in resp.text  # citation badge always rendered


def test_card_renders_published_date(client_two_papers):
    """Each paper card renders `published` as YYYY-MM-DD on the authors line."""
    resp = client_two_papers.get("/_paper_list")
    # Fixture publishes both papers on 2024-01-01
    assert "2024-01-01" in resp.text
    assert 'class="paper-published"' in resp.text


def test_header_badge_cluster_wrapper_present(client_two_papers):
    """The right-aligned badge cluster wrapper exists on every card —
    including the fresh-paper case (tier + citation only, no older badge)
    and the older case (tier + older + citation)."""
    # Fresh paper (no older badge): cluster still present
    resp = client_two_papers.get("/_paper_list?older=exclude")
    assert "paper-card-header-badges" in resp.text

    # Older paper (all three badges): cluster still present
    resp = client_two_papers.get("/_paper_list?older=only")
    assert "paper-card-header-badges" in resp.text
