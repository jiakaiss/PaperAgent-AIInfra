"""Configuration management with Pydantic + YAML."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


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
    min_relevance: float = 6.0
    min_quality: float = 5.0
    top_n: int = 20


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


class NotifyConfig(BaseModel):
    email: EmailNotifierConfig = Field(default_factory=EmailNotifierConfig)
    wecom: WeComNotifierConfig = Field(default_factory=WeComNotifierConfig)
    feishu: FeishuNotifierConfig = Field(default_factory=FeishuNotifierConfig)
    dingtalk: DingTalkNotifierConfig = Field(default_factory=DingTalkNotifierConfig)


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


class AppConfig(BaseModel):
    fetch: FetchConfig = Field(default_factory=FetchConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    notify: NotifyConfig = Field(default_factory=NotifyConfig)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


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
