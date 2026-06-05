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

    def run_pipeline():
        logger.info("Scheduled pipeline run started...")
        try:
            pipeline.run(user_ids=user_ids)
        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)

    # Add scheduled job
    if config.schedule.mode == "interval":
        trigger = IntervalTrigger(minutes=config.schedule.interval_minutes)
    else:
        trigger = CronTrigger(
            hour=config.schedule.cron_hour,
            minute=config.schedule.cron_minute,
        )

    scheduler.add_job(
        run_pipeline,
        trigger=trigger,
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
    if config.schedule.mode == "interval":
        schedule_desc = f"every {config.schedule.interval_minutes} minute(s)"
    else:
        schedule_desc = (
            f"daily at {config.schedule.cron_hour:02d}:{config.schedule.cron_minute:02d}"
        )
    logger.info(
        f"Daemon started. Running {schedule_desc} "
        f"({config.schedule.timezone}) for {target}"
    )
    logger.info("Press Ctrl+C to stop.")

    # Run once on startup
    logger.info("Running initial pipeline...")
    run_pipeline()

    scheduler.start()
