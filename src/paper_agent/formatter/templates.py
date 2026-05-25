"""Template rendering for notifications."""

from __future__ import annotations

from datetime import datetime

from paper_agent.models import ScoredPaper


def format_paper_line(sp: ScoredPaper, index: int) -> str:
    """Format a single paper as a compact line for messaging."""
    stars_r = "★" * int(sp.relevance_score) + "☆" * (10 - int(sp.relevance_score))
    return (
        f"**{index}. {sp.paper.title}**\n"
        f"   📊 相关度: {sp.relevance_score:.1f}/10  质量: {sp.quality_score:.1f}/10\n"
        f"   📝 {sp.summary_zh}\n"
        f"   🏷️ {', '.join(sp.paper.categories)}\n"
        f"   🔗 [论文]({sp.paper.abs_url}) | [PDF]({sp.paper.pdf_url})"
    )


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
    lines.append(f"_由 Paper Agent 自动生成推送_")

    return "\n".join(lines)


def format_email_html(papers: list[ScoredPaper]) -> str:
    """Format papers as HTML email."""
    if not papers:
        return "<p>今日无符合条件的高质量 AI Infra 论文。</p>"

    date_str = datetime.now().strftime("%Y-%m-%d")

    rows = []
    for i, sp in enumerate(papers, 1):
        authors = ", ".join(sp.paper.authors[:5])
        if len(sp.paper.authors) > 5:
            authors += " et al."
        rows.append(f"""
        <tr>
            <td style="text-align:center; padding:12px 8px; border-bottom:1px solid #eee;">
                <strong>{i}</strong>
            </td>
            <td style="padding:12px 8px; border-bottom:1px solid #eee;">
                <a href="{sp.paper.abs_url}" style="color:#1a73e8; text-decoration:none; font-weight:bold;">
                    {sp.paper.title}
                </a>
                <div style="color:#666; font-size:13px; margin-top:4px;">
                    {authors}
                </div>
                <div style="color:#333; font-size:13px; margin-top:6px;">
                    {sp.summary_zh}
                </div>
                <div style="margin-top:6px;">
                    <span style="background:#e8f5e9; color:#2e7d32; padding:2px 8px; border-radius:12px; font-size:12px;">
                        相关度 {sp.relevance_score:.1f}
                    </span>
                    <span style="background:#e3f2fd; color:#1565c0; padding:2px 8px; border-radius:12px; font-size:12px;">
                        质量 {sp.quality_score:.1f}
                    </span>
                    <span style="background:#f5f5f5; color:#666; padding:2px 8px; border-radius:12px; font-size:12px;">
                        {', '.join(sp.paper.categories)}
                    </span>
                </div>
            </td>
        </tr>""")

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px;">
    <h1 style="color:#1a73e8; border-bottom:2px solid #1a73e8; padding-bottom:10px;">
        🤖 AI Infra 论文日报
    </h1>
    <p style="color:#666;">📅 {date_str} | 共筛选出 <strong>{len(papers)}</strong> 篇高质量论文</p>
    <table style="width:100%; border-collapse:collapse;">
        {''.join(rows)}
    </table>
    <p style="color:#999; font-size:12px; margin-top:20px; text-align:center;">
        由 Paper Agent 自动生成推送
    </p>
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
        chunks = [f"[{i+1}/{len(chunks)}]\n{c}" for i, c in enumerate(chunks)]

    return chunks
