"""Tests for config loading."""

import os
import tempfile

import yaml

from paper_agent.config import AppConfig, load_config


def test_default_config():
    cfg = AppConfig()
    assert cfg.fetch.max_results == 200
    assert cfg.scoring.model == "claude-haiku-4-5"
    assert cfg.schedule.cron_hour == 9
    assert cfg.storage.db_path == "paper_agent.db"


def test_load_config_from_file():
    data = {
        "fetch": {"max_results": 50, "days_back": 3},
        "scoring": {"model": "claude-sonnet-4-5", "top_n": 10},
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f)
        config_path = f.name

    try:
        cfg = load_config(config_path)
        assert cfg.fetch.max_results == 50
        assert cfg.fetch.days_back == 3
        assert cfg.scoring.model == "claude-sonnet-4-5"
        assert cfg.scoring.top_n == 10
        # Defaults should still apply for unspecified fields
        assert cfg.schedule.cron_hour == 9
    finally:
        os.unlink(config_path)


def test_env_var_interpolation():
    os.environ["TEST_API_KEY"] = "sk-test-12345"

    data = {
        "scoring": {"model": "claude-haiku-4-5"},
    }

    # Test interpolation in a string context
    from paper_agent.config import _interpolate_env

    result = _interpolate_env("key=${TEST_API_KEY}")
    assert result == "key=sk-test-12345"

    del os.environ["TEST_API_KEY"]
