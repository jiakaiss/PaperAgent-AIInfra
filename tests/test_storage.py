"""Tests for SQLite storage with two-table schema."""

import os
import tempfile
from datetime import datetime

from paper_agent.models import Paper, ScoredPaper
from paper_agent.storage.database import PaperDatabase


def _make_scored_paper(arxiv_id: str = "2401.00001v1", tags=("quantization",)) -> ScoredPaper:
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
        sub_domain_tags=tags,
    )


def test_cache_and_filter_uncached():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = PaperDatabase(db_path)
        sp1 = _make_scored_paper("2401.00001v1")
        sp2 = _make_scored_paper("2401.00002v1")

        # Initially all uncached
        uncached = db.filter_uncached(["2401.00001v1", "2401.00002v1", "2401.00003v1"])
        assert len(uncached) == 3

        # Cache some papers
        db.cache_papers([sp1, sp2])

        # Now only 00003 should be uncached
        uncached = db.filter_uncached(["2401.00001v1", "2401.00002v1", "2401.00003v1"])
        assert uncached == ["2401.00003v1"]
    finally:
        os.unlink(db_path)


def test_load_cached_papers():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = PaperDatabase(db_path)
        sp = _make_scored_paper("2401.00001v1", tags=("quantization", "sparsity"))
        db.cache_papers([sp])

        loaded = db.load_cached_papers(["2401.00001v1"])
        assert len(loaded) == 1
        assert loaded[0].paper.arxiv_id == "2401.00001v1"
        assert loaded[0].sub_domain_tags == ("quantization", "sparsity")
        assert loaded[0].relevance_score == 8.0
    finally:
        os.unlink(db_path)


def test_per_user_sent_tracking():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = PaperDatabase(db_path)
        sp1 = _make_scored_paper("2401.00001v1")
        sp2 = _make_scored_paper("2401.00002v1")

        # Mark as sent for alice only
        db.mark_sent("alice", [sp1, sp2])

        # Alice has seen both
        unsent_alice = db.filter_unsent_for_user("alice", ["2401.00001v1", "2401.00002v1"])
        assert unsent_alice == []

        # Bob hasn't seen any
        unsent_bob = db.filter_unsent_for_user("bob", ["2401.00001v1", "2401.00002v1"])
        assert set(unsent_bob) == {"2401.00001v1", "2401.00002v1"}
    finally:
        os.unlink(db_path)


def test_mark_sent_idempotent():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = PaperDatabase(db_path)
        sp = _make_scored_paper("2401.00001v1")

        # Mark twice should not error
        db.mark_sent("alice", [sp])
        db.mark_sent("alice", [sp])

        unsent = db.filter_unsent_for_user("alice", ["2401.00001v1"])
        assert unsent == []
    finally:
        os.unlink(db_path)


def test_stats_global():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = PaperDatabase(db_path)
        stats = db.get_stats()
        assert stats["total_cached"] == 0
        assert stats["total_sent"] == 0
        assert stats["sent_today"] == 0
        assert stats["last_sent"] == "never"
        assert stats["user_count"] == 0
    finally:
        os.unlink(db_path)


def test_stats_per_user():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = PaperDatabase(db_path)
        sp = _make_scored_paper("2401.00001v1")
        db.cache_papers([sp])
        db.mark_sent("alice", [sp])

        stats_alice = db.get_stats(user_id="alice")
        assert stats_alice["total_sent"] == 1

        stats_bob = db.get_stats(user_id="bob")
        assert stats_bob["total_sent"] == 0
    finally:
        os.unlink(db_path)
