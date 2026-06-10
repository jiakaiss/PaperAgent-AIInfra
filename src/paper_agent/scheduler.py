"""Scheduler for periodic pipeline runs."""

from __future__ import annotations

import logging
import os
import signal
import sys
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from paper_agent.config import AppConfig
from paper_agent.daemon_heartbeat import (
    heartbeat_path,
    pid_is_alive,
    read_heartbeat,
    write_heartbeat,
)
from paper_agent.pipeline import Pipeline

logger = logging.getLogger(__name__)


class DaemonAlreadyRunningError(RuntimeError):
    """Raised when start_daemon detects another live daemon for the same DB.

    Carries the existing PID so the caller (CLI) can render a useful message.
    Without this guard, two daemons would happily share the same DB and each
    fire the digest cron at 09:00, sending every subscriber two identical
    emails (one per process). See logs/daemon.log on 2026-06-10 for the
    incident that motivated this check.
    """

    def __init__(self, pid: int, started_at: str | None):
        self.pid = pid
        self.started_at = started_at
        super().__init__(
            f"Another paper-agent daemon is already running (PID {pid}, "
            f"started {started_at or 'unknown'}). Stop it first or pass --force."
        )


def start_daemon(
    config: AppConfig,
    user_ids: list[str] | None = None,
    *,
    force: bool = False,
) -> None:
    """Start the scheduler daemon.

    Args:
        config: Application config
        user_ids: Optional list of user IDs to run for (None = all users)
        force: Skip the duplicate-daemon preflight check. Use only when the
            heartbeat file is known to be stale and the OS-level PID check
            is somehow wrong (rare — prefer killing the old process instead).
    """
    db_path = config.storage.db_path
    if not force:
        hb = read_heartbeat(db_path)
        if hb is not None:
            other_pid = int(hb.get("pid", 0))
            last_event = hb.get("last_event")
            # last_event == "shutdown" means the previous daemon exited
            # cleanly via SIGINT/SIGTERM — the heartbeat is a tombstone,
            # not a liveness signal, so don't treat it as a conflict even
            # if the PID happens to have been reused by something else.
            if last_event != "shutdown" and other_pid > 0 and other_pid != os.getpid():
                if pid_is_alive(other_pid):
                    raise DaemonAlreadyRunningError(other_pid, hb.get("started_at"))

    scheduler = BlockingScheduler(timezone=config.schedule.timezone)

    pipeline = Pipeline(config)

    started_at = datetime.now().isoformat(timespec="seconds")
    # Initial heartbeat so the admin dashboard sees "running" the moment
    # the daemon starts, before the first scheduled job fires.
    write_heartbeat(db_path, started_at=started_at, last_event="startup")
    logger.info("Heartbeat file: %s", heartbeat_path(db_path))

    def run_ingest():
        logger.info("Scheduled ingest started...")
        try:
            pipeline.ingest()
        except Exception as e:
            logger.error(f"Ingest failed: {e}", exc_info=True)
        finally:
            # Always tick the heartbeat — even if the job failed, the
            # scheduler is alive and trying. A wedged scheduler stops
            # ticking entirely, which is what the dashboard's "stale"
            # status detects.
            write_heartbeat(db_path, started_at=started_at, last_event="ingest")

    def run_digest():
        logger.info("Scheduled digest started...")
        try:
            pipeline.run_cached_digest(user_ids=user_ids)
        except Exception as e:
            logger.error(f"Digest failed: {e}", exc_info=True)
        finally:
            write_heartbeat(db_path, started_at=started_at, last_event="digest")

    if config.schedule.ingest_hours:
        ingest_hours_csv = ",".join(str(h) for h in sorted(config.schedule.ingest_hours))
        ingest_trigger = CronTrigger(
            hour=ingest_hours_csv,
            minute=config.schedule.ingest_minute,
        )
        ingest_desc = (
            f"at {ingest_hours_csv}:{config.schedule.ingest_minute:02d} "
            f"({config.schedule.timezone})"
        )
    else:
        ingest_trigger = IntervalTrigger(minutes=config.schedule.ingest_interval_minutes)
        ingest_desc = f"every {config.schedule.ingest_interval_minutes} minute(s)"

    scheduler.add_job(
        run_ingest,
        trigger=ingest_trigger,
        id="paper_ingest",
        name="AI Infra Paper Ingest",
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        run_digest,
        trigger=CronTrigger(
            hour=config.schedule.digest_hour,
            minute=config.schedule.digest_minute,
        ),
        id="paper_digest",
        name="AI Infra Paper Digest",
        misfire_grace_time=3600,
    )

    # Handle shutdown signals
    def shutdown(signum, frame):
        logger.info("Shutting down scheduler...")
        # Mark the heartbeat as shutdown so the admin dashboard distinguishes
        # "operator stopped it" from "process crashed". (PID dies either way,
        # so this is best-effort observability — the dashboard's primary
        # signal is still the PID liveness check.)
        try:
            write_heartbeat(db_path, started_at=started_at, last_event="shutdown")
        except Exception:
            pass
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    target = f"users: {', '.join(user_ids)}" if user_ids else "all users"
    logger.info(
        f"Daemon started. Ingest {ingest_desc}; "
        f"digest daily at {config.schedule.digest_hour:02d}:{config.schedule.digest_minute:02d} "
        f"({config.schedule.timezone}) for {target}"
    )
    logger.info("Press Ctrl+C to stop.")

    # Populate the cache on startup; user-facing digest remains on its daily schedule.
    logger.info("Running initial ingest...")
    run_ingest()

    scheduler.start()
