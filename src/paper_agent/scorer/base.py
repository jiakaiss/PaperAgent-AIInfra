"""Scorer protocol definition."""

from __future__ import annotations

from typing import Protocol

from paper_agent.models import Paper, ScoredPaper


class Scorer(Protocol):
    """Protocol for paper scorers."""

    def score(self, papers: list[Paper]) -> list[ScoredPaper]:
        """Score a list of papers and return those with scores."""
        ...
