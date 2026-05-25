"""Notifier protocol definition."""

from __future__ import annotations

from typing import Protocol

from paper_agent.models import ScoredPaper


class Notifier(Protocol):
    """Protocol for notification channels."""

    @property
    def name(self) -> str:
        """Name of this notifier."""
        ...

    def notify(self, papers: list[ScoredPaper]) -> bool:
        """Send notification. Returns True on success."""
        ...
