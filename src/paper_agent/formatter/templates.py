"""Template rendering for notifications."""

from __future__ import annotations

from datetime import datetime

from paper_agent.models import IMPACT_TIERS, ScoredPaper

# zh labels for impact tier section headers (per design decision: tier
# headers are localized in zh to match summary_zh).
TIER_LABELS_ZH: dict[str, str] = {
    "breakthrough": "重磅突破",
    "solid": "稳健工作",
    "incremental": "渐进改进",
}

# Inline CSS per tier — email clients require styles inline. Mirrors the
# web UI's tier-* classes but expressed as ready-to-substitute fragments.
_TIER_STYLE = {
    "breakthrough": {
        "border": "border-left: 4px solid #f59e0b;",
        "opacity": "",
        "badge_bg": "#fde68a",
        "badge_fg": "#92400e",
    },
    "solid": {
        "border": "",
        "opacity": "",
        "badge_bg": "#e5e7eb",
        "badge_fg": "#374151",
    },
    "incremental": {
        "border": "",
        "opacity": "opacity: 0.78;",
        "badge_bg": "#f3f4f6",
        "badge_fg": "#9ca3af",
    },
}


def format_paper_line(sp: ScoredPaper, index: int) -> str:
    """Format a single paper as a compact line for messaging.

    Includes the impact tier as a prefix marker so email recipients
    also see the tiering signal.
    """
    tier = sp.impact_tier if sp.impact_tier in TIER_LABELS_ZH else "solid"
    tier_marker = TIER_LABELS_ZH[tier]
    parts = [
        f"**[{tier_marker}] {index}. {sp.paper.title}**",
        f"   📊 相关度: {sp.relevance_score:.1f}/10  质量: {sp.quality_score:.1f}/10",
        f"   📝 {sp.summary_zh}",
    ]
    if sp.key_contributions:
        bullets = "; ".join(sp.key_contributions)
        parts.append(f"   ✨ 关键贡献: {bullets}")
    if sp.problem_statement_zh:
        parts.append(f"   🎯 问题: {sp.problem_statement_zh}")
    if sp.methods_zh:
        parts.append(f"   🛠 方法: {sp.methods_zh}")
    parts.append(f"   🏷️ {sp.sub_domain_display}")
    parts.append(f"   🔗 [论文]({sp.paper.abs_url}) | [PDF]({sp.paper.pdf_url})")
    return "\n".join(parts)


def format_markdown(papers: list[ScoredPaper], title: str | None = None) -> str:
    """Format papers as Markdown for webhook messages."""
    if not papers:
        return "今日无符合条件的高质量 AI Infra 论文。"

    date_str = datetime.now().strftime("%Y-%m-%d")
    header = title or f"🤖 AI Infra 论文日报 - {date_str}"

    lines = [f"# {header}\n", f"共筛选出 **{len(papers)}** 篇高质量论文：\n"]

    for i, sp in enumerate(papers, 1):
        lines.append(format_paper_line(sp, i))
        lines.append("")

    lines.append("---")
    lines.append("_由 Paper Agent 自动生成推送_")

    return "\n".join(lines)


def _group_papers_by_tier(
    papers: list[ScoredPaper],
) -> list[tuple[str, list[ScoredPaper]]]:
    """Group papers into tier-ordered sections (breakthrough → solid → incremental).

    Empty sections are skipped. Unknown tiers (NULL / typo) bucket into 'solid'.
    """
    buckets: dict[str, list[ScoredPaper]] = {tier: [] for tier in IMPACT_TIERS}
    for sp in papers:
        tier = sp.impact_tier if sp.impact_tier in buckets else "solid"
        buckets[tier].append(sp)
    return [(tier, papers) for tier, papers in buckets.items() if papers]


def _citation_badge(sp: ScoredPaper) -> str:
    """Render the inline "📈 N citations" badge, or empty when count is 0.

    Older-works papers (paper_kind="older") additionally get a "🔖 重要老作"
    marker next to the citation count so users can visually distinguish
    surfaced classics from fresh papers in the mixed list.
    """
    parts: list[str] = []
    if sp.citation_count and sp.citation_count > 0:
        parts.append(
            f'<span style="background:#fef3c7; color:#92400e; padding:2px 8px; '
            f'border-radius:12px; font-size:12px;">'
            f"📈 {sp.citation_count} citations</span>"
        )
    if sp.paper_kind == "older":
        parts.append(
            '<span style="background:#fce7f3; color:#9d174d; padding:2px 8px; '
            'border-radius:12px; font-size:12px;">🔖 重要老作</span>'
        )
    return " ".join(parts)


def _paper_row(sp: ScoredPaper, index: int) -> str:
    """Render one paper as an HTML table row with per-tier styling."""
    authors = ", ".join(sp.paper.authors[:5])
    if len(sp.paper.authors) > 5:
        authors += " et al."

    tag_badges = (
        " ".join(
            f'<span style="background:#fff3e0; color:#e65100; padding:2px 8px; '
            f'border-radius:12px; font-size:11px; margin-right:4px;">{tag}</span>'
            for tag in sp.sub_domain_tags
        )
        or '<span style="color:#999; font-size:11px;">general</span>'
    )

    tier = sp.impact_tier if sp.impact_tier in _TIER_STYLE else "solid"
    style = _TIER_STYLE[tier]
    cell_inline_style = (
        f"padding:12px 8px; border-bottom:1px solid #eee; {style['border']} {style['opacity']}"
    )

    # Structured insights — each block hidden if its source field is empty.
    # Visual styling matches the web UI: colored badge + left border +
    # tinted background. All styles inlined because email clients reliably
    # support only inline CSS (Gmail strips <style> tags in some cases).
    contributions_html = ""
    if sp.key_contributions:
        bullets = "".join(
            f'<li style="margin-bottom:3px; color:#1f2937;">{c}</li>' for c in sp.key_contributions
        )
        contributions_html = f"""
                <div style="margin-top:10px; padding:8px 12px;
                            background:#ecfdf5; border-left:3px solid #10b981;
                            border-radius:4px; font-size:13px; line-height:1.55;">
                    <span style="display:inline-block; background:#10b981;
                                 color:white; font-weight:700; font-size:11px;
                                 padding:2px 8px; border-radius:999px;
                                 letter-spacing:0.02em;">
                        关键贡献
                    </span>
                    <ul style="margin:6px 0 0 18px; padding:0;">{bullets}</ul>
                </div>"""

    problem_html = ""
    if sp.problem_statement_zh:
        problem_html = f"""
                <div style="margin-top:8px; padding:8px 12px;
                            background:#eff6ff; border-left:3px solid #3b82f6;
                            border-radius:4px; color:#1e3a8a; font-size:13px;
                            line-height:1.55;">
                    <span style="display:inline-block; background:#3b82f6;
                                 color:white; font-weight:700; font-size:11px;
                                 padding:2px 8px; border-radius:999px;
                                 margin-right:6px; letter-spacing:0.02em;">
                        问题
                    </span>
                    {sp.problem_statement_zh}
                </div>"""

    methods_html = ""
    if sp.methods_zh:
        methods_html = f"""
                <div style="margin-top:8px; padding:8px 12px;
                            background:#faf5ff; border-left:3px solid #a855f7;
                            border-radius:4px; color:#581c87; font-size:13px;
                            line-height:1.55;">
                    <span style="display:inline-block; background:#a855f7;
                                 color:white; font-weight:700; font-size:11px;
                                 padding:2px 8px; border-radius:999px;
                                 margin-right:6px; letter-spacing:0.02em;">
                        方法
                    </span>
                    {sp.methods_zh}
                </div>"""

    return f"""
        <tr>
            <td style="text-align:center; padding:12px 8px; border-bottom:1px solid #eee;
                       {style["opacity"]}">
                <strong>{index}</strong>
            </td>
            <td style="{cell_inline_style}">
                <a href="{sp.paper.abs_url}"
                   style="color:#1a73e8; text-decoration:none; font-weight:bold;">
                    {sp.paper.title}
                </a>
                <div style="color:#666; font-size:13px; margin-top:4px;">
                    {authors}
                </div>
                <div style="color:#333; font-size:13px; margin-top:6px;">
                    {sp.summary_zh}
                </div>{contributions_html}{problem_html}{methods_html}
                <div style="margin-top:8px;">
                    <span style="background:#e8f5e9; color:#2e7d32; padding:2px 8px;
                                 border-radius:12px; font-size:12px;">
                        相关度 {sp.relevance_score:.1f}
                    </span>
                    <span style="background:#e3f2fd; color:#1565c0; padding:2px 8px;
                                 border-radius:12px; font-size:12px;">
                        质量 {sp.quality_score:.1f}
                    </span>
                    {_citation_badge(sp)}
                    {tag_badges}
                </div>
            </td>
        </tr>"""


def _tier_section(tier: str, papers: list[ScoredPaper], start_index: int) -> str:
    """Render one tier section: header row + a row per paper in it."""
    style = _TIER_STYLE[tier]
    label = TIER_LABELS_ZH[tier]
    header = f"""
        <tr>
            <td colspan="2" style="padding:16px 8px 6px;
                                   border-bottom:2px solid #ddd;">
                <span style="background:{style["badge_bg"]}; color:{style["badge_fg"]};
                             padding:4px 12px; border-radius:999px; font-weight:600;
                             font-size:13px; letter-spacing:0.02em;">
                    {label}
                </span>
                <span style="color:#888; font-size:12px; margin-left:8px;">
                    {len(papers)} 篇
                </span>
            </td>
        </tr>"""
    rows = [_paper_row(sp, start_index + i) for i, sp in enumerate(papers)]
    return header + "".join(rows)


def _older_works_section(papers: list[ScoredPaper], start_index: int) -> str:
    """Render the "重要老作" section: distinct header + paper rows.

    Visually separated from the tier groups by a deeper-tinted header bar
    so users immediately recognize this is curated older content, not new
    arXiv submissions. Citation badges (rendered by ``_paper_row`` via
    ``_citation_badge``) carry the actual numeric impact signal.
    """
    if not papers:
        return ""
    header = f"""
        <tr>
            <td colspan="2" style="padding:20px 8px 8px;
                                   border-bottom:2px solid #be185d;">
                <span style="background:#fce7f3; color:#9d174d;
                             padding:6px 14px; border-radius:999px;
                             font-weight:700; font-size:14px;
                             letter-spacing:0.02em;">
                    🔖 重要老作 / Important Older Works
                </span>
                <span style="color:#888; font-size:12px; margin-left:8px;">
                    {len(papers)} 篇
                </span>
            </td>
        </tr>"""
    rows = [_paper_row(sp, start_index + i) for i, sp in enumerate(papers)]
    return header + "".join(rows)


def format_email_html(papers: list[ScoredPaper], unsubscribe_url: str = "") -> str:
    """Format papers as HTML email grouped by impact tier.

    Splits the input by ``paper_kind`` so the older-works track gets its own
    visually-distinct section after the regular tier groups. Callers don't
    need to think about the split — they pass everything in one list and
    the formatter routes papers based on their stored ``paper_kind``.
    """
    if not papers:
        return "<p>今日无符合条件的高质量 AI Infra 论文。</p>"

    fresh = [sp for sp in papers if sp.paper_kind != "older"]
    older = [sp for sp in papers if sp.paper_kind == "older"]

    date_str = datetime.now().strftime("%Y-%m-%d")

    sections: list[str] = []
    idx = 1
    for tier, tier_papers in _group_papers_by_tier(fresh):
        sections.append(_tier_section(tier, tier_papers, idx))
        idx += len(tier_papers)
    if older:
        sections.append(_older_works_section(older, idx))
        idx += len(older)

    unsubscribe_html = ""
    if unsubscribe_url:
        unsubscribe_html = f"""
    <p style=\"color:#999; font-size:12px; margin-top:10px; text-align:center;\">
        不想继续收到推送？<a href=\"{unsubscribe_url}\" style=\"color:#999;\">取消订阅</a>
    </p>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: 'Times New Roman', 'Microsoft YaHei', '微软雅黑', serif;
             max-width: 800px; margin: 0 auto; padding: 20px;">
    <h1 style="color:#1a73e8; border-bottom:2px solid #1a73e8; padding-bottom:10px;">
        🤖 AI Infra 论文日报
    </h1>
    <p style="color:#666;">📅 {date_str} | 共筛选出 <strong>{len(papers)}</strong> 篇高质量论文</p>
    <table style="width:100%; border-collapse:collapse;">
        {"".join(sections)}
    </table>
    <p style="color:#999; font-size:12px; margin-top:20px; text-align:center;">
        由 Paper Agent 自动生成推送
    </p>
    {unsubscribe_html}
</body>
</html>"""


def split_markdown_chunks(text: str, max_bytes: int = 3800) -> list[str]:
    """Split markdown text into chunks that fit within byte limits.

    Used for platforms like 企业微信 (4096 byte limit) to avoid truncation.
    Splits on paper boundaries (double newline after a paper block).
    """
    if len(text.encode("utf-8")) <= max_bytes:
        return [text]

    chunks: list[str] = []
    current_chunk = ""

    # Split by paper entries (separated by blank lines after links)
    blocks = text.split("\n\n")

    for block in blocks:
        test = current_chunk + ("\n\n" if current_chunk else "") + block
        if len(test.encode("utf-8")) > max_bytes and current_chunk:
            chunks.append(current_chunk)
            current_chunk = block
        else:
            current_chunk = test

    if current_chunk:
        chunks.append(current_chunk)

    # Add part numbers if multiple chunks
    if len(chunks) > 1:
        chunks = [f"[{i + 1}/{len(chunks)}]\n{c}" for i, c in enumerate(chunks)]

    return chunks
