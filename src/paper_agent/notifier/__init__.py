"""Notifier registry and factory."""

from __future__ import annotations

import logging
from typing import Any

from paper_agent.config import UserNotifyConfig
from paper_agent.notifier.base import Notifier
from paper_agent.notifier.email_notifier import EmailNotifier

logger = logging.getLogger(__name__)

# Registry: name -> (notifier class, config attribute on UserNotifyConfig)
_REGISTRY: dict[str, tuple[type[Any], str]] = {
    "email": (EmailNotifier, "email"),
}


def create_notifiers_for_user(config: UserNotifyConfig) -> list[Notifier]:
    """Create enabled notifiers for a single user."""
    notifiers: list[Notifier] = []
    for _name, (cls, attr) in _REGISTRY.items():
        sub_config = getattr(config, attr)
        if sub_config.enabled:
            notifiers.append(cls(sub_config))
    return notifiers


def get_notifier_by_name(name: str, config: UserNotifyConfig) -> Notifier | None:
    """Get a specific notifier by name (for test command)."""
    entry = _REGISTRY.get(name)
    if entry is None:
        return None
    cls, attr = entry
    return cls(getattr(config, attr))


__all__ = [
    "Notifier",
    "create_notifiers_for_user",
    "get_notifier_by_name",
    "EmailNotifier",
]
