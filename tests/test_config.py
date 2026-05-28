"""Tests for config loading."""

import os
import tempfile

import pytest
import yaml

from paper_agent.config import (
    AppConfig,
    PromptsConfig,
    ScoringConfig,
    SubscriptionConfig,
    UserConfig,
    UserThresholdsConfig,
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


# ─── New scoring config field tests ───


def test_scoring_config_defaults():
    """All new ScoringConfig fields have sensible defaults."""
    cfg = ScoringConfig()
    assert cfg.api_key is None
    assert cfg.base_url is None
    assert cfg.max_tokens == 4096
    assert cfg.temperature is None
    assert cfg.tool_choice == "auto"
    assert cfg.abstract_max_length == 800
    assert cfg.relevance_weight == 0.6
    assert cfg.quality_weight == 0.4
    assert cfg.prompts.system_prompt is None
    assert cfg.prompts.user_message_template is None


def test_scoring_config_custom_values():
    """ScoringConfig accepts all new fields."""
    cfg = ScoringConfig(
        api_key="sk-ant-test",
        base_url="https://proxy.example.com/v1",
        max_tokens=8192,
        temperature=0.3,
        tool_choice="tool",
        abstract_max_length=1200,
        relevance_weight=0.8,
        quality_weight=0.2,
        prompts=PromptsConfig(
            system_prompt="Custom prompt",
            user_message_template="Score {paper_count} papers:\n{papers}",
        ),
    )
    assert cfg.api_key == "sk-ant-test"
    assert cfg.base_url == "https://proxy.example.com/v1"
    assert cfg.max_tokens == 8192
    assert cfg.temperature == 0.3
    assert cfg.tool_choice == "tool"
    assert cfg.abstract_max_length == 1200
    assert cfg.relevance_weight == 0.8
    assert cfg.quality_weight == 0.2
    assert cfg.prompts.system_prompt == "Custom prompt"
    assert cfg.prompts.user_message_template == "Score {paper_count} papers:\n{papers}"


def test_scoring_config_api_key_env_interpolation():
    """api_key supports ${ENV_VAR} interpolation through YAML loading."""
    os.environ["TEST_SCORING_KEY"] = "sk-ant-interpolated"
    data = {
        "scoring": {"api_key": "${TEST_SCORING_KEY}"},
        "users": [],
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f)
        config_path = f.name

    try:
        cfg = load_config(config_path)
        assert cfg.scoring.api_key == "sk-ant-interpolated"
    finally:
        os.unlink(config_path)
        del os.environ["TEST_SCORING_KEY"]


def test_scoring_config_weight_warning(caplog):
    """Weights not summing to ~1.0 emit a warning."""
    import logging

    with caplog.at_level(logging.WARNING, logger="paper_agent.config"):
        ScoringConfig(relevance_weight=0.8, quality_weight=0.8)

    assert any("expected ~1.0" in rec.message for rec in caplog.records)


def test_scoring_config_weight_no_warning():
    """Weights summing to 1.0 do not emit a warning."""
    import io
    import logging

    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.WARNING)
    logger = logging.getLogger("paper_agent.config")
    logger.addHandler(handler)
    try:
        ScoringConfig(relevance_weight=0.7, quality_weight=0.3)
        assert "expected ~1.0" not in log_stream.getvalue()
    finally:
        logger.removeHandler(handler)


def test_scoring_config_load_from_yaml():
    """New scoring fields round-trip through YAML."""
    data = {
        "scoring": {
            "model": "claude-sonnet-4-5",
            "max_tokens": 2048,
            "temperature": 0.5,
            "abstract_max_length": 1000,
            "relevance_weight": 0.7,
            "quality_weight": 0.3,
            "prompts": {
                "system_prompt": "You are a reviewer.",
            },
        },
        "users": [],
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f)
        config_path = f.name

    try:
        cfg = load_config(config_path)
        assert cfg.scoring.max_tokens == 2048
        assert cfg.scoring.temperature == 0.5
        assert cfg.scoring.abstract_max_length == 1000
        assert cfg.scoring.relevance_weight == 0.7
        assert cfg.scoring.quality_weight == 0.3
        assert cfg.scoring.prompts.system_prompt == "You are a reviewer."
        assert cfg.scoring.prompts.user_message_template is None
    finally:
        os.unlink(config_path)
