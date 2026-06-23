"""Tests for subscription helper functions."""

from paper_agent.config import EmailNotifierConfig
from paper_agent.subscriptions import (
    build_subscription_email_config,
    is_email_configured,
    missing_email_config_fields,
    subscription_to_user_config,
)


def _email_config(**overrides) -> EmailNotifierConfig:
    data = {
        "enabled": True,
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_user": "system@example.com",
        "smtp_password": "secret",
        "sender": "noreply@example.com",
        "use_tls": True,
    }
    data.update(overrides)
    return EmailNotifierConfig(**data)


def test_missing_email_config_fields_when_complete():
    assert missing_email_config_fields(_email_config()) == []


def test_missing_email_config_fields_lists_critical_fields():
    missing = missing_email_config_fields(
        _email_config(smtp_host="", smtp_user="", smtp_password="")
    )
    assert missing == ["smtp_host", "smtp_user", "smtp_password"]


def test_is_email_configured_requires_enabled_and_credentials():
    assert is_email_configured(_email_config()) is True
    assert is_email_configured(_email_config(enabled=False)) is False
    assert is_email_configured(_email_config(smtp_password="")) is False


def test_build_subscription_email_config_copies_global_smtp_fields():
    config = build_subscription_email_config("user@example.com", _email_config(use_tls=False))
    assert config == {
        "enabled": True,
        "recipients": ["user@example.com"],
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_user": "system@example.com",
        "smtp_password": "secret",
        "sender": "noreply@example.com",
        "use_tls": False,
        "unsubscribe_url": "",
        "web_url": "",
    }


def test_build_subscription_email_config_propagates_web_url():
    config = build_subscription_email_config(
        "user@example.com",
        _email_config(),
        web_url="https://papers.example.com/",
    )
    assert config["web_url"] == "https://papers.example.com/"


def test_build_subscription_email_config_disabled_keeps_web_url_when_set():
    config = build_subscription_email_config(
        "user@example.com",
        _email_config(enabled=False),
        web_url="https://papers.example.com/",
    )
    assert config == {
        "enabled": False,
        "recipients": ["user@example.com"],
        "web_url": "https://papers.example.com/",
    }


def test_build_subscription_email_config_disabled_when_global_email_incomplete():
    config = build_subscription_email_config(
        "user@example.com",
        _email_config(enabled=False),
    )
    assert config == {"enabled": False, "recipients": ["user@example.com"]}


def test_subscription_to_user_config_uses_shared_email_config_builder():
    user = subscription_to_user_config(
        "user@example.com",
        ["quantization", "moe"],
        _email_config(smtp_port=465),
    )
    assert user.user_id == "user@example.com"
    assert user.display_name == "user@example.com"
    assert user.subscriptions.sub_domains == ["quantization", "moe"]
    assert user.notify.email.enabled is True
    assert user.notify.email.recipients == ["user@example.com"]
    assert user.notify.email.smtp_port == 465
    assert user.notify.email.smtp_user == "system@example.com"


def test_subscription_to_user_config_copies_web_url():
    """The web URL plumbed in by load_subscriptions_into_config must land on the user."""
    user = subscription_to_user_config(
        "user@example.com",
        ["quantization"],
        _email_config(),
        web_url="https://papers.example.com/",
    )
    assert user.notify.email.web_url == "https://papers.example.com/"
