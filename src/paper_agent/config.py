"""Configuration management with Pydantic + YAML.

Supports multi-user configuration with per-user subscriptions and notification channels.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)


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
    categories: list[str] = Field(default=["cs.DC", "cs.LG", "cs.AI", "cs.PF", "cs.NI", "cs.AR"])
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


class PromptsConfig(BaseModel):
    """Configurable LLM prompts for paper scoring.

    When a field is None or empty, the scorer falls back to its built-in
    default prompt (defined as module-level constants in claude_scorer.py).

    The ``user_message_template`` supports ``{paper_count}`` (int) and
    ``{papers}`` (formatted paper text) placeholders via ``str.format()``.
    """

    system_prompt: str | None = None
    user_message_template: str | None = None


class ScoringConfig(BaseModel):
    """LLM-based paper scoring configuration.

    Fields fall into three groups:

    **Model & batching:**
        - ``model``: Anthropic model name (e.g. ``claude-haiku-4-5``).
        - ``batch_size``: papers per API call.

    **API connection** (all optional; ``None`` uses SDK/env defaults):
        - ``api_key``: Anthropic API key. Supports ``${ENV_VAR}`` interpolation.
          When ``None``, the SDK reads ``ANTHROPIC_API_KEY`` from the env.
        - ``base_url``: custom API endpoint (proxy / gateway).

    **Generation parameters:**
        - ``max_tokens``: max output tokens per call (default 4096).
        - ``temperature``: sampling temperature. ``None`` omits the parameter
          (SDK default).
        - ``tool_choice``: ``"auto"`` (let the model decide) or ``"tool"``
          (force the ``score_papers`` tool).
        - ``abstract_max_length``: chars to keep when truncating abstracts
          before sending to the model.

    **Score weighting:**
        - ``relevance_weight`` / ``quality_weight``: coefficients for
          ``total_score = relevance * w_r + quality * w_q``. A warning is
          emitted if they don't sum to ~1.0.

    **Prompts:**
        - ``prompts``: nested :class:`PromptsConfig` with optional overrides
          for the system prompt and user-message template.
    """

    model: str = "claude-haiku-4-5"
    batch_size: int = 10
    api_key: str | None = None
    base_url: str | None = None
    max_tokens: int = 4096
    temperature: float | None = None
    tool_choice: str = "auto"
    abstract_max_length: int = 800
    relevance_weight: float = 0.6
    quality_weight: float = 0.4
    prompts: PromptsConfig = Field(default_factory=PromptsConfig)

    @model_validator(mode="after")
    def _check_weights_sum(self) -> ScoringConfig:
        total = self.relevance_weight + self.quality_weight
        if abs(total - 1.0) > 0.01:
            logger.warning(
                f"ScoringConfig: relevance_weight ({self.relevance_weight}) + "
                f"quality_weight ({self.quality_weight}) = {total}, "
                f"expected ~1.0"
            )
        return self


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
    file: str | None = None


# ─── Top-level config ───


class AppConfig(BaseModel):
    fetch: FetchConfig = Field(default_factory=FetchConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    email: EmailNotifierConfig = Field(default_factory=EmailNotifierConfig)
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

    @model_validator(mode="after")
    def validate_email_config(self) -> "AppConfig":
        """Validate email configuration on startup."""
        email = self.email
        if email.enabled:
            missing = []
            if not email.smtp_host:
                missing.append("smtp_host")
            if not email.smtp_user:
                missing.append("smtp_user")
            if not email.smtp_password:
                missing.append("smtp_password")
            if missing:
                logger.warning(
                    f"Email config enabled but missing fields: {', '.join(missing)}. "
                    f"Subscription users may not receive emails."
                )
        return self


# ─── Web API models ───


class SubscriptionRequest(BaseModel):
    """Request model for subscription form submission."""

    email: str = Field(..., description="User's email address")
    sub_domains: list[str] = Field(
        ..., min_length=1, description="List of sub-domain names (at least one required)"
    )

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, email: str) -> str:
        """Validate email format using a simple regex pattern."""
        import re
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(pattern, email):
            raise ValueError("Invalid email format")
        return email.lower()

    @field_validator("sub_domains")
    @classmethod
    def validate_sub_domains(cls, sub_domains: list[str]) -> list[str]:
        """Validate that all sub-domains are valid taxonomy keys."""
        from paper_agent.models import SUB_DOMAINS

        valid_domains = set(SUB_DOMAINS.keys())
        invalid = [sd for sd in sub_domains if sd not in valid_domains]
        if invalid:
            raise ValueError(f"Invalid sub-domain(s): {invalid}")
        return sub_domains


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    """Load config from YAML file with environment variable interpolation."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}\nRun 'paper-agent init' to create a template config."
        )

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    raw = _interpolate_recursive(raw)
    return AppConfig(**raw)
