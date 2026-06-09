"""Configuration management with Pydantic + YAML.

Supports multi-user configuration with per-user subscriptions and notification channels.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Literal

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
    # Quality floor strategy (dual-track fetch). "per_keyword_cap" enables a
    # per-keyword budget and a recency-based cross-list pass; "none" preserves
    # the legacy single-pass behavior.
    quality_floor_strategy: Literal["none", "per_keyword_cap"] = "none"
    # Minimum results per keyword when quality_floor_strategy is
    # "per_keyword_cap". Prevents a keyword with 0 results from inflating
    # another keyword's share.
    min_per_keyword: int = 10
    # arXiv categories for the recency-based cross-list pass (track 2 of the
    # dual-track fetch). When empty, the cross-list pass is skipped.
    cross_list_categories: list[str] = Field(default_factory=list)


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
    unsubscribe_url: str = ""


# ─── Per-user configuration (internal models, used by subscription system) ───


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
    """Notification channels for a single user (only email supported)."""

    email: EmailNotifierConfig = Field(default_factory=EmailNotifierConfig)


class UserThresholdsConfig(BaseModel):
    """Per-user filtering thresholds."""

    min_relevance: float = 6.0
    min_quality: float = 5.0
    top_n: int = 200
    per_sub_domain_top_n: int = 20
    # Minimum impact tier to include in this user's digest. "solid" (default)
    # excludes incremental papers — same default behavior as the web UI front
    # page. Set to "incremental" to include everything, "breakthrough" to
    # restrict to top-tier papers only.
    min_tier: Literal["breakthrough", "solid", "incremental"] = "solid"

    @model_validator(mode="after")
    def _check_positive_limits(self) -> UserThresholdsConfig:
        if self.top_n <= 0:
            raise ValueError("thresholds top_n must be positive")
        if self.per_sub_domain_top_n <= 0:
            raise ValueError("thresholds per_sub_domain_top_n must be positive")
        return self


class UserConfig(BaseModel):
    """Configuration for a single user with subscriptions and notification preferences."""

    user_id: str
    display_name: str = ""
    subscriptions: SubscriptionConfig = Field(default_factory=SubscriptionConfig)
    notify: UserNotifyConfig = Field(default_factory=UserNotifyConfig)
    thresholds: UserThresholdsConfig = Field(default_factory=UserThresholdsConfig)


# ─── Web subscriptions, Schedule, Storage, Logging (global) ───


class SubscriptionAccessConfig(BaseModel):
    """Access-code gate for public web subscription creation."""

    enabled: bool = False
    access_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_access_codes(self) -> SubscriptionAccessConfig:
        if self.enabled and not [code for code in self.access_codes if code.strip()]:
            raise ValueError("subscription access control enabled but no access_codes configured")
        return self

    def is_valid_code(self, code: str | None) -> bool:
        """Return True if access control is disabled or ``code`` is allowed."""
        if not self.enabled:
            return True
        if code is None:
            return False
        return code.strip() in {c.strip() for c in self.access_codes if c.strip()}


class UnsubscribeConfig(BaseModel):
    """Configuration for signed unsubscribe links."""

    secret: str = ""
    token_max_age_hours: int = 24 * 30

    @model_validator(mode="after")
    def _check_token_max_age(self) -> UnsubscribeConfig:
        if self.token_max_age_hours <= 0:
            raise ValueError("unsubscribe token_max_age_hours must be positive")
        return self


class WebConfig(BaseModel):
    """Configuration for web-facing features."""

    min_quality: float | None = 5.0
    public_base_url: str = ""
    admin_contact: str = ""

    @model_validator(mode="after")
    def _check_min_quality(self) -> WebConfig:
        if self.min_quality is not None and self.min_quality < 0:
            raise ValueError("web min_quality must be non-negative or null")
        return self


class SubscriptionDefaultsConfig(BaseModel):
    """Defaults used for users created from web subscription rows."""

    default_top_n: int = 10
    send_initial_digest_on_signup: bool = True
    access: SubscriptionAccessConfig = Field(default_factory=SubscriptionAccessConfig)
    unsubscribe: UnsubscribeConfig = Field(default_factory=UnsubscribeConfig)

    @model_validator(mode="after")
    def _check_default_top_n(self) -> SubscriptionDefaultsConfig:
        if self.default_top_n <= 0:
            raise ValueError("subscriptions default_top_n must be positive")
        return self


class ScheduleConfig(BaseModel):
    enabled: bool = True
    mode: Literal["cron", "interval"] = "cron"
    cron_hour: int = 9
    cron_minute: int = 0
    interval_minutes: int = 24 * 60
    ingest_interval_minutes: int = 360
    digest_hour: int = 9
    digest_minute: int = 0
    timezone: str = "Asia/Shanghai"

    @model_validator(mode="after")
    def _check_schedule(self) -> ScheduleConfig:
        if self.mode == "interval" and self.interval_minutes <= 0:
            raise ValueError("schedule interval_minutes must be positive when mode='interval'")
        if self.ingest_interval_minutes <= 0:
            raise ValueError("schedule ingest_interval_minutes must be positive")
        if not 0 <= self.digest_hour <= 23:
            raise ValueError("schedule digest_hour must be between 0 and 23")
        if not 0 <= self.digest_minute <= 59:
            raise ValueError("schedule digest_minute must be between 0 and 59")
        return self


class StorageConfig(BaseModel):
    db_path: str = "paper_agent.db"


class ThresholdsConfig(BaseModel):
    """Global filtering thresholds shared by all subscription users.

    Replaces the per-user ``UserThresholdsConfig`` once present in the legacy
    static ``users`` list. The subscription system reads these values when
    building a ``UserConfig`` for each active subscription email.
    """

    min_relevance: float = 6.0
    min_quality: float = 5.0
    top_n: int = 10
    per_sub_domain_top_n: int = 20
    min_tier: Literal["breakthrough", "solid", "incremental"] = "solid"

    @model_validator(mode="after")
    def _check_positive_limits(self) -> ThresholdsConfig:
        if self.top_n <= 0:
            raise ValueError("thresholds top_n must be positive")
        if self.per_sub_domain_top_n <= 0:
            raise ValueError("thresholds per_sub_domain_top_n must be positive")
        return self


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str | None = None


class AdminConfig(BaseModel):
    """Single-operator admin dashboard configuration.

    The dashboard is gated by HTTP Basic Auth. ``password`` supports
    ``${ENV_VAR}`` interpolation through the same recursive substitution
    applied to every string in the config. When ``enabled`` is False or
    ``password`` is empty/whitespace, the admin router is not registered
    and every ``/admin*`` URL responds 404 — indistinguishable from any
    other unknown path. See ``is_active``.
    """

    enabled: bool = False
    username: str = "admin"
    password: str = ""

    @property
    def is_active(self) -> bool:
        """True only when the operator has both opted in and set a password.

        Used by the app factory to decide whether to register the admin
        router. Empty-or-whitespace password is treated as disabled, since
        a deployed config with no real password is a misconfiguration
        (no credential could match) rather than "allow anyone in".
        """
        return self.enabled and bool(self.password.strip())


# ─── Top-level config ───


class AppConfig(BaseModel):
    fetch: FetchConfig = Field(default_factory=FetchConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    email: EmailNotifierConfig = Field(default_factory=EmailNotifierConfig)
    subscriptions: SubscriptionDefaultsConfig = Field(default_factory=SubscriptionDefaultsConfig)
    web: WebConfig = Field(default_factory=WebConfig)
    thresholds: ThresholdsConfig = Field(default_factory=ThresholdsConfig)
    users: list[UserConfig] = Field(default_factory=list)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    admin: AdminConfig = Field(default_factory=AdminConfig)

    @model_validator(mode="after")
    def validate_email_config(self) -> AppConfig:
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
