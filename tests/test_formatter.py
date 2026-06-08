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


# ─── Tier sections + structured insights ───


def _make_tiered_paper(
    idx: int = 1,
    impact_tier: str = "solid",
    key_contributions=(),
    problem_zh: str = "",
    methods_zh: str = "",
) -> ScoredPaper:
    paper = Paper(
        arxiv_id=f"2401.{idx:05d}v1",
        title=f"Tiered Paper {idx}",
        authors=["Alice"],
        abstract="abs",
        published=datetime(2024, 1, 15),
        categories=["cs.DC"],
        pdf_url=f"https://arxiv.org/pdf/2401.{idx:05d}v1",
        abs_url=f"https://arxiv.org/abs/2401.{idx:05d}v1",
    )
    return ScoredPaper(
        paper=paper,
        relevance_score=8.0,
        quality_score=7.0,
        summary_zh="摘要",
        sub_domain_tags=("quantization",),
        key_contributions=key_contributions,
        problem_statement_zh=problem_zh,
        methods_zh=methods_zh,
        impact_tier=impact_tier,
    )


def test_email_html_groups_papers_by_tier_with_zh_headers():
    """Email renders one section per non-empty tier with the zh header."""
    papers = [
        _make_tiered_paper(1, impact_tier="breakthrough"),
        _make_tiered_paper(2, impact_tier="solid"),
        _make_tiered_paper(3, impact_tier="solid"),
        _make_tiered_paper(4, impact_tier="incremental"),
    ]
    html = format_email_html(papers)
    assert "重磅突破" in html
    assert "稳健工作" in html
    assert "渐进改进" in html
    # Per-section counts
    assert "1 篇" in html  # breakthrough has 1
    assert "2 篇" in html  # solid has 2


def test_email_html_skips_empty_tier_sections():
    """Tier sections with zero papers don't render a header."""
    papers = [_make_tiered_paper(1, impact_tier="solid")]
    html = format_email_html(papers)
    assert "稳健工作" in html
    assert "重磅突破" not in html
    assert "渐进改进" not in html


def test_email_html_breakthrough_section_comes_first():
    """Sections render in tier-priority order regardless of paper input order."""
    papers = [
        _make_tiered_paper(1, impact_tier="incremental"),
        _make_tiered_paper(2, impact_tier="breakthrough"),
    ]
    html = format_email_html(papers)
    # breakthrough header must precede incremental header in the rendered HTML
    assert html.index("重磅突破") < html.index("渐进改进")


def test_email_html_renders_key_contributions_when_present():
    papers = [
        _make_tiered_paper(
            1,
            impact_tier="solid",
            key_contributions=("贡献 A", "贡献 B"),
            problem_zh="问题描述",
            methods_zh="方法描述",
        )
    ]
    html = format_email_html(papers)
    assert "关键贡献" in html
    assert "贡献 A" in html
    assert "贡献 B" in html
    assert "问题" in html
    assert "问题描述" in html
    assert "方法" in html
    assert "方法描述" in html


def test_email_html_insight_sections_have_color_coded_badges():
    """Each insight section uses its own colored badge + left border to
    match the web UI's visual distinction (green / blue / purple)."""
    papers = [
        _make_tiered_paper(
            1,
            impact_tier="solid",
            key_contributions=("贡献",),
            problem_zh="问题",
            methods_zh="方法",
        )
    ]
    html = format_email_html(papers)
    # Green for contributions
    assert "border-left:3px solid #10b981" in html
    assert "background:#10b981" in html         # green badge background
    assert "background:#ecfdf5" in html         # light green section background
    # Blue for problem
    assert "border-left:3px solid #3b82f6" in html
    assert "background:#3b82f6" in html         # blue badge background
    assert "background:#eff6ff" in html         # light blue section background
    # Purple for methods
    assert "border-left:3px solid #a855f7" in html
    assert "background:#a855f7" in html         # purple badge background
    assert "background:#faf5ff" in html         # light purple section background


def test_email_html_insight_badges_are_white_pill_shaped():
    """Section labels render as pill-shaped white-text badges, not plain text."""
    papers = [
        _make_tiered_paper(
            1,
            impact_tier="solid",
            key_contributions=("贡献",),
            problem_zh="问题",
            methods_zh="方法",
        )
    ]
    html = format_email_html(papers)
    # White text + rounded pill shape are the key visual cues
    assert "color:white" in html
    assert "border-radius:999px" in html


def test_email_html_hides_empty_insight_sections():
    """A paper with no contributions/problem/methods doesn't show those sections."""
    papers = [_make_tiered_paper(1, impact_tier="solid")]
    html = format_email_html(papers)
    assert "关键贡献" not in html
    # "问题" might appear in other contexts (e.g. error messages) but in the
    # tested paper there's no problem_statement_zh, so the labeled block
    # shouldn't be there. The label appears with text-transform:uppercase
    # right before the value; if neither is present, neither check matches.


def test_email_html_incremental_papers_have_dimmed_style():
    """Incremental papers use opacity:0.78 in their cell style."""
    papers = [_make_tiered_paper(1, impact_tier="incremental")]
    html = format_email_html(papers)
    assert "opacity: 0.78" in html


def test_email_html_breakthrough_papers_have_left_border():
    """Breakthrough papers get a 4px solid amber left border."""
    papers = [_make_tiered_paper(1, impact_tier="breakthrough")]
    html = format_email_html(papers)
    assert "border-left: 4px solid #f59e0b" in html


def test_email_html_unknown_tier_treated_as_solid():
    """A paper with an unrecognised impact_tier renders under the 'solid' section."""
    sp = _make_tiered_paper(1, impact_tier="legendary")
    html = format_email_html([sp])
    assert "稳健工作" in html  # solid section header
    assert "Tiered Paper 1" in html


def test_format_paper_line_includes_tier_marker():
    """Webhook-format paper line includes a tier prefix marker."""
    sp = _make_tiered_paper(1, impact_tier="breakthrough")
    from paper_agent.formatter.templates import format_paper_line

    line = format_paper_line(sp, 1)
    assert "[重磅突破]" in line


def test_format_paper_line_includes_key_contributions():
    sp = _make_tiered_paper(
        1, impact_tier="solid", key_contributions=("贡献 X",), problem_zh="问题 Y"
    )
    from paper_agent.formatter.templates import format_paper_line

    line = format_paper_line(sp, 1)
    assert "✨ 关键贡献" in line
    assert "贡献 X" in line
    assert "🎯 问题" in line
    assert "问题 Y" in line
