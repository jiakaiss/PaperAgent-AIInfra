"""Helpers for web/CLI subscription users.

Subscription rows only store identity and preferences. Runtime UserConfig objects
inherit SMTP settings from the global AppConfig.email configuration.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from paper_agent.config import EmailNotifierConfig, UserConfig
from paper_agent.unsubscribe import sign_unsubscribe_token

if TYPE_CHECKING:
    from paper_agent.config import AppConfig

logger = logging.getLogger(__name__)


def missing_email_config_fields(email: EmailNotifierConfig) -> list[str]:
    """Return critical SMTP fields missing from an enabled email config."""
    missing = []
    if not email.smtp_host:
        missing.append("smtp_host")
    if not email.smtp_user:
        missing.append("smtp_user")
    if not email.smtp_password:
        missing.append("smtp_password")
    return missing


def is_email_configured(email: EmailNotifierConfig) -> bool:
    """Return True when global email config can send subscription emails."""
    return email.enabled and not missing_email_config_fields(email)


def build_subscription_email_config(
    email: str,
    global_email: EmailNotifierConfig,
    unsubscribe_url: str = "",
) -> dict:
    """Build a per-user email notify config for a subscription recipient."""
    if not is_email_configured(global_email):
        config = {"enabled": False, "recipients": [email]}
        if unsubscribe_url:
            config["unsubscribe_url"] = unsubscribe_url
        return config
    return {
        "enabled": True,
        "recipients": [email],
        "smtp_host": global_email.smtp_host,
        "smtp_port": global_email.smtp_port,
        "smtp_user": global_email.smtp_user,
        "smtp_password": global_email.smtp_password,
        "sender": global_email.sender,
        "use_tls": global_email.use_tls,
        "unsubscribe_url": unsubscribe_url,
    }


def build_unsubscribe_url(email: str, base_url: str, secret: str) -> str:
    """Build a signed unsubscribe URL, or return empty string if not configured."""
    if not base_url or not secret:
        return ""
    token = sign_unsubscribe_token(email, secret)
    return f"{base_url.rstrip('/')}/unsubscribe?{urlencode({'email': email, 'token': token})}"


def subscription_to_user_config(
    email: str,
    sub_domains: Sequence[str],
    global_email: EmailNotifierConfig,
    default_top_n: int = 10,
    unsubscribe_url: str = "",
) -> UserConfig:
    """Convert a subscription record into a runtime UserConfig."""
    return UserConfig(
        user_id=email,
        display_name=email,
        subscriptions={"sub_domains": list(sub_domains)},
        notify={"email": build_subscription_email_config(email, global_email, unsubscribe_url)},
        thresholds={"top_n": default_top_n},
    )


def load_subscriptions_into_config(config: AppConfig) -> int:
    """Load active subscription rows into ``config.users``.

    Returns the number of subscription rows loaded from storage. Existing
    user_ids are skipped to avoid duplicates.
    """
    from paper_agent.storage.database import PaperDatabase

    db = PaperDatabase(config.storage.db_path)
    subscriptions = db.load_active_subscriptions()
    existing_user_ids = {u.user_id for u in config.users}

    if config.email.enabled:
        missing = missing_email_config_fields(config.email)
        if missing:
            logger.warning(
                f"Email config enabled but missing fields: {', '.join(missing)}. "
                f"Subscription users may not receive emails."
            )

    for sub in subscriptions:
        email = sub["email"]
        if email in existing_user_ids:
            continue
        if not is_email_configured(config.email):
            logger.warning(
                "Global email config not configured, "
                f"subscription user '{email}' will not receive emails"
            )
        unsubscribe_url = build_unsubscribe_url(
            email,
            config.web.public_base_url,
            config.subscriptions.unsubscribe.secret,
        )
        if not unsubscribe_url:
            logger.warning(f"Unsubscribe link not configured for subscription user '{email}'")
        config.users.append(
            subscription_to_user_config(
                email,
                sub["sub_domains"],
                config.email,
                default_top_n=config.subscriptions.default_top_n,
                unsubscribe_url=unsubscribe_url,
            )
        )
        existing_user_ids.add(email)
        logger.info(f"Loaded subscription user '{email}' from database")

    if subscriptions:
        logger.info(f"Loaded {len(subscriptions)} subscription(s) from database")
    return len(subscriptions)
