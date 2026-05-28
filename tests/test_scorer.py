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
