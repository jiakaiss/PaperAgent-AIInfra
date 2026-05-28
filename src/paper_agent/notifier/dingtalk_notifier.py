"""钉钉 (DingTalk) webhook notifier."""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
import urllib.parse

import base64

import requests

from paper_agent.config import DingTalkNotifierConfig
from paper_agent.formatter.templates import format_markdown, split_markdown_chunks
from paper_agent.models import ScoredPaper

logger = logging.getLogger(__name__)


class DingTalkNotifier:
    """Sends paper digest via 钉钉 webhook."""

    def __init__(self, config: DingTalkNotifierConfig):
        self.config = config

    @property
    def name(self) -> str:
        return "dingtalk"

    def _get_signed_url(self) -> str:
        """Generate signed webhook URL (钉钉 requires HMAC-SHA256)."""
        if not self.config.secret:
            return self.config.webhook_url

        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{self.config.secret}"

        hmac_code = hmac.new(
            self.config.secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()

        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))

        return f"{self.config.webhook_url}&timestamp={timestamp}&sign={sign}"

    def _send_message(self, content: str) -> bool:
        url = self._get_signed_url()

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": "AI Infra 论文日报",
                "text": content,
            },
        }

        try:
            resp = requests.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if data.get("errcode", 0) != 0:
                logger.error(f"DingTalk API error: {data}")
                return False

            return True
        except Exception as e:
            logger.error(f"Failed to send DingTalk message: {e}")
            return False

    def notify(self, papers: list[ScoredPaper]) -> bool:
        if not self.config.enabled:
            logger.debug("DingTalk notifier disabled")
            return True

        if not self.config.webhook_url:
            logger.warning("DingTalk webhook URL not configured")
            return False

        content = format_markdown(papers)
        # DingTalk markdown limit ~20KB, use conservative 18KB
        chunks = split_markdown_chunks(content, max_bytes=18000)

        all_ok = True
        for i, chunk in enumerate(chunks):
            logger.info(f"Sending DingTalk message {i + 1}/{len(chunks)}...")
            if not self._send_message(chunk):
                all_ok = False

        if all_ok:
            logger.info(f"DingTalk notification sent ({len(chunks)} messages)")
        return all_ok

    def send_test(self) -> bool:
        content = "## ✅ Paper Agent 测试\n\n钉钉 Webhook 配置测试成功！"
        return self._send_message(content)
