"""Tests for the daemon-heartbeat liveness module."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from paper_agent.daemon_heartbeat import (
    assess_health,
    heartbeat_path,
    pid_is_alive,
    read_heartbeat,
    write_heartbeat,
)

# ─── path / I/O ───────────────────────────────────────────────────────


def test_heartbeat_path_suffix(tmp_path: Path) -> None:
    p = heartbeat_path(tmp_path / "test.db")
    assert p == tmp_path / "test.db.daemon.json"


def test_write_and_read(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    write_heartbeat(db, last_event="startup")
    hb = read_heartbeat(db)
    assert hb is not None
    assert hb["pid"] == os.getpid()
    assert hb["last_event"] == "startup"
    assert "last_heartbeat_at" in hb
    assert "started_at" in hb


def test_write_read_corrupt_file(tmp_path: Path) -> None:
    """A corrupt JSON file returns None, never crashes."""
    p = heartbeat_path(tmp_path / "test.db")
    p.write_text("{{{not json", encoding="utf-8")
    assert read_heartbeat(tmp_path / "test.db") is None


def test_write_missing_file(tmp_path: Path) -> None:
    assert read_heartbeat(tmp_path / "nonexistent.db") is None


def test_write_preserves_started_at(tmp_path: Path) -> None:
    """Repeated writes preserve the original started_at."""
    db = tmp_path / "test.db"
    write_heartbeat(db, started_at="2026-01-01T00:00:00", last_event="startup")
    write_heartbeat(db, last_event="ingest")
    hb = read_heartbeat(db)
    assert hb["started_at"] == "2026-01-01T00:00:00"
    assert hb["last_event"] == "ingest"


# ─── pid_is_alive ─────────────────────────────────────────────────────


def test_own_pid_is_alive() -> None:
    """Our own PID is always alive."""
    assert pid_is_alive(os.getpid()) is True


def test_invalid_pid_is_dead() -> None:
    assert pid_is_alive(-1) is False
    assert pid_is_alive(0) is False


def test_very_high_pid_is_dead() -> None:
    assert pid_is_alive(999_999_999) is False


# ─── assess_health ────────────────────────────────────────────────────


def test_health_never_started(tmp_path: Path) -> None:
    h = assess_health(tmp_path / "never.db", 360)
    assert h["status"] == "never_started"
    assert h["pid"] is None


def test_health_running_fresh(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    write_heartbeat(db, last_event="ingest")
    h = assess_health(db, 360)  # 360 min = 6 h interval
    assert h["status"] == "running"
    # PID should match our current process
    assert h["pid"] == os.getpid()


def test_health_stale_no_recent_heartbeat(tmp_path: Path) -> None:
    """A heartbeat that is 7 hours old with a 3-hour interval is stale."""
    db = tmp_path / "test.db"
    # Write a heartbeat with a crafted timestamp
    old = (datetime.now() - timedelta(hours=7)).isoformat(timespec="seconds")
    p = heartbeat_path(db)
    p.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "started_at": old,
                "last_heartbeat_at": old,
                "last_event": "ingest",
            }
        ),
        encoding="utf-8",
    )
    h = assess_health(db, 180)  # 3 h interval → stale after ~6 h
    assert h["status"] == "stale"


def test_health_running_barely_fresh(tmp_path: Path) -> None:
    """A heartbeat just under the 2× interval threshold is still running."""
    db = tmp_path / "test.db"
    # Write a heartbeat within the threshold
    recent = (datetime.now() - timedelta(minutes=30)).isoformat(timespec="seconds")
    p = heartbeat_path(db)
    p.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "started_at": recent,
                "last_heartbeat_at": recent,
                "last_event": "ingest",
            }
        ),
        encoding="utf-8",
    )
    h = assess_health(db, 60)  # 60 min interval → stale after ~2 h
    assert h["status"] == "running"


def test_health_dead_pid(tmp_path: Path) -> None:
    """A PID that doesn't exist + any heartbeat = dead."""
    db = tmp_path / "test.db"
    now = datetime.now().isoformat(timespec="seconds")
    p = heartbeat_path(db)
    p.write_text(
        json.dumps(
            {
                "pid": 999_999_999,
                "started_at": now,
                "last_heartbeat_at": now,
                "last_event": "ingest",
            }
        ),
        encoding="utf-8",
    )
    h = assess_health(db, 360)
    assert h["status"] == "dead"
