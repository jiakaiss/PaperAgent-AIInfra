"""Tests for delivery control configuration and unsubscribe helpers."""

import pytest

from paper_agent.config import (
    AppConfig,
    EmailNotifierConfig,
    ScheduleConfig,
    SubscriptionAccessConfig,
    SubscriptionDefaultsConfig,
    WebConfig,
)
from paper_agent.subscriptions import build_unsubscribe_url, subscription_to_user_config
from paper_agent.unsubscribe import sign_unsubscribe_token, verify_unsubscribe_token


def test_subscription_access_config_disabled_allows_missing_code():
    cfg = SubscriptionAccessConfig(enabled=False)
    assert cfg.is_valid_code(None) is True


def test_subscription_access_config_accepts_valid_code():
    cfg = SubscriptionAccessConfig(enabled=True, access_codes=["secret"])
    assert cfg.is_valid_code("secret") is True
    assert cfg.is_valid_code("wrong") is False


def test_subscription_access_config_requires_codes_when_enabled():
    with pytest.raises(ValueError, match="access_codes"):
        SubscriptionAccessConfig(enabled=True, access_codes=[])


def test_subscription_defaults_default_top_n_is_10():
    cfg = SubscriptionDefaultsConfig()
    assert cfg.default_top_n == 10


def test_schedule_interval_requires_positive_interval():
    with pytest.raises(ValueError, match="interval_minutes"):
        ScheduleConfig(mode="interval", interval_minutes=0)


def test_web_min_quality_can_be_disabled():
    assert WebConfig(min_quality=0).min_quality == 0
    assert WebConfig(min_quality=None).min_quality is None


def test_unsubscribe_token_validates_and_expires():
    token = sign_unsubscribe_token("user@example.com", "secret", now=100)
    assert verify_unsubscribe_token("user@example.com", token, "secret", 3600, now=200)
    assert not verify_unsubscribe_token("user@example.com", token, "wrong", 3600, now=200)
    assert not verify_unsubscribe_token("user@example.com", token, "secret", 50, now=200)


def test_build_unsubscribe_url_requires_base_url_and_secret():
    assert build_unsubscribe_url("user@example.com", "", "secret") == ""
    assert build_unsubscribe_url("user@example.com", "https://example.com", "") == ""
    url = build_unsubscribe_url("user@example.com", "https://example.com/", "secret")
    assert url.startswith("https://example.com/unsubscribe?")
    assert "email=user%40example.com" in url
    assert "token=" in url


def test_subscription_to_user_config_uses_default_top_n_and_unsubscribe_url():
    user = subscription_to_user_config(
        "user@example.com",
        ["quantization"],
        EmailNotifierConfig(
            enabled=True,
            smtp_host="smtp.example.com",
            smtp_user="system@example.com",
            smtp_password="secret",
        ),
        default_top_n=15,
        unsubscribe_url="https://example.com/unsubscribe?token=abc",
    )
    assert user.thresholds.top_n == 15
    assert user.notify.email.unsubscribe_url == "https://example.com/unsubscribe?token=abc"


def test_app_config_new_defaults():
    cfg = AppConfig()
    assert cfg.subscriptions.default_top_n == 10
    assert cfg.subscriptions.access.enabled is False
    assert cfg.web.min_quality == 5.0
    assert cfg.schedule.mode == "cron"
