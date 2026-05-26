# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies (editable mode with dev tools)
pip install -e ".[dev]"

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_config.py -v

# Run a specific test
pytest tests/test_config.py::test_default_config -v

# Lint code
ruff check src/ tests/

# Format code
ruff format src/ tests/

# Run the CLI
paper-agent --help
paper-agent run --dry-run -c config.yaml
paper-agent test --notifier feishu -c config.yaml
paper-agent daemon -c config.yaml
```

## Architecture

This is an AI Infra paper recommendation agent that fetches from arXiv, scores with Claude, and pushes to multiple channels.

**Pipeline Flow** (`pipeline.py`):
```
Fetch → Dedup → Score → Filter → Notify
```

The `Pipeline` class orchestrates these 5 steps. Dedup happens **before** scoring to avoid wasting Claude API calls on papers already sent. Papers are marked as sent **after** notification succeeds (not before), so failed sends can retry on next run.

**Plugin System** (`notifier/`):
Notifiers implement the `Notifier` Protocol (structural typing, no base class required). Each notifier handles platform-specific quirks:
- **Email**: SMTP with Jinja2 HTML templates
- **企业微信**: Markdown with 4096-byte limit → auto-splits long messages
- **飞书**: Rich text `post` format (structured JSON, not raw markdown)
- **钉钉**: Markdown with HMAC-SHA256 signature

The `create_notifiers()` factory in `notifier/__init__.py` instantiates enabled notifiers from config.

**Scoring** (`scorer/claude_scorer.py`):
Uses Claude's `tool_use` feature with `tool_choice={"type": "tool", "name": "score_papers"}` to guarantee structured JSON output. Papers are scored in batches (default 10) to reduce API calls and allow cross-paper calibration. The `SCORE_TOOL` schema enforces `relevance_score`, `quality_score`, and `summary_zh` fields.

**Config** (`config.py`):
YAML-based with `${ENV_VAR}` interpolation. `_interpolate_env()` has two modes:
- `strict=False` (default): missing env vars become empty strings (allows loading template configs)
- `strict=True`: raises `ValueError` for missing vars (use for production validation)

Pydantic models validate structure and types.

**Storage** (`storage/database.py`):
SQLite tracks sent papers by `arxiv_id`. The `filter_new()` method returns only IDs not yet sent, enabling dedup before expensive scoring.

## Key Design Decisions

1. **Dedup before scoring**: Saves ~80% of Claude API costs when most papers were already sent
2. **Batch scoring**: 5-10 papers per API call reduces latency and rate-limit risk
3. **Mark sent after notify**: Transient failures don't lose papers; next run retries automatically
4. **Protocol-based plugins**: No inheritance required; any class with `name` property and `notify()` method works
5. **Tool_use for scoring**: Eliminates JSON parsing failures; Claude must return valid structured data

## Environment Variables

Required for full pipeline:
- `ANTHROPIC_API_KEY`: Claude API key for scoring

Optional (for notifications):
- `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_SENDER`: Email config
- `WECOM_WEBHOOK`, `FEISHU_WEBHOOK`, `DINGTALK_WEBHOOK`, `DINGTALK_SECRET`: Webhook URLs

On Windows, set `PYTHONIOENCODING=utf-8` before running CLI to avoid GBK encoding errors with emoji output.
