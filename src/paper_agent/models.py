"""Data models for papers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Paper:
    """A paper fetched from arXiv."""

    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    published: datetime
    categories: list[str]
    pdf_url: str
    abs_url: str

    @property
    def primary_category(self) -> str:
        return self.categories[0] if self.categories else "unknown"


@dataclass(frozen=True)
class ScoredPaper:
    """A paper with LLM-generated scores and summary."""

    paper: Paper
    relevance_score: float  # 0-10, relevance to AI Infra
    quality_score: float  # 0-10, overall quality/impact
    summary_zh: str  # One-line Chinese summary

    @property
    def total_score(self) -> float:
        """Weighted total score (relevance matters more)."""
        return self.relevance_score * 0.6 + self.quality_score * 0.4


def sort_by_score(papers: list[ScoredPaper]) -> list[ScoredPaper]:
    """Sort papers by total score, highest first."""
    return sorted(papers, key=lambda p: p.total_score, reverse=True)
