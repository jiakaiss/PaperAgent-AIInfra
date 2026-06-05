"""Scheduler for periodic pipeline runs."""

from __future__ import annotations

import logging
import signal
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from paper_agent.config import AppConfig
from paper_agent.pipeline import Pipeline

logger = logging.getLogger(__name__)


def start_daemon(config: AppConfig, user_ids: list[str] | None = None) -> None:
    """Start the scheduler daemon.

    Args:
        config: Application config
        user_ids: Optional list of user IDs to run for (None = all users)
    """
    scheduler = BlockingScheduler(timezone=config.schedule.timezone)

    pipeline = Pipeline(config)

    def run_ingest():
        logger.info("Scheduled ingest started...")
        try:
            pipeline.ingest()
        except Exception as e:
            logger.error(f"Ingest failed: {e}", exc_info=True)

    def run_digest():
        logger.info("Scheduled digest started...")
        try:
            pipeline.run_cached_digest(user_ids=user_ids)
        except Exception as e:
            logger.error(f"Digest failed: {e}", exc_info=True)

    scheduler.add_job(
        run_ingest,
        trigger=IntervalTrigger(minutes=config.schedule.ingest_interval_minutes),
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
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    target = f"users: {', '.join(user_ids)}" if user_ids else "all users"
    logger.info(
        f"Daemon started. Ingest every {config.schedule.ingest_interval_minutes} minute(s); "
        f"digest daily at {config.schedule.digest_hour:02d}:{config.schedule.digest_minute:02d} "
        f"({config.schedule.timezone}) for {target}"
    )
    logger.info("Press Ctrl+C to stop.")

    # Populate the cache on startup; user-facing digest remains on its daily schedule.
    logger.info("Running initial ingest...")
    run_ingest()

    scheduler.start()
