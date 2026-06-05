"""飞书 (Feishu/Lark) webhook notifier."""

from __future__ import annotations

import logging
from datetime import datetime

import requests

from paper_agent.config import FeishuNotifierConfig
from paper_agent.models import ScoredPaper

logger = logging.getLogger(__name__)


class FeishuNotifier:
    """Sends paper digest via 飞书 webhook (rich text post format)."""

    def __init__(self, config: FeishuNotifierConfig):
        self.config = config

    @property
    def name(self) -> str:
        return "feishu"

    def _build_post(self, papers: list[ScoredPaper]) -> dict:
        """Build 飞书 rich text post message."""
        date_str = datetime.now().strftime("%Y-%m-%d")

        content_lines = []

        # Header line
        content_lines.append(
            [{"tag": "text", "text": f"共筛选出 {len(papers)} 篇高质量 AI Infra 论文"}]
        )
        content_lines.append([{"tag": "text", "text": ""}])

        for i, sp in enumerate(papers, 1):
            # Title as link
            content_lines.append(
                [{"tag": "a", "text": f"{i}. {sp.paper.title}", "href": sp.paper.abs_url}]
            )
            # Scores
            content_lines.append(
                [
                    {
                        "tag": "text",
                        "text": (
                            f"   📊 相关度: {sp.relevance_score:.1f}/10  "
                            f"质量: {sp.quality_score:.1f}/10"
                        ),
                    }
                ]
            )
            # Summary
            content_lines.append([{"tag": "text", "text": f"   📝 {sp.summary_zh}"}])
            # Categories
            content_lines.append(
                [{"tag": "text", "text": f"   🏷️ {', '.join(sp.paper.categories)}"}]
            )
            # Blank line separator
            content_lines.append([{"tag": "text", "text": ""}])

        return {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": f"🤖 AI Infra 论文日报 - {date_str}",
                        "content": content_lines,
                    }
                }
            },
        }

    def _send_message(self, payload: dict) -> bool:
        try:
            resp = requests.post(
                self.config.webhook_url,
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("code", -1) != 0 and data.get("StatusCode", -1) != 0:
                logger.error(f"Feishu API error: {data}")
                return False

            return True
        except Exception as e:
            logger.error(f"Failed to send Feishu message: {e}")
            return False

    def notify(self, papers: list[ScoredPaper]) -> bool:
        if not self.config.enabled:
            logger.debug("Feishu notifier disabled")
            return True

        if not self.config.webhook_url:
            logger.warning("Feishu webhook URL not configured")
            return False

        # 飞书 has a 30KB limit, split if too many papers
        if len(papers) > 15:
            # Send in batches of 15
            all_ok = True
            for start in range(0, len(papers), 15):
                batch = papers[start : start + 15]
                payload = self._build_post(batch)
                if not self._send_message(payload):
                    all_ok = False
            return all_ok

        payload = self._build_post(papers)
        ok = self._send_message(payload)
        if ok:
            logger.info("Feishu notification sent")
        return ok

    def send_test(self) -> bool:
        payload = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": "🧪 Paper Agent 测试",
                        "content": [[{"tag": "text", "text": "飞书 Webhook 配置测试成功！"}]],
                    }
                }
            },
        }
        return self._send_message(payload)
