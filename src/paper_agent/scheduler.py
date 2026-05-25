"""Scheduler for periodic pipeline runs."""

from __future__ import annotations

import logging
import signal
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from paper_agent.config import AppConfig
from paper_agent.pipeline import Pipeline

logger = logging.getLogger(__name__)


def start_daemon(config: AppConfig) -> None:
    """Start the scheduler daemon."""
    scheduler = BlockingScheduler(timezone=config.schedule.timezone)

    pipeline = Pipeline(config)

    def run_pipeline():
        logger.info("Scheduled pipeline run started...")
        try:
            pipeline.run()
        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)

    # Add cron job
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

    logger.info(
        f"Daemon started. Running daily at "
        f"{config.schedule.cron_hour:02d}:{config.schedule.cron_minute:02d} "
        f"({config.schedule.timezone})"
    )
    logger.info("Press Ctrl+C to stop.")

    # Run once on startup
    logger.info("Running initial pipeline...")
    run_pipeline()

    scheduler.start()
