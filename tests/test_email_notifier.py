"""Tests for the EmailNotifier — verifies plumbing from config to rendered HTML.

Tests inspect the MIME message body directly via ``_build_message`` so they
don't need to mock SMTP. Network calls in ``notify()`` are exercised
separately via the smtplib patch.
"""

from datetime import datetime
from unittest.mock import patch

from paper_agent.config import EmailNotifierConfig
from paper_agent.models import Paper, ScoredPaper
from paper_agent.notifier.email_notifier import EmailNotifier


def _make_scored_paper() -> ScoredPaper:
    paper = Paper(
        arxiv_id="2401.00001v1",
        title="Test Paper",
        authors=["Alice"],
        abstract="Abstract.",
        published=datetime(2024, 1, 15),
        categories=["cs.LG"],
        pdf_url="https://arxiv.org/pdf/2401.00001v1",
        abs_url="https://arxiv.org/abs/2401.00001v1",
    )
    return ScoredPaper(
        paper=paper,
        relevance_score=8.0,
        quality_score=7.0,
        summary_zh="测试摘要。",
        sub_domain_tags=("quantization",),
    )


def _email_config(**overrides) -> EmailNotifierConfig:
    data = {
        "enabled": True,
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_user": "system@example.com",
        "smtp_password": "secret",
        "sender": "noreply@example.com",
        "recipients": ["user@example.com"],
        "use_tls": True,
    }
    data.update(overrides)
    return EmailNotifierConfig(**data)


def _extract_html_body(msg) -> str:
    """Pull the decoded text/html payload out of a MIMEMultipart message."""
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            return part.get_payload(decode=True).decode("utf-8")
    raise AssertionError("no text/html part found")


def test_email_notifier_forwards_web_url_into_rendered_html():
    """Notifier must pass ``config.web_url`` through to ``format_email_html`` so
    the rendered body contains the operator's web URL.

    Regression guard for the email-header-web-link change: if the notifier
    stops forwarding ``web_url``, the digest email loses its top-of-message
    'browse on web' CTA and recipients have no path back to the web UI.
    """
    config = _email_config(web_url="https://papers.example.com/")
    notifier = EmailNotifier(config)

    msg = notifier._build_message([_make_scored_paper()])
    body = _extract_html_body(msg)

    assert "https://papers.example.com/" in body
    assert "在网页中浏览全部论文" in body


def test_email_notifier_omits_web_link_when_web_url_empty():
    """Default (empty ``web_url``) ⇒ no header link rendered."""
    config = _email_config()  # web_url defaults to ""
    notifier = EmailNotifier(config)

    msg = notifier._build_message([_make_scored_paper()])
    body = _extract_html_body(msg)

    assert "在网页中浏览全部论文" not in body


def test_email_notifier_notify_path_invokes_smtp():
    """End-to-end: ``notify()`` opens SMTP, logs in, and calls sendmail once."""
    config = _email_config(web_url="https://papers.example.com/")
    notifier = EmailNotifier(config)

    calls: dict[str, object] = {}

    class _FakeSMTP:
        def __init__(self, host, port):
            calls["host"] = host
            calls["port"] = port

        def starttls(self):
            calls["starttls"] = True

        def login(self, user, pw):
            calls["login_user"] = user

        def sendmail(self, sender, recipients, body):
            calls["sender"] = sender
            calls["recipients"] = recipients
            calls["body_len"] = len(body)

        def quit(self):
            calls["quit"] = True

    with patch("paper_agent.notifier.email_notifier.smtplib.SMTP", _FakeSMTP):
        assert notifier.notify([_make_scored_paper()]) is True

    assert calls["host"] == "smtp.example.com"
    assert calls["login_user"] == "system@example.com"
    assert calls["recipients"] == ["user@example.com"]
    assert calls.get("starttls") is True
    assert calls.get("quit") is True
    # Body should be a non-empty SMTP wire payload.
    assert calls["body_len"] > 0
