"""Tests for config loading."""

import os
import tempfile

import pytest
import yaml

from paper_agent.config import (
    AppConfig,
    UserConfig,
    SubscriptionConfig,
    UserNotifyConfig,
    UserThresholdsConfig,
    FeishuNotifierConfig,
    load_config,
)


def test_default_config():
    cfg = AppConfig()
    assert cfg.fetch.max_results == 200
    assert cfg.scoring.model == "claude-haiku-4-5"
    assert cfg.schedule.cron_hour == 9
    assert cfg.storage.db_path == "paper_agent.db"
    assert cfg.users == []


def test_user_config():
    user = UserConfig(
        user_id="alice",
        display_name="Alice",
        subscriptions=SubscriptionConfig(sub_domains=["quantization", "sparsity"]),
        thresholds=UserThresholdsConfig(min_relevance=7.0, top_n=10),
    )
    assert user.user_id == "alice"
    assert user.subscriptions.sub_domains == ["quantization", "sparsity"]
    assert user.thresholds.min_relevance == 7.0
    assert user.thresholds.top_n == 10


def test_subscription_all():
    sub = SubscriptionConfig(sub_domains=["all"])
    assert sub.sub_domains == ["all"]


def test_app_config_with_users():
    cfg = AppConfig(
        users=[
            UserConfig(user_id="alice", display_name="Alice"),
            UserConfig(user_id="bob", display_name="Bob"),
        ]
    )
    assert len(cfg.users) == 2
    assert cfg.users[0].user_id == "alice"
    assert cfg.users[1].user_id == "bob"


def test_duplicate_user_ids_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        AppConfig(
            users=[
                UserConfig(user_id="alice"),
                UserConfig(user_id="alice"),
            ]
        )


def test_load_config_from_file():
    data = {
        "fetch": {"max_results": 50, "days_back": 3},
        "scoring": {"model": "claude-sonnet-4-5"},
        "users": [
            {
                "user_id": "test_user",
                "display_name": "Test",
                "subscriptions": {"sub_domains": ["quantization"]},
                "thresholds": {"min_relevance": 8.0},
            }
        ],
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f)
        config_path = f.name

    try:
        cfg = load_config(config_path)
        assert cfg.fetch.max_results == 50
        assert cfg.fetch.days_back == 3
        assert cfg.scoring.model == "claude-sonnet-4-5"
        assert len(cfg.users) == 1
        assert cfg.users[0].user_id == "test_user"
        assert cfg.users[0].subscriptions.sub_domains == ["quantization"]
        assert cfg.users[0].thresholds.min_relevance == 8.0
        # Defaults should still apply for unspecified fields
        assert cfg.schedule.cron_hour == 9
    finally:
        os.unlink(config_path)


def test_env_var_interpolation():
    os.environ["TEST_API_KEY"] = "sk-test-12345"

    from paper_agent.config import _interpolate_env

    result = _interpolate_env("key=${TEST_API_KEY}")
    assert result == "key=sk-test-12345"

    del os.environ["TEST_API_KEY"]


def test_env_var_missing_non_strict():
    """When strict=False, missing env vars become empty strings."""
    from paper_agent.config import _interpolate_env

    os.environ.pop("NONEXISTENT_VAR_XYZ", None)
    result = _interpolate_env("value=${NONEXISTENT_VAR_XYZ}")
    assert result == "value="


def test_env_var_missing_strict():
    """When strict=True, missing env vars raise ValueError."""
    from paper_agent.config import _interpolate_env

    os.environ.pop("NONEXISTENT_VAR_XYZ", None)
    with pytest.raises(ValueError, match="NONEXISTENT_VAR_XYZ"):
        _interpolate_env("value=${NONEXISTENT_VAR_XYZ}", strict=True)
