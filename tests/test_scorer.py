"""Tests for ClaudeScorer configurable behavior."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from paper_agent.config import PromptsConfig, ScoringConfig
from paper_agent.models import Paper
from paper_agent.scorer.claude_scorer import (
    SYSTEM_PROMPT,
    ClaudeScorer,
    _build_tool_choice,
)


def _make_paper(arxiv_id: str = "2401.00001v1") -> Paper:
    return Paper(
        arxiv_id=arxiv_id,
        title="Test Paper",
        authors=["Alice", "Bob"],
        abstract="A" * 2000,  # Long abstract for truncation tests
        published=datetime(2024, 1, 15, tzinfo=UTC),
        categories=["cs.DC", "cs.LG"],
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        abs_url=f"https://arxiv.org/abs/{arxiv_id}",
    )


# ─── Constructor & config wiring ───


@patch("paper_agent.scorer.claude_scorer.anthropic.Anthropic")
def test_scorer_default_behavior(mock_anthropic_cls):
    """Without config, scorer uses historical defaults."""
    mock_anthropic_cls.return_value = MagicMock()
    scorer = ClaudeScorer()

    assert scorer.model == "claude-haiku-4-5"
    assert scorer.batch_size == 10
    assert scorer.max_tokens == 4096
    assert scorer.temperature is None
    assert scorer.tool_choice == {"type": "auto"}
    assert scorer.abstract_max_length == 800
    mock_anthropic_cls.assert_called_once_with(api_key=None, base_url=None)


@patch("paper_agent.scorer.claude_scorer.anthropic.Anthropic")
def test_scorer_from_config(mock_anthropic_cls):
    """Scorer extracts all fields from a ScoringConfig."""
    mock_anthropic_cls.return_value = MagicMock()
    cfg = ScoringConfig(
        api_key="sk-ant-test",
        base_url="https://proxy.example.com/v1",
        model="claude-sonnet-4-5",
        batch_size=5,
        max_tokens=2048,
        temperature=0.3,
        tool_choice="tool",
        abstract_max_length=500,
        prompts=PromptsConfig(system_prompt="Custom system"),
    )
    scorer = ClaudeScorer(config=cfg)

    mock_anthropic_cls.assert_called_once_with(
        api_key="sk-ant-test",
        base_url="https://proxy.example.com/v1",
    )
    assert scorer.model == "claude-sonnet-4-5"
    assert scorer.batch_size == 5
    assert scorer.max_tokens == 2048
    assert scorer.temperature == 0.3
    assert scorer.tool_choice == {"type": "tool", "name": "score_papers"}
    assert scorer.abstract_max_length == 500
    assert scorer.prompts.system_prompt == "Custom system"


@patch("paper_agent.scorer.claude_scorer.anthropic.Anthropic")
def test_scorer_kwargs_override_config(mock_anthropic_cls):
    """Explicit kwargs take precedence over ScoringConfig."""
    mock_anthropic_cls.return_value = MagicMock()
    cfg = ScoringConfig(model="claude-sonnet-4-5", max_tokens=2048)
    scorer = ClaudeScorer(config=cfg, model="claude-opus-4-5", max_tokens=8192)
    assert scorer.model == "claude-opus-4-5"
    assert scorer.max_tokens == 8192


# ─── tool_choice mapping ───


def test_build_tool_choice_auto():
    assert _build_tool_choice("auto") == {"type": "auto"}


def test_build_tool_choice_tool():
    assert _build_tool_choice("tool") == {"type": "tool", "name": "score_papers"}


def test_build_tool_choice_unknown_defaults_to_auto():
    assert _build_tool_choice("something_else") == {"type": "auto"}


# ─── Prompt resolution ───


@patch("paper_agent.scorer.claude_scorer.anthropic.Anthropic")
def test_resolve_system_prompt_default(mock_anthropic_cls):
    mock_anthropic_cls.return_value = MagicMock()
    scorer = ClaudeScorer()
    assert scorer._resolve_system_prompt() == SYSTEM_PROMPT


@patch("paper_agent.scorer.claude_scorer.anthropic.Anthropic")
def test_resolve_system_prompt_custom(mock_anthropic_cls):
    mock_anthropic_cls.return_value = MagicMock()
    scorer = ClaudeScorer(prompts=PromptsConfig(system_prompt="You are a reviewer."))
    assert scorer._resolve_system_prompt() == "You are a reviewer."


@patch("paper_agent.scorer.claude_scorer.anthropic.Anthropic")
def test_resolve_system_prompt_empty_falls_back(mock_anthropic_cls):
    mock_anthropic_cls.return_value = MagicMock()
    scorer = ClaudeScorer(prompts=PromptsConfig(system_prompt=""))
    assert scorer._resolve_system_prompt() == SYSTEM_PROMPT


# ─── User message template ───


@patch("paper_agent.scorer.claude_scorer.anthropic.Anthropic")
def test_build_user_message_default_template(mock_anthropic_cls):
    mock_anthropic_cls.return_value = MagicMock()
    scorer = ClaudeScorer()
    papers = [_make_paper()]
    msg = scorer._build_user_message(papers)
    assert "Please score the following 1 papers" in msg
    assert "Test Paper" in msg


@patch("paper_agent.scorer.claude_scorer.anthropic.Anthropic")
def test_build_user_message_custom_template(mock_anthropic_cls):
    mock_anthropic_cls.return_value = MagicMock()
    scorer = ClaudeScorer(
        prompts=PromptsConfig(user_message_template="Review {paper_count} papers:\n{papers}")
    )
    papers = [_make_paper(), _make_paper("2")]
    msg = scorer._build_user_message(papers)
    assert msg.startswith("Review 2 papers:")
    assert "Test Paper" in msg


@patch("paper_agent.scorer.claude_scorer.anthropic.Anthropic")
def test_build_user_message_missing_placeholders(mock_anthropic_cls):
    """Template with unknown placeholders doesn't crash."""
    mock_anthropic_cls.return_value = MagicMock()
    scorer = ClaudeScorer(
        prompts=PromptsConfig(user_message_template="Custom: {paper_count}, {papers}, {unknown}")
    )
    papers = [_make_paper()]
    msg = scorer._build_user_message(papers)
    assert "Custom: 1," in msg
    assert "{unknown}" in msg  # Left as-is


# ─── Abstract truncation ───


@patch("paper_agent.scorer.claude_scorer.anthropic.Anthropic")
def test_abstract_truncation_default(mock_anthropic_cls):
    mock_anthropic_cls.return_value = MagicMock()
    scorer = ClaudeScorer()
    formatted = scorer._format_papers([_make_paper()])
    # Default abstract_max_length = 800
    assert "A" * 800 in formatted
    assert "A" * 801 not in formatted


@patch("paper_agent.scorer.claude_scorer.anthropic.Anthropic")
def test_abstract_truncation_custom(mock_anthropic_cls):
    mock_anthropic_cls.return_value = MagicMock()
    scorer = ClaudeScorer(abstract_max_length=200)
    formatted = scorer._format_papers([_make_paper()])
    assert "A" * 200 in formatted
    assert "A" * 201 not in formatted


# ─── API call parameters ───


@patch("paper_agent.scorer.claude_scorer.anthropic.Anthropic")
def test_score_batch_passes_config_params(mock_anthropic_cls):
    """messages.create() is called with config-derived parameters."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = []  # No tool_use blocks → empty result
    mock_client.messages.create.return_value = mock_response
    mock_anthropic_cls.return_value = mock_client

    scorer = ClaudeScorer(
        model="claude-sonnet-4-5",
        max_tokens=2048,
        temperature=0.3,
        tool_choice="tool",
        prompts=PromptsConfig(system_prompt="Custom system"),
    )
    scorer._score_batch([_make_paper()])

    mock_client.messages.create.assert_called_once()
    kwargs = mock_client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-sonnet-4-5"
    assert kwargs["max_tokens"] == 2048
    assert kwargs["temperature"] == 0.3
    assert kwargs["tool_choice"] == {"type": "tool", "name": "score_papers"}
    assert kwargs["system"] == "Custom system"


@patch("paper_agent.scorer.claude_scorer.anthropic.Anthropic")
def test_score_batch_omits_temperature_when_none(mock_anthropic_cls):
    """When temperature is None, it's not passed to messages.create()."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = []
    mock_client.messages.create.return_value = mock_response
    mock_anthropic_cls.return_value = mock_client

    scorer = ClaudeScorer(temperature=None)
    scorer._score_batch([_make_paper()])

    kwargs = mock_client.messages.create.call_args.kwargs
    assert "temperature" not in kwargs


# ─── Structured-insights response validation ───


def _mock_tool_use_block(scores_payload: list[dict]) -> MagicMock:
    """Build a fake Anthropic content block with a tool_use response."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = "score_papers"
    block.input = {"scores": scores_payload}
    return block


def _full_score_payload(index: int = 0, **overrides) -> dict:
    """Construct a complete tool_use score payload for one paper."""
    payload = {
        "index": index,
        "relevance_score": 7.5,
        "quality_score": 6.5,
        "summary_zh": "测试摘要",
        "sub_domain_tags": ["quantization"],
        "key_contributions": ["首个 INT4 方案"],
        "problem_statement_zh": "解决量化精度问题",
        "methods_zh": "采用混合精度",
        "impact_tier": "solid",
    }
    payload.update(overrides)
    return payload


@patch("paper_agent.scorer.claude_scorer.anthropic.Anthropic")
def test_score_batch_populates_structured_insights(mock_anthropic_cls):
    """A well-formed response round-trips into ScoredPaper fields."""
    mock_client = MagicMock()
    response = MagicMock()
    response.content = [
        _mock_tool_use_block(
            [
                _full_score_payload(
                    index=0,
                    key_contributions=["贡献 A", "贡献 B"],
                    problem_statement_zh="问题描述",
                    methods_zh="方法描述",
                    impact_tier="breakthrough",
                )
            ]
        )
    ]
    mock_client.messages.create.return_value = response
    mock_anthropic_cls.return_value = mock_client

    scorer = ClaudeScorer()
    [sp] = scorer._score_batch([_make_paper()])

    assert sp.key_contributions == ("贡献 A", "贡献 B")
    assert sp.problem_statement_zh == "问题描述"
    assert sp.methods_zh == "方法描述"
    assert sp.impact_tier == "breakthrough"


@patch("paper_agent.scorer.claude_scorer.anthropic.Anthropic")
def test_score_batch_truncates_overlong_contribution_bullets(mock_anthropic_cls):
    """A bullet longer than MAX_CONTRIBUTION_CHARS is sliced."""
    from paper_agent.scorer.claude_scorer import MAX_CONTRIBUTION_CHARS

    mock_client = MagicMock()
    long_bullet = "x" * (MAX_CONTRIBUTION_CHARS + 50)
    response = MagicMock()
    response.content = [
        _mock_tool_use_block([_full_score_payload(key_contributions=[long_bullet])])
    ]
    mock_client.messages.create.return_value = response
    mock_anthropic_cls.return_value = mock_client

    scorer = ClaudeScorer()
    [sp] = scorer._score_batch([_make_paper()])
    assert len(sp.key_contributions) == 1
    assert len(sp.key_contributions[0]) == MAX_CONTRIBUTION_CHARS


@patch("paper_agent.scorer.claude_scorer.anthropic.Anthropic")
def test_score_batch_caps_bullet_count(mock_anthropic_cls, caplog):
    """More than MAX_KEY_CONTRIBUTIONS bullets are truncated with a warning."""
    import logging

    from paper_agent.scorer.claude_scorer import MAX_KEY_CONTRIBUTIONS

    mock_client = MagicMock()
    response = MagicMock()
    bullets = [f"贡献 {i}" for i in range(5)]
    response.content = [_mock_tool_use_block([_full_score_payload(key_contributions=bullets)])]
    mock_client.messages.create.return_value = response
    mock_anthropic_cls.return_value = mock_client

    scorer = ClaudeScorer()
    with caplog.at_level(logging.WARNING, logger="paper_agent.scorer.claude_scorer"):
        [sp] = scorer._score_batch([_make_paper()])

    assert len(sp.key_contributions) == MAX_KEY_CONTRIBUTIONS
    assert any("key_contributions" in r.message for r in caplog.records)


@patch("paper_agent.scorer.claude_scorer.anthropic.Anthropic")
def test_score_batch_unknown_tier_falls_back_to_solid(mock_anthropic_cls, caplog):
    """An unknown impact_tier value is replaced with 'solid' and warned."""
    import logging

    mock_client = MagicMock()
    response = MagicMock()
    response.content = [_mock_tool_use_block([_full_score_payload(impact_tier="legendary")])]
    mock_client.messages.create.return_value = response
    mock_anthropic_cls.return_value = mock_client

    scorer = ClaudeScorer()
    with caplog.at_level(logging.WARNING, logger="paper_agent.scorer.claude_scorer"):
        [sp] = scorer._score_batch([_make_paper()])

    assert sp.impact_tier == "solid"
    assert any("impact_tier" in r.message for r in caplog.records)


@patch("paper_agent.scorer.claude_scorer.anthropic.Anthropic")
def test_score_batch_missing_new_fields_uses_defaults(mock_anthropic_cls):
    """When the LLM omits the new fields, the scorer still produces a paper."""
    mock_client = MagicMock()
    response = MagicMock()
    # Payload missing all four new fields — simulate either an older LLM
    # response shape or a partial tool call.
    payload = {
        "index": 0,
        "relevance_score": 5.0,
        "quality_score": 5.0,
        "summary_zh": "摘要",
        "sub_domain_tags": ["quantization"],
    }
    response.content = [_mock_tool_use_block([payload])]
    mock_client.messages.create.return_value = response
    mock_anthropic_cls.return_value = mock_client

    scorer = ClaudeScorer()
    [sp] = scorer._score_batch([_make_paper()])
    assert sp.key_contributions == ()
    assert sp.problem_statement_zh == ""
    assert sp.methods_zh == ""
    assert sp.impact_tier == "solid"


@patch("paper_agent.scorer.claude_scorer.anthropic.Anthropic")
def test_score_logs_tier_distribution(mock_anthropic_cls, caplog):
    """score() logs an aggregate tier distribution line at INFO level."""
    import logging

    mock_client = MagicMock()
    response = MagicMock()
    response.content = [
        _mock_tool_use_block(
            [
                _full_score_payload(index=0, impact_tier="breakthrough"),
                _full_score_payload(index=1, impact_tier="solid"),
                _full_score_payload(index=2, impact_tier="solid"),
            ]
        )
    ]
    mock_client.messages.create.return_value = response
    mock_anthropic_cls.return_value = mock_client

    scorer = ClaudeScorer()
    papers = [_make_paper(f"id-{i}") for i in range(3)]
    with caplog.at_level(logging.INFO, logger="paper_agent.scorer.claude_scorer"):
        scorer.score(papers)

    tier_lines = [r.message for r in caplog.records if "tier distribution" in r.message]
    assert tier_lines, "Expected a tier-distribution log line"
    line = tier_lines[-1]
    assert "breakthrough=1" in line
    assert "solid=2" in line
    assert "incremental=0" in line
