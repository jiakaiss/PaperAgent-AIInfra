"""Tests for config loading."""

import os
import tempfile

import pytest
import yaml

from paper_agent.config import (
    AppConfig,
    EmailNotifierConfig,
    PromptsConfig,
    ScoringConfig,
    SubscriptionConfig,
    ThresholdsConfig,
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


def test_thresholds_defaults():
    """ThresholdsConfig has sensible defaults for all subscription users."""
    cfg = AppConfig()
    assert cfg.thresholds.min_relevance == 6.0
    assert cfg.thresholds.min_quality == 5.0
    assert cfg.thresholds.top_n == 10
    assert cfg.thresholds.per_sub_domain_top_n == 20
    assert cfg.thresholds.min_tier == "solid"


def test_thresholds_custom_values():
    """ThresholdsConfig accepts custom values."""
    cfg = AppConfig(
        thresholds=ThresholdsConfig(
            min_relevance=7.5,
            min_quality=6.0,
            top_n=20,
            per_sub_domain_top_n=10,
            min_tier="breakthrough",
        )
    )
    assert cfg.thresholds.min_relevance == 7.5
    assert cfg.thresholds.min_quality == 6.0
    assert cfg.thresholds.top_n == 20
    assert cfg.thresholds.per_sub_domain_top_n == 10
    assert cfg.thresholds.min_tier == "breakthrough"


def test_thresholds_rejects_non_positive_top_n():
    with pytest.raises(ValueError, match="top_n"):
        ThresholdsConfig(top_n=0)


def test_thresholds_loads_from_yaml():
    data = {
        "thresholds": {
            "min_relevance": 8.0,
            "min_quality": 7.0,
            "top_n": 15,
            "min_tier": "breakthrough",
        }
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f)
        config_path = f.name

    try:
        cfg = load_config(config_path)
        assert cfg.thresholds.min_relevance == 8.0
        assert cfg.thresholds.min_quality == 7.0
        assert cfg.thresholds.top_n == 15
        assert cfg.thresholds.min_tier == "breakthrough"
    finally:
        os.unlink(config_path)


def test_user_notify_config_has_only_email():
    """UserNotifyConfig should only contain an email field (no wecom/feishu/dingtalk)."""
    from paper_agent.config import UserNotifyConfig

    cfg = UserNotifyConfig()
    assert hasattr(cfg, "email")
    assert not hasattr(cfg, "wecom")
    assert not hasattr(cfg, "feishu")
    assert not hasattr(cfg, "dingtalk")


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


# ─── Global email config tests ───


def test_email_config_defaults():
    """Default email config has enabled=false and empty credentials."""
    cfg = AppConfig()
    assert cfg.email.enabled is False
    assert cfg.email.smtp_host == "smtp.gmail.com"
    assert cfg.email.smtp_port == 587
    assert cfg.email.smtp_user == ""
    assert cfg.email.smtp_password == ""
    assert cfg.email.sender == ""
    assert cfg.email.use_tls is True


def test_email_config_custom_values():
    """Email config accepts custom SMTP settings."""
    cfg = AppConfig(
        email=EmailNotifierConfig(
            enabled=True,
            smtp_host="smtp.example.com",
            smtp_port=465,
            smtp_user="user@example.com",
            smtp_password="secret",
            sender="noreply@example.com",
            use_tls=False,
        )
    )
    assert cfg.email.enabled is True
    assert cfg.email.smtp_host == "smtp.example.com"
    assert cfg.email.smtp_port == 465
    assert cfg.email.smtp_user == "user@example.com"
    assert cfg.email.smtp_password == "secret"
    assert cfg.email.sender == "noreply@example.com"
    assert cfg.email.use_tls is False


def test_email_config_env_interpolation():
    """Email config supports ${ENV_VAR} interpolation."""
    os.environ["TEST_SMTP_USER"] = "test@example.com"
    os.environ["TEST_SMTP_PASSWORD"] = "test_password"
    data = {
        "email": {
            "enabled": True,
            "smtp_user": "${TEST_SMTP_USER}",
            "smtp_password": "${TEST_SMTP_PASSWORD}",
            "sender": "noreply@example.com",
        },
        "users": [],
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f)
        config_path = f.name

    try:
        cfg = load_config(config_path)
        assert cfg.email.enabled is True
        assert cfg.email.smtp_user == "test@example.com"
        assert cfg.email.smtp_password == "test_password"
    finally:
        os.unlink(config_path)
        del os.environ["TEST_SMTP_USER"]
        del os.environ["TEST_SMTP_PASSWORD"]


def test_email_config_warning_missing_credentials(caplog):
    """Email config enabled with missing credentials emits warning."""
    import logging

    with caplog.at_level(logging.WARNING, logger="paper_agent.config"):
        AppConfig(
            email=EmailNotifierConfig(
                enabled=True,
                smtp_user="",  # missing
                smtp_password="secret",
            )
        )

    assert any("missing fields" in rec.message for rec in caplog.records)
    assert any("smtp_user" in rec.message for rec in caplog.records)


def test_email_config_no_warning_when_disabled():
    """Email config disabled does not emit warning even with missing credentials."""
    import io
    import logging

    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.WARNING)
    logger = logging.getLogger("paper_agent.config")
    logger.addHandler(handler)
    try:
        AppConfig(
            email=EmailNotifierConfig(
                enabled=False,
                smtp_user="",
                smtp_password="",
            )
        )
        assert "missing fields" not in log_stream.getvalue()
    finally:
        logger.removeHandler(handler)


def test_email_config_no_warning_when_complete(caplog):
    """Email config enabled with all credentials does not emit warning."""
    import logging

    with caplog.at_level(logging.WARNING, logger="paper_agent.config"):
        AppConfig(
            email=EmailNotifierConfig(
                enabled=True,
                smtp_host="smtp.example.com",
                smtp_user="user@example.com",
                smtp_password="secret",
            )
        )

    assert not any("missing fields" in rec.message for rec in caplog.records)


def test_schedule_config_interval_values():
    """ScheduleConfig accepts interval mode for frequent paper queries."""
    from paper_agent.config import ScheduleConfig

    cfg = ScheduleConfig(mode="interval", interval_minutes=360)
    assert cfg.mode == "interval"
    assert cfg.interval_minutes == 360
    assert cfg.cron_hour == 9
    assert cfg.cron_minute == 0


def test_schedule_config_cron_backward_compatible():
    """Cron mode remains the default and keeps daily schedule fields."""
    from paper_agent.config import ScheduleConfig

    cfg = ScheduleConfig()
    assert cfg.mode == "cron"
    assert cfg.cron_hour == 9
    assert cfg.cron_minute == 0


def test_schedule_config_interval_loads_from_yaml():
    """Interval schedule fields round-trip through YAML loading."""
    data = {
        "schedule": {
            "enabled": True,
            "mode": "interval",
            "interval_minutes": 360,
            "cron_hour": 9,
            "cron_minute": 0,
        },
        "users": [],
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f)
        config_path = f.name

    try:
        cfg = load_config(config_path)
        assert cfg.schedule.mode == "interval"
        assert cfg.schedule.interval_minutes == 360
        assert cfg.schedule.cron_hour == 9
        assert cfg.schedule.cron_minute == 0
    finally:
        os.unlink(config_path)


def test_schedule_config_separate_ingest_digest_values():
    """ScheduleConfig supports separate ingest interval and daily digest time."""
    from paper_agent.config import ScheduleConfig

    cfg = ScheduleConfig(
        ingest_interval_minutes=360,
        digest_hour=9,
        digest_minute=0,
    )
    assert cfg.ingest_interval_minutes == 360
    assert cfg.digest_hour == 9
    assert cfg.digest_minute == 0


def test_schedule_config_rejects_invalid_digest_time():
    """Digest time must be a valid hour/minute pair."""
    from paper_agent.config import ScheduleConfig

    with pytest.raises(ValueError, match="digest_hour"):
        ScheduleConfig(digest_hour=24)
    with pytest.raises(ValueError, match="digest_minute"):
        ScheduleConfig(digest_minute=60)


def test_schedule_config_separate_ingest_digest_loads_from_yaml():
    """Separate ingest/digest fields round-trip through YAML loading."""
    data = {
        "schedule": {
            "enabled": True,
            "ingest_interval_minutes": 360,
            "digest_hour": 9,
            "digest_minute": 0,
        },
        "users": [],
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f)
        config_path = f.name

    try:
        cfg = load_config(config_path)
        assert cfg.schedule.ingest_interval_minutes == 360
        assert cfg.schedule.digest_hour == 9
        assert cfg.schedule.digest_minute == 0
    finally:
        os.unlink(config_path)


def test_schedule_config_ingest_hours_cron_mode():
    """Setting ingest_hours switches to cron-style ingest scheduling."""
    from paper_agent.config import ScheduleConfig

    cfg = ScheduleConfig(ingest_hours=[6, 18], ingest_minute=0)
    assert cfg.ingest_hours == [6, 18]
    assert cfg.ingest_minute == 0
    # 6→18 gap is 12h, 18→6 wrap is also 12h → effective interval 720 min.
    # Heartbeat staleness uses this so cron-mode daemons don't get flagged
    # mid-gap as "wedged".
    assert cfg.effective_ingest_interval_minutes == 720


def test_schedule_config_effective_interval_falls_back_when_unset():
    """Without ingest_hours, effective interval is just ingest_interval_minutes."""
    from paper_agent.config import ScheduleConfig

    cfg = ScheduleConfig(ingest_interval_minutes=360)
    assert cfg.ingest_hours is None
    assert cfg.effective_ingest_interval_minutes == 360


def test_schedule_config_effective_interval_takes_widest_gap():
    """For uneven ingest_hours the effective interval tracks the longest gap."""
    from paper_agent.config import ScheduleConfig

    # 6→12 = 6h, 12→18 = 6h, 18→6 wrap = 12h → 12h wins
    cfg = ScheduleConfig(ingest_hours=[6, 12, 18])
    assert cfg.effective_ingest_interval_minutes == 720

    # Single hour means once-per-day → 24h
    cfg = ScheduleConfig(ingest_hours=[3])
    assert cfg.effective_ingest_interval_minutes == 24 * 60


def test_schedule_config_rejects_invalid_ingest_hours():
    """ingest_hours validation covers range, emptiness, and duplicates."""
    from paper_agent.config import ScheduleConfig

    with pytest.raises(ValueError, match="ingest_hours"):
        ScheduleConfig(ingest_hours=[6, 25])
    with pytest.raises(ValueError, match="ingest_hours"):
        ScheduleConfig(ingest_hours=[])
    with pytest.raises(ValueError, match="ingest_hours"):
        ScheduleConfig(ingest_hours=[6, 6])
    with pytest.raises(ValueError, match="ingest_minute"):
        ScheduleConfig(ingest_minute=60)


def test_schedule_config_ingest_hours_round_trip_yaml():
    """ingest_hours and ingest_minute survive a YAML load."""
    data = {
        "schedule": {
            "enabled": True,
            "ingest_hours": [6, 18],
            "ingest_minute": 0,
            "digest_hour": 9,
            "digest_minute": 0,
        },
        "users": [],
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f)
        config_path = f.name

    try:
        cfg = load_config(config_path)
        assert cfg.schedule.ingest_hours == [6, 18]
        assert cfg.schedule.ingest_minute == 0
        assert cfg.schedule.effective_ingest_interval_minutes == 720
    finally:
        os.unlink(config_path)


def test_web_admin_contact_default_empty():
    """Default WebConfig has admin_contact = '' so no parenthetical leaks."""
    cfg = AppConfig()
    assert cfg.web.admin_contact == ""


def test_web_admin_contact_round_trips_from_yaml():
    data = {"web": {"admin_contact": "张三 <admin@example.com>"}}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True)
        config_path = f.name
    try:
        cfg = load_config(config_path)
        assert cfg.web.admin_contact == "张三 <admin@example.com>"
    finally:
        os.unlink(config_path)


def test_web_admin_contact_absent_from_yaml_defaults_to_empty():
    """Existing configs that don't mention admin_contact still load cleanly."""
    data = {"web": {"min_quality": 5.0}}  # no admin_contact key at all
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f)
        config_path = f.name
    try:
        cfg = load_config(config_path)
        assert cfg.web.admin_contact == ""
    finally:
        os.unlink(config_path)
