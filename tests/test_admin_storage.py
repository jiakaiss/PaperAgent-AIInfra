"""Unit tests for the admin-dashboard aggregate queries on PaperDatabase."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from paper_agent.storage.database import PaperDatabase


@pytest.fixture
def db(tmp_path: Path) -> PaperDatabase:
    """Empty DB at a tmp path. Tests seed rows directly to control timestamps."""
    return PaperDatabase(tmp_path / "test.db")


def _insert_sent(db: PaperDatabase, user_id: str, arxiv_id: str, sent_at: str) -> None:
    """Insert a sent_papers row with a controlled timestamp (bypasses mark_sent)."""
    with sqlite3.connect(str(db.db_path)) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO sent_papers (user_id, arxiv_id, sent_at) VALUES (?, ?, ?)",
            (user_id, arxiv_id, sent_at),
        )
        conn.commit()


def _insert_paper(
    db: PaperDatabase, arxiv_id: str, scored_at: str, impact_tier: str = "solid"
) -> None:
    """Insert a papers row with a controlled scored_at and impact_tier."""
    with sqlite3.connect(str(db.db_path)) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO papers
               (arxiv_id, title, authors, abstract, published, categories,
                pdf_url, abs_url, relevance_score, quality_score, summary_zh,
                sub_domain_tags, scored_at, key_contributions, problem_statement_zh,
                methods_zh, impact_tier)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                arxiv_id,
                f"Title {arxiv_id}",
                "Author A",
                "Abstract text",
                "2026-06-01",
                "cs.LG",
                f"https://arxiv.org/pdf/{arxiv_id}",
                f"https://arxiv.org/abs/{arxiv_id}",
                7.0,
                6.0,
                "摘要",
                json.dumps(["quantization"]),
                scored_at,
                json.dumps(["contrib"]),
                "problem",
                "methods",
                impact_tier,
            ),
        )
        conn.commit()


# ─── count_active_subscriptions ───────────────────────────────────────


def test_count_active_subscriptions_empty(db: PaperDatabase) -> None:
    assert db.count_active_subscriptions() == 0


def test_count_active_subscriptions_mixed(db: PaperDatabase) -> None:
    db.add_subscription("alice@example.com", ["quantization"])
    db.add_subscription("bob@example.com", ["serving"])
    db.add_subscription("carol@example.com", ["moe"])
    db.unsubscribe_email("carol@example.com")
    assert db.count_active_subscriptions() == 2


# ─── get_user_stats ───────────────────────────────────────────────────


def test_get_user_stats_empty(db: PaperDatabase) -> None:
    assert db.get_user_stats() == []


def test_get_user_stats_subscriber_with_zero_deliveries(db: PaperDatabase) -> None:
    """A subscribed user with no sent_papers rows MUST still appear (per spec)."""
    db.add_subscription("noobie@example.com", ["serving"])
    stats = db.get_user_stats()
    assert len(stats) == 1
    row = stats[0]
    assert row["user_id"] == "noobie@example.com"
    assert row["total_sent"] == 0
    assert row["sent_7d"] == 0
    assert row["sent_30d"] == 0
    assert row["last_sent_at"] is None
    assert row["status"] == "active"
    assert row["sub_domains"] == ["serving"]


def test_get_user_stats_counts_windows_correctly(db: PaperDatabase) -> None:
    db.add_subscription("alice@example.com", ["quantization"])
    today = date.today()
    # 3 in last 7d, 5 more in 8-30d range, 2 more 60d ago = 10 total.
    for i in range(3):
        _insert_sent(
            db,
            "alice@example.com",
            f"arxiv-7d-{i}",
            (today - timedelta(days=i)).isoformat() + "T10:00:00",
        )
    for i in range(5):
        _insert_sent(
            db,
            "alice@example.com",
            f"arxiv-30d-{i}",
            (today - timedelta(days=10 + i)).isoformat() + "T10:00:00",
        )
    for i in range(2):
        _insert_sent(
            db,
            "alice@example.com",
            f"arxiv-old-{i}",
            (today - timedelta(days=60 + i)).isoformat() + "T10:00:00",
        )

    stats = db.get_user_stats()
    assert len(stats) == 1
    row = stats[0]
    assert row["total_sent"] == 10
    assert row["sent_7d"] == 3
    assert row["sent_30d"] == 8  # 3 in last 7d + 5 in 8-30d window
    assert row["last_sent_at"] is not None


def test_get_user_stats_includes_sent_only_users(db: PaperDatabase) -> None:
    """Users with deliveries but no subscription row (e.g. test_user) appear too."""
    _insert_sent(db, "test_user", "arxiv-1", datetime.now().isoformat())
    stats = db.get_user_stats()
    assert len(stats) == 1
    assert stats[0]["user_id"] == "test_user"
    assert stats[0]["status"] is None  # not a subscriber
    assert stats[0]["total_sent"] == 1


def test_get_user_stats_unsubscribed_user_still_listed(db: PaperDatabase) -> None:
    db.add_subscription("bye@example.com", ["serving"])
    _insert_sent(db, "bye@example.com", "arxiv-1", datetime.now().isoformat())
    db.unsubscribe_email("bye@example.com")
    stats = db.get_user_stats()
    assert len(stats) == 1
    assert stats[0]["status"] == "inactive"
    assert stats[0]["total_sent"] == 1


# ─── get_daily_sent_counts ────────────────────────────────────────────


def test_get_daily_sent_counts_empty_db(db: PaperDatabase) -> None:
    result = db.get_daily_sent_counts(days=7)
    assert len(result) == 7
    assert all(r["count"] == 0 for r in result)
    # Most-recent-first ordering.
    dates = [r["date"] for r in result]
    assert dates == sorted(dates, reverse=True)


def test_get_daily_sent_counts_sparse(db: PaperDatabase) -> None:
    today = date.today()
    day_before_yesterday = (today - timedelta(days=2)).isoformat()
    _insert_sent(db, "alice@example.com", "p1", day_before_yesterday + "T10:00:00")
    _insert_sent(db, "alice@example.com", "p2", day_before_yesterday + "T11:00:00")

    result = db.get_daily_sent_counts(days=7)
    assert len(result) == 7
    by_date = {r["date"]: r["count"] for r in result}
    assert by_date[day_before_yesterday] == 2
    # Other 6 days are zero.
    assert sum(r["count"] for r in result) == 2


def test_get_daily_sent_counts_ordering(db: PaperDatabase) -> None:
    result = db.get_daily_sent_counts(days=3)
    today = date.today()
    assert result[0]["date"] == today.isoformat()
    assert result[1]["date"] == (today - timedelta(days=1)).isoformat()
    assert result[2]["date"] == (today - timedelta(days=2)).isoformat()


def test_get_daily_sent_counts_zero_days(db: PaperDatabase) -> None:
    assert db.get_daily_sent_counts(days=0) == []


# ─── get_daily_paper_counts ───────────────────────────────────────────


def test_get_daily_paper_counts_empty_db(db: PaperDatabase) -> None:
    result = db.get_daily_paper_counts(days=7)
    assert len(result) == 7
    assert all(r["count"] == 0 for r in result)


def test_get_daily_paper_counts_today_batch(db: PaperDatabase) -> None:
    today = date.today().isoformat()
    for i in range(5):
        _insert_paper(db, f"p-{i}", today + "T10:00:00")
    result = db.get_daily_paper_counts(days=7)
    assert result[0]["date"] == today
    assert result[0]["count"] == 5


# ─── get_tier_distribution ────────────────────────────────────────────


def test_get_tier_distribution_empty(db: PaperDatabase) -> None:
    result = db.get_tier_distribution()
    assert result == {"breakthrough": 0, "solid": 0, "incremental": 0}


def test_get_tier_distribution_mixed(db: PaperDatabase) -> None:
    today = date.today().isoformat() + "T10:00:00"
    _insert_paper(db, "p-b1", today, impact_tier="breakthrough")
    _insert_paper(db, "p-s1", today, impact_tier="solid")
    _insert_paper(db, "p-s2", today, impact_tier="solid")
    _insert_paper(db, "p-i1", today, impact_tier="incremental")
    result = db.get_tier_distribution()
    assert result == {"breakthrough": 1, "solid": 2, "incremental": 1}


# ─── last-ingest / last-digest ────────────────────────────────────────


def test_get_last_ingest_at_empty(db: PaperDatabase) -> None:
    assert db.get_last_ingest_at() is None


def test_get_last_digest_at_empty(db: PaperDatabase) -> None:
    assert db.get_last_digest_at() is None


def test_get_last_ingest_at_returns_max(db: PaperDatabase) -> None:
    _insert_paper(db, "p1", "2026-06-01T10:00:00")
    _insert_paper(db, "p2", "2026-06-08T15:00:00")
    _insert_paper(db, "p3", "2026-06-05T12:00:00")
    assert db.get_last_ingest_at() == "2026-06-08T15:00:00"


def test_get_last_digest_at_returns_max(db: PaperDatabase) -> None:
    _insert_sent(db, "alice@example.com", "p1", "2026-06-08T09:00:00")
    _insert_sent(db, "alice@example.com", "p2", "2026-06-08T15:30:00")
    assert db.get_last_digest_at() == "2026-06-08T15:30:00"


# ─── list_subscriptions ───────────────────────────────────────────────


def test_list_subscriptions_includes_inactive(db: PaperDatabase) -> None:
    db.add_subscription("alice@example.com", ["quantization"])
    db.add_subscription("bob@example.com", ["serving"])
    db.unsubscribe_email("bob@example.com")
    result = db.list_subscriptions()
    assert len(result) == 2
    by_email = {r["email"]: r for r in result}
    assert by_email["alice@example.com"]["status"] == "active"
    assert by_email["bob@example.com"]["status"] == "inactive"
    assert by_email["bob@example.com"]["unsubscribed_at"] is not None
