"""Tests for scheduler job setup."""

from paper_agent.config import AppConfig, ScheduleConfig
from paper_agent.scheduler import start_daemon


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


def test_daemon_registers_separate_ingest_and_digest_jobs(monkeypatch):
    """Daemon registers interval ingest and cron digest as separate jobs."""
    FakeScheduler.instances = []
    FakePipeline.instances = []
    monkeypatch.setattr("paper_agent.scheduler.BlockingScheduler", FakeScheduler)
    monkeypatch.setattr("paper_agent.scheduler.Pipeline", FakePipeline)

    config = AppConfig(
        schedule=ScheduleConfig(
            ingest_interval_minutes=360,
            digest_hour=9,
            digest_minute=0,
        )
    )

    start_daemon(config)

    scheduler = FakeScheduler.instances[0]
    assert {job["id"] for job in scheduler.jobs} == {"paper_ingest", "paper_digest"}
    pipeline = FakePipeline.instances[0]
    assert pipeline.ingest_calls == 1
    assert pipeline.digest_calls == 0
