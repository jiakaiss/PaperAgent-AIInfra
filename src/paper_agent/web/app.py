"""FastAPI application factory."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from paper_agent.config import AppConfig, UserConfig
from paper_agent.storage.database import PaperDatabase

WEB_DIR = Path(__file__).parent
logger = logging.getLogger(__name__)


def _load_subscriptions_into_config(config: AppConfig) -> None:
    """Load active subscriptions from database and add to config.users.

    Avoids duplicates by checking existing user_ids.
    SMTP credentials are inherited from config.email (global email config).
    """
    db = PaperDatabase(config.storage.db_path)
    subscriptions = db.load_active_subscriptions()

    existing_user_ids = {u.user_id for u in config.users}

    # Check if global email config is properly configured
    email_enabled = config.email.enabled
    if email_enabled:
        # Check for missing critical fields
        missing = []
        if not config.email.smtp_host:
            missing.append("smtp_host")
        if not config.email.smtp_user:
            missing.append("smtp_user")
        if not config.email.smtp_password:
            missing.append("smtp_password")
        if missing:
            logger.warning(
                f"Email config enabled but missing fields: {', '.join(missing)}. "
                f"Subscription users may not receive emails."
            )

    for sub in subscriptions:
        email = sub["email"]
        if email not in existing_user_ids:
            # Build email notify config with SMTP credentials from global config
            if email_enabled:
                email_notify = {
                    "enabled": True,
                    "recipients": [email],
                    "smtp_host": config.email.smtp_host,
                    "smtp_port": config.email.smtp_port,
                    "smtp_user": config.email.smtp_user,
                    "smtp_password": config.email.smtp_password,
                    "sender": config.email.sender,
                    "use_tls": config.email.use_tls,
                }
            else:
                email_notify = {"enabled": False, "recipients": [email]}
                logger.warning(
                    f"Global email config not configured, subscription user '{email}' will not receive emails"
                )

            user_config = UserConfig(
                user_id=email,
                display_name=email,
                subscriptions={"sub_domains": sub["sub_domains"]},
                notify={"email": email_notify},
            )
            config.users.append(user_config)
            existing_user_ids.add(email)
            logger.info(f"Loaded subscription user '{email}' from database")

    if subscriptions:
        logger.info(f"Loaded {len(subscriptions)} subscription(s) from database")


def create_app(config: AppConfig) -> FastAPI:
    """Build and return a configured FastAPI application."""
    app = FastAPI(title="Paper Agent", docs_url=None, redoc_url=None)
    app.state.config = config

    # Load subscriptions from database on startup
    _load_subscriptions_into_config(config)

    # Mount static assets
    app.mount(
        "/static",
        StaticFiles(directory=str(WEB_DIR / "static")),
        name="static",
    )

    # Jinja2 templates
    templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))
    app.state.templates = templates

    # Register route handlers
    from paper_agent.web.routes import router

    app.include_router(router)

    return app
