"""Fetcher protocol definition."""

from __future__ import annotations

from typing import Protocol

from paper_agent.models import Paper


class Fetcher(Protocol):
    """Protocol for paper fetchers."""

    def fetch(self, max_results: int, days_back: int) -> list[Paper]:
        """Fetch recent papers from a source."""
        ...
