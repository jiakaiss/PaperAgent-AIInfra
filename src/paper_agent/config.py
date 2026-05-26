"""Configuration management with Pydantic + YAML.

Supports multi-user configuration with per-user subscriptions and notification channels.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator


def _interpolate_env(value: str, strict: bool = False) -> str:
    """Replace ${ENV_VAR} with environment variable values.

    If strict=False (default), unset variables are left as empty strings.
    If strict=True, unset variables raise ValueError.
    """

    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        env_val = os.environ.get(var_name)
        if env_val is None:
            if strict:
                raise ValueError(
                    f"Environment variable '{var_name}' is not set. "
                    f"Please set it or update config.yaml directly."
                )
            return ""
        return env_val

    return re.sub(r"\$\{(\w+)\}", replacer, value)


def _interpolate_recursive(obj):
    """Recursively interpolate environment variables in config values."""
    if isinstance(obj, str):
        return _interpolate_env(obj)
    elif isinstance(obj, dict):
        return {k: _interpolate_recursive(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_interpolate_recursive(item) for item in obj]
    return obj


# ─── Fetch & Scoring (shared across all users) ───


class FetchConfig(BaseModel):
    categories: list[str] = Field(
        default=["cs.DC", "cs.LG", "cs.AI", "cs.PF", "cs.NI", "cs.AR"]
    )
    keywords: list[str] = Field(
        default=[
            "distributed training",
            "model parallelism",
            "pipeline parallelism",
            "data parallelism",
            "tensor parallelism",
            "inference optimization",
            "model serving",
            "GPU scheduling",
            "GPU cluster",
            "large language model infrastructure",
            "mixture of experts",
            "mixture-of-experts",
            "speculative decoding",
            "KV cache",
            "quantization",
            "model compression",
            "checkpoint",
            "all-reduce",
            "communication optimization",
            "memory optimization",
            "deep learning compiler",
            "operator fusion",
        ]
    )
    max_results: int = 200
    days_back: int = 2


class ScoringConfig(BaseModel):
    model: str = "claude-haiku-4-5"
    batch_size: int = 10


# ─── Notifier configs (reused per-user) ───


class EmailNotifierConfig(BaseModel):
    enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    sender: str = ""
    recipients: list[str] = []
    use_tls: bool = True


class WeComNotifierConfig(BaseModel):
    enabled: bool = False
    webhook_url: str = ""


class FeishuNotifierConfig(BaseModel):
    enabled: bool = False
    webhook_url: str = ""


class DingTalkNotifierConfig(BaseModel):
    enabled: bool = False
    webhook_url: str = ""
    secret: str = ""


# ─── Per-user configuration ───


class SubscriptionConfig(BaseModel):
    """User's sub-domain subscriptions.

    sub_domains can be:
    - ["all"] to receive all AI Infra papers
    - A list of specific sub-domains like ["quantization", "sparsity", "pruning"]

    Valid sub-domains: quantization, distillation, pruning, sparsity,
    distributed_training, parallelism, serving, speculative_decoding,
    kv_cache, moe, compiler, memory_optimization, communication, scheduling
    """

    sub_domains: list[str] = Field(default=["all"])


class UserNotifyConfig(BaseModel):
    """Notification channels for a single user."""

    email: EmailNotifierConfig = Field(default_factory=EmailNotifierConfig)
    wecom: WeComNotifierConfig = Field(default_factory=WeComNotifierConfig)
    feishu: FeishuNotifierConfig = Field(default_factory=FeishuNotifierConfig)
    dingtalk: DingTalkNotifierConfig = Field(default_factory=DingTalkNotifierConfig)


class UserThresholdsConfig(BaseModel):
    """Per-user filtering thresholds."""

    min_relevance: float = 6.0
    min_quality: float = 5.0
    top_n: int = 20


class UserConfig(BaseModel):
    """Configuration for a single user with subscriptions and notification preferences."""

    user_id: str
    display_name: str = ""
    subscriptions: SubscriptionConfig = Field(default_factory=SubscriptionConfig)
    notify: UserNotifyConfig = Field(default_factory=UserNotifyConfig)
    thresholds: UserThresholdsConfig = Field(default_factory=UserThresholdsConfig)


# ─── Schedule, Storage, Logging (global) ───


class ScheduleConfig(BaseModel):
    enabled: bool = True
    cron_hour: int = 9
    cron_minute: int = 0
    timezone: str = "Asia/Shanghai"


class StorageConfig(BaseModel):
    db_path: str = "paper_agent.db"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: Optional[str] = None


# ─── Top-level config ───


class AppConfig(BaseModel):
    fetch: FetchConfig = Field(default_factory=FetchConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    users: list[UserConfig] = Field(default_factory=list)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @field_validator("users")
    @classmethod
    def validate_unique_user_ids(cls, users: list[UserConfig]) -> list[UserConfig]:
        ids = [u.user_id for u in users]
        if len(ids) != len(set(ids)):
            dupes = [uid for uid in ids if ids.count(uid) > 1]
            raise ValueError(f"Duplicate user_id(s): {set(dupes)}")
        return users


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    """Load config from YAML file with environment variable interpolation."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}\n"
            f"Run 'paper-agent init' to create a template config."
        )

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    raw = _interpolate_recursive(raw)
    return AppConfig(**raw)
