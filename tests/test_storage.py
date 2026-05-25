"""Tests for SQLite storage."""

import os
import tempfile
from datetime import datetime

from paper_agent.models import Paper, ScoredPaper
from paper_agent.storage.database import PaperDatabase


def _make_scored_paper(arxiv_id: str = "2401.00001v1") -> ScoredPaper:
    paper = Paper(
        arxiv_id=arxiv_id,
        title="Test Paper",
        authors=["Alice"],
        abstract="Test abstract",
        published=datetime(2024, 1, 15),
        categories=["cs.DC"],
        pdf_url="https://arxiv.org/pdf/" + arxiv_id,
        abs_url="https://arxiv.org/abs/" + arxiv_id,
    )
    return ScoredPaper(
        paper=paper,
        relevance_score=8.0,
        quality_score=7.0,
        summary_zh="测试论文",
    )


def test_is_sent():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = PaperDatabase(db_path)
        assert not db.is_sent("2401.00001v1")

        sp = _make_scored_paper("2401.00001v1")
        db.mark_sent([sp])

        assert db.is_sent("2401.00001v1")
        assert not db.is_sent("2401.00002v1")
    finally:
        os.unlink(db_path)


def test_filter_new():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = PaperDatabase(db_path)
        sp1 = _make_scored_paper("2401.00001v1")
        sp2 = _make_scored_paper("2401.00002v1")
        db.mark_sent([sp1, sp2])

        new_ids = db.filter_new(["2401.00001v1", "2401.00002v1", "2401.00003v1"])
        assert new_ids == ["2401.00003v1"]
    finally:
        os.unlink(db_path)


def test_stats():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = PaperDatabase(db_path)
        stats = db.get_stats()
        assert stats["total_papers"] == 0
        assert stats["sent_today"] == 0
        assert stats["last_sent"] == "never"
    finally:
        os.unlink(db_path)
