"""Email notifier using SMTP."""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from paper_agent.config import EmailNotifierConfig
from paper_agent.formatter.templates import format_email_html
from paper_agent.models import ScoredPaper

logger = logging.getLogger(__name__)


class EmailNotifier:
    """Sends paper digest via email."""

    def __init__(self, config: EmailNotifierConfig):
        self.config = config

    @property
    def name(self) -> str:
        return "email"

    def _build_message(self, papers: list[ScoredPaper]) -> MIMEMultipart:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🤖 AI Infra 论文日报 - {len(papers)} 篇精选"
        msg["From"] = self.config.sender or self.config.smtp_user
        msg["To"] = ", ".join(self.config.recipients)

        html_content = format_email_html(papers, unsubscribe_url=self.config.unsubscribe_url)
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        return msg

    def notify(self, papers: list[ScoredPaper]) -> bool:
        if not self.config.enabled:
            logger.debug("Email notifier disabled")
            return True

        if not self.config.recipients:
            logger.warning("No email recipients configured")
            return False

        try:
            msg = self._build_message(papers)

            if self.config.use_tls:
                server = smtplib.SMTP(self.config.smtp_host, self.config.smtp_port)
                server.starttls()
            else:
                server = smtplib.SMTP(self.config.smtp_host, self.config.smtp_port)

            if self.config.smtp_user and self.config.smtp_password:
                server.login(self.config.smtp_user, self.config.smtp_password)

            server.sendmail(
                self.config.sender or self.config.smtp_user,
                self.config.recipients,
                msg.as_string(),
            )
            server.quit()

            logger.info(f"Email sent to {len(self.config.recipients)} recipients")
            return True

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    def send_test(self) -> bool:
        """Send a test email."""
        test_msg = MIMEMultipart("alternative")
        test_msg["Subject"] = "🧪 Paper Agent 测试邮件"
        test_msg["From"] = self.config.sender or self.config.smtp_user
        test_msg["To"] = ", ".join(self.config.recipients)

        html = (
            "<html><body>"
            "<h2>✅ Paper Agent 邮件配置测试成功！</h2>"
            "<p>如果你收到这封邮件，说明 SMTP 配置正确。</p>"
            "<p>配置好 arXiv 抓取和 Claude 打分后，你将每天收到 AI Infra 论文推送。</p>"
            "</body></html>"
        )
        test_msg.attach(MIMEText(html, "html", "utf-8"))

        try:
            if self.config.use_tls:
                server = smtplib.SMTP(self.config.smtp_host, self.config.smtp_port)
                server.starttls()
            else:
                server = smtplib.SMTP(self.config.smtp_host, self.config.smtp_port)

            if self.config.smtp_user and self.config.smtp_password:
                server.login(self.config.smtp_user, self.config.smtp_password)

            server.sendmail(
                self.config.sender or self.config.smtp_user,
                self.config.recipients,
                test_msg.as_string(),
            )
            server.quit()
            logger.info("Test email sent successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to send test email: {e}")
            return False
