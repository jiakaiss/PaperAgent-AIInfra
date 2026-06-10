"""Tests for scheduler job setup."""

import json

import pytest

from paper_agent.config import AppConfig, ScheduleConfig, StorageConfig
from paper_agent.daemon_heartbeat import heartbeat_path
from paper_agent.scheduler import DaemonAlreadyRunningError, start_daemon


class FakeScheduler:
    instances = []

    def __init__(self, timezone=None):
        self.timezone = timezone
        self.jobs = []
        FakeScheduler.instances.append(self)

    def add_job(self, func, trigger, id=None, name=None, misfire_grace_time=None):
        self.jobs.append(
            {
                "func": func,
                "trigger": trigger,
                "id": id,
                "name": name,
                "misfire_grace_time": misfire_grace_time,
            }
        )

    def start(self):
        return None

    def shutdown(self, wait=False):
        return None


class FakePipeline:
    instances = []

    def __init__(self, config):
        self.config = config
        self.ingest_calls = 0
        self.digest_calls = 0
        FakePipeline.instances.append(self)

    def ingest(self):
        self.ingest_calls += 1

    def run_cached_digest(self, user_ids=None):
        self.digest_calls += 1


def _make_config(tmp_path) -> AppConfig:
    """Build an AppConfig pointing at an isolated DB so tests don't trip the
    duplicate-daemon preflight against a real running daemon."""
    return AppConfig(
        schedule=ScheduleConfig(
            ingest_interval_minutes=360,
            digest_hour=9,
            digest_minute=0,
        ),
        storage=StorageConfig(db_path=str(tmp_path / "test.db")),
    )


def test_daemon_registers_separate_ingest_and_digest_jobs(monkeypatch, tmp_path):
    """Daemon registers interval ingest and cron digest as separate jobs."""
    FakeScheduler.instances = []
    FakePipeline.instances = []
    monkeypatch.setattr("paper_agent.scheduler.BlockingScheduler", FakeScheduler)
    monkeypatch.setattr("paper_agent.scheduler.Pipeline", FakePipeline)

    start_daemon(_make_config(tmp_path))

    scheduler = FakeScheduler.instances[0]
    assert {job["id"] for job in scheduler.jobs} == {"paper_ingest", "paper_digest"}
    pipeline = FakePipeline.instances[0]
    assert pipeline.ingest_calls == 1
    assert pipeline.digest_calls == 0


def test_daemon_refuses_to_start_when_another_is_alive(monkeypatch, tmp_path):
    """Preflight raises DaemonAlreadyRunningError when an existing heartbeat
    points to a live PID — the safeguard against the 2026-06-10 double-digest
    incident (two daemons sharing the same DB each fired the 09:00 cron)."""
    FakeScheduler.instances = []
    FakePipeline.instances = []
    monkeypatch.setattr("paper_agent.scheduler.BlockingScheduler", FakeScheduler)
    monkeypatch.setattr("paper_agent.scheduler.Pipeline", FakePipeline)
    # Force pid_is_alive() to report True regardless of OS state so the test
    # doesn't depend on real process IDs.
    monkeypatch.setattr("paper_agent.scheduler.pid_is_alive", lambda pid: True)

    config = _make_config(tmp_path)
    heartbeat_path(config.storage.db_path).write_text(
        json.dumps(
            {
                "pid": 999999,
                "started_at": "2026-06-09T16:41:26",
                "last_heartbeat_at": "2026-06-10T09:00:14",
                "last_event": "digest",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(DaemonAlreadyRunningError) as exc:
        start_daemon(config)
    assert exc.value.pid == 999999
    # No jobs/pipeline should have been built when preflight rejected.
    assert FakeScheduler.instances == []
    assert FakePipeline.instances == []


def test_daemon_force_overrides_preflight(monkeypatch, tmp_path):
    """force=True bypasses the preflight even with a live-looking heartbeat."""
    FakeScheduler.instances = []
    FakePipeline.instances = []
    monkeypatch.setattr("paper_agent.scheduler.BlockingScheduler", FakeScheduler)
    monkeypatch.setattr("paper_agent.scheduler.Pipeline", FakePipeline)
    monkeypatch.setattr("paper_agent.scheduler.pid_is_alive", lambda pid: True)

    config = _make_config(tmp_path)
    heartbeat_path(config.storage.db_path).write_text(
        json.dumps({"pid": 999999, "last_event": "digest"}),
        encoding="utf-8",
    )

    start_daemon(config, force=True)
    assert len(FakeScheduler.instances) == 1


def test_daemon_starts_when_previous_heartbeat_is_shutdown(monkeypatch, tmp_path):
    """A heartbeat with last_event='shutdown' is a tombstone, not a live
    daemon — restarting after a clean stop must not require --force."""
    FakeScheduler.instances = []
    FakePipeline.instances = []
    monkeypatch.setattr("paper_agent.scheduler.BlockingScheduler", FakeScheduler)
    monkeypatch.setattr("paper_agent.scheduler.Pipeline", FakePipeline)
    monkeypatch.setattr("paper_agent.scheduler.pid_is_alive", lambda pid: True)

    config = _make_config(tmp_path)
    heartbeat_path(config.storage.db_path).write_text(
        json.dumps({"pid": 999999, "last_event": "shutdown"}),
        encoding="utf-8",
    )

    start_daemon(config)
    assert len(FakeScheduler.instances) == 1


def test_daemon_starts_when_previous_pid_is_dead(monkeypatch, tmp_path):
    """A heartbeat pointing to a dead PID must not block startup."""
    FakeScheduler.instances = []
    FakePipeline.instances = []
    monkeypatch.setattr("paper_agent.scheduler.BlockingScheduler", FakeScheduler)
    monkeypatch.setattr("paper_agent.scheduler.Pipeline", FakePipeline)
    monkeypatch.setattr("paper_agent.scheduler.pid_is_alive", lambda pid: False)

    config = _make_config(tmp_path)
    heartbeat_path(config.storage.db_path).write_text(
        json.dumps({"pid": 999999, "last_event": "ingest"}),
        encoding="utf-8",
    )

    start_daemon(config)
    assert len(FakeScheduler.instances) == 1
