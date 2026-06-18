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


def _scored(arxiv_id: str, *, citations=0, paper_kind="fresh") -> ScoredPaper:
    paper = Paper(
        arxiv_id=arxiv_id,
        title=f"Title {arxiv_id}",
        authors=["A"],
        abstract="abs",
        published=datetime(2024, 1, 1),
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


def test_legacy_zero_citation_fresh_paper_shows_neither_badge(client_two_papers):
    """A normal fresh paper with citation_count=0 shows no citation/older badges."""
    resp = client_two_papers.get("/_paper_list?older=exclude")
    assert "🔖 重要老作" not in resp.text
    assert "📈" not in resp.text  # no citation badge for 0-citation paper
