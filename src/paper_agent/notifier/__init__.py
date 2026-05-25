"""Notifier registry and factory."""

from __future__ import annotations

import logging

from paper_agent.config import NotifyConfig
from paper_agent.notifier.dingtalk_notifier import DingTalkNotifier
from paper_agent.notifier.email_notifier import EmailNotifier
from paper_agent.notifier.feishu_notifier import FeishuNotifier
from paper_agent.notifier.wecom_notifier import WeComNotifier

logger = logging.getLogger(__name__)

# Type alias for notifier protocol
from paper_agent.notifier.base import Notifier


def create_notifiers(config: NotifyConfig) -> list[Notifier]:
    """Create enabled notifiers from config."""
    notifiers: list[Notifier] = []

    if config.email.enabled:
        notifiers.append(EmailNotifier(config.email))
    if config.wecom.enabled:
        notifiers.append(WeComNotifier(config.wecom))
    if config.feishu.enabled:
        notifiers.append(FeishuNotifier(config.feishu))
    if config.dingtalk.enabled:
        notifiers.append(DingTalkNotifier(config.dingtalk))

    if not notifiers:
        logger.warning("No notifiers enabled. Check your config.yaml notify section.")

    return notifiers


def get_notifier_by_name(name: str, config: NotifyConfig) -> Notifier | None:
    """Get a specific notifier by name (for test command)."""
    mapping = {
        "email": EmailNotifier(config.email),
        "wecom": WeComNotifier(config.wecom),
        "feishu": FeishuNotifier(config.feishu),
        "dingtalk": DingTalkNotifier(config.dingtalk),
    }
    return mapping.get(name)


__all__ = [
    "Notifier",
    "create_notifiers",
    "get_notifier_by_name",
    "EmailNotifier",
    "WeComNotifier",
    "FeishuNotifier",
    "DingTalkNotifier",
]
