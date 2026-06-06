"""Tests for template formatting."""

from datetime import datetime

from paper_agent.formatter.templates import (
    format_email_html,
    format_markdown,
    split_markdown_chunks,
)
from paper_agent.models import Paper, ScoredPaper


def _make_scored_paper(idx: int = 1) -> ScoredPaper:
    paper = Paper(
        arxiv_id=f"2401.{idx:05d}v1",
        title=f"Test Paper {idx}: Distributed Training at Scale",
        authors=["Alice", "Bob", "Charlie"],
        abstract="A test abstract.",
        published=datetime(2024, 1, 15),
        categories=["cs.DC", "cs.LG"],
        pdf_url=f"https://arxiv.org/pdf/2401.{idx:05d}v1",
        abs_url=f"https://arxiv.org/abs/2401.{idx:05d}v1",
    )
    return ScoredPaper(
        paper=paper,
        relevance_score=8.5,
        quality_score=7.0,
        summary_zh="本文提出了一种新的分布式训练框架。",
        sub_domain_tags=("distributed_training", "parallelism"),
    )


def test_format_markdown():
    papers = [_make_scored_paper(1), _make_scored_paper(2)]
    result = format_markdown(papers)

    assert "AI Infra" in result
    assert "Test Paper 1" in result
    assert "Test Paper 2" in result
    assert "8.5" in result
    assert "distributed_training" in result


def test_format_markdown_empty():
    result = format_markdown([])
    assert "无" in result


def test_format_email_html():
    papers = [_make_scored_paper(1)]
    html = format_email_html(papers)

    assert "<html>" in html
    assert "Test Paper 1" in html
    assert "8.5" in html
    assert "distributed_training" in html


def test_email_html_uses_times_and_yahei():
    """Email body should declare Times New Roman (English) + Microsoft YaHei (Chinese)."""
    html = format_email_html([_make_scored_paper(1)])
    assert "'Times New Roman'" in html
    assert "'Microsoft YaHei'" in html
    # Old sans-serif stack should be gone
    assert "BlinkMacSystemFont" not in html
    assert "-apple-system" not in html


def test_format_markdown_has_no_html_font_family():
    """Markdown notifier output must not leak the email font-family declaration."""
    md = format_markdown([_make_scored_paper(1)])
    assert "font-family" not in md
    assert "Times New Roman" not in md


def test_split_markdown_chunks_short():
    text = "Short text"
    chunks = split_markdown_chunks(text, max_bytes=3800)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_split_markdown_chunks_long():
    # Create a long text that exceeds the byte limit
    lines = [f"Paper {i}: {'x' * 200}" for i in range(50)]
    text = "\n\n".join(lines)

    chunks = split_markdown_chunks(text, max_bytes=500)
    assert len(chunks) > 1
    # Each chunk should be within limit (approximately)
    for chunk in chunks:
        assert len(chunk.encode("utf-8")) < 1000  # some slack for chunk headers
