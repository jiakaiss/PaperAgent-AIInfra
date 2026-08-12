"""Tests for scheduler job setup."""

import json
import threading

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
    # Class-level hook: a test sets this to a threading.Event before calling
    # start_daemon so the FakePipeline constructed inside start_daemon picks
    # it up. __init__ consumes it (resets to None) so every other test stays
    # non-blocking.
    block_event: threading.Event | None = None

    def __init__(self, config):
        self.config = config
        self.ingest_calls = 0
        self.ingest_completed = 0
        self.digest_calls = 0
        self.refresh_calls = 0
        # When set, ingest() blocks on this event - simulates a hung ingest
        # for the watchdog test. None (default) keeps ingest non-blocking so
        # every other test is unaffected.
        self.block_event = FakePipeline.block_event
        FakePipeline.block_event = None
        FakePipeline.instances.append(self)

    def ingest(self):
        self.ingest_calls += 1
        if self.block_event is not None:
            # Simulate a hung ingest (e.g. a stalled network call). The
            # watchdog must abandon this run and return, releasing the
            # scheduler slot, rather than waiting forever.
            self.block_event.wait(timeout=30)
        self.ingest_completed += 1

    def run_cached_digest(self, user_ids=None):
        self.digest_calls += 1

    def refresh_users(self):
        # Mirror the real Pipeline.refresh_users contract — scheduler calls
        # this at the top of every tick to pick up newly-subscribed users.
        self.refresh_calls += 1
        return {"added": 0, "removed": 0, "active": 0}


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


def test_ingest_watchdog_aborts_hung_run_and_releases_slot(monkeypatch, tmp_path):
    """A hung ingest must be abandoned after ``ingest_timeout_seconds`` so the
    APScheduler instance slot (max_instances=1) is released and the next
    scheduled tick can run. This is the defense-in-depth for the 2026-07-24
    arXiv stall, which held that slot for 18 days and blocked every later
    ingest. The per-request HTTP timeout in the fetcher is the primary fix;
    this watchdog catches any *other* hang source (DB lock, Claude API, etc.).
    """
    import time

    FakeScheduler.instances = []
    FakePipeline.instances = []
    monkeypatch.setattr("paper_agent.scheduler.BlockingScheduler", FakeScheduler)
    monkeypatch.setattr("paper_agent.scheduler.Pipeline", FakePipeline)
    monkeypatch.setattr("paper_agent.scheduler.pid_is_alive", lambda pid: False)
    # signal.signal() only works in the main thread; start_daemon registers
    # SIGINT/SIGTERM handlers, so neutralize it to run start_daemon in a
    # worker thread below (which lets the test fail fast instead of hanging
    # if the watchdog ever regresses).
    monkeypatch.setattr("paper_agent.scheduler.signal.signal", lambda *a, **k: None)

    # Arm the hang: the FakePipeline constructed inside start_daemon will
    # pick this up and block inside ingest().
    block_event = threading.Event()
    FakePipeline.block_event = block_event

    config = AppConfig(
        schedule=ScheduleConfig(
            ingest_interval_minutes=360,
            digest_hour=9,
            digest_minute=0,
            ingest_timeout_seconds=1,
        ),
        storage=StorageConfig(db_path=str(tmp_path / "test.db")),
    )

    # Start the daemon; its initial run_ingest() will hit the 1s watchdog and
    # return instead of hanging on the blocked ingest. start_daemon() reaching
    # the assertion below is itself proof the slot was released.
    def _start():
        start_daemon(config)

    # Run in a thread so the test itself can't hang if the watchdog regresses.
    runner = threading.Thread(target=_start, daemon=True)
    runner.start()
    runner.join(timeout=10)
    assert not runner.is_alive(), "start_daemon hung - watchdog did not abort the ingest"

    pipeline = FakePipeline.instances[0]
    assert pipeline.block_event is block_event
    # The worker entered ingest() (incrementing ingest_calls) then blocked on
    # the event before completing - so it started but never finished. Poll
    # briefly since thread scheduling isn't instant.
    for _ in range(20):
        if pipeline.ingest_calls >= 1:
            break
        time.sleep(0.05)
    assert pipeline.ingest_calls == 1
    assert pipeline.ingest_completed == 0

    # Heartbeat still ticked despite the timeout - the dashboard's staleness
    # signal must reflect "scheduler is trying", not "ingest timed out".
    hb = json.loads(heartbeat_path(config.storage.db_path).read_text(encoding="utf-8"))
    assert hb["last_event"] == "ingest"

    # Release the orphaned worker so it doesn't linger past the test.
    block_event.set()


def test_ingest_timeout_seconds_must_be_positive():
    """Config validation rejects a non-positive ingest budget - a zero/negative
    watchdog would either fire instantly (aborting every healthy ingest) or
    never fire (no protection)."""
    with pytest.raises(ValueError, match="ingest_timeout_seconds"):
        ScheduleConfig(ingest_timeout_seconds=0)
