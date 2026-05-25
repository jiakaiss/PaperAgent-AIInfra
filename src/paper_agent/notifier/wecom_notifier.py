"""企业微信 (WeCom) webhook notifier."""

from __future__ import annotations

import logging

import requests

from paper_agent.config import WeComNotifierConfig
from paper_agent.formatter.templates import format_markdown, split_markdown_chunks
from paper_agent.models import ScoredPaper

logger = logging.getLogger(__name__)


class WeComNotifier:
    """Sends paper digest via 企业微信 webhook."""

    def __init__(self, config: WeComNotifierConfig):
        self.config = config

    @property
    def name(self) -> str:
        return "wecom"

    def _send_message(self, content: str) -> bool:
        """Send a single markdown message to WeCom."""
        payload = {
            "msgtype": "markdown",
            "markdown": {"content": content},
        }

        try:
            resp = requests.post(
                self.config.webhook_url,
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("errcode", 0) != 0:
                logger.error(f"WeCom API error: {data}")
                return False

            return True
        except Exception as e:
            logger.error(f"Failed to send WeCom message: {e}")
            return False

    def notify(self, papers: list[ScoredPaper]) -> bool:
        if not self.config.enabled:
            logger.debug("WeCom notifier disabled")
            return True

        if not self.config.webhook_url:
            logger.warning("WeCom webhook URL not configured")
            return False

        content = format_markdown(papers)
        # WeCom markdown limit is 4096 bytes
        chunks = split_markdown_chunks(content, max_bytes=3800)

        all_ok = True
        for i, chunk in enumerate(chunks):
            logger.info(f"Sending WeCom message {i+1}/{len(chunks)}...")
            if not self._send_message(chunk):
                all_ok = False

        if all_ok:
            logger.info(f"WeCom notification sent ({len(chunks)} messages)")
        return all_ok

    def send_test(self) -> bool:
        """Send a test message."""
        content = "## ✅ Paper Agent 测试\n企业微信 Webhook 配置测试成功！"
        return self._send_message(content)
