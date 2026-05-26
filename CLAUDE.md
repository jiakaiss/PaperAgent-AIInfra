# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies (editable mode with dev tools)
pip install -e ".[dev]"

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_pipeline.py -v

# Run a specific test
pytest tests/test_pipeline.py::test_pipeline_multi_user_filter -v

# Lint code
ruff check src/ tests/

# Format code
ruff format src/ tests/

# Run the CLI
paper-agent --help
paper-agent run --dry-run -c config.yaml
paper-agent run --user alice --dry-run -c config.yaml
paper-agent test --notifier feishu --user alice -c config.yaml
paper-agent daemon -c config.yaml
paper-agent stats -c config.yaml
```

On Windows, set `PYTHONIOENCODING=utf-8` before running CLI to avoid GBK encoding errors with emoji output.

## Architecture

This is a **multi-user** AI Infra paper recommendation agent that fetches from arXiv, scores with Claude (including sub-domain tags), and pushes personalized digests to different users.

### Pipeline Flow (`pipeline.py`)

The pipeline has two phases:

**Shared phase** (runs once, saves Claude API cost):
```
Fetch superset → Dedup against papers cache → Score with Claude → Cache results
```

**Per-user phase** (runs for each user):
```
Filter by sub_domain tags → Filter by thresholds → Dedup per-user → Notify → mark_sent
```

The `Pipeline._build_superset_keywords()` method unions all users' subscribed sub-domain keywords with global fetch keywords, so a single arXiv fetch covers everyone's interests.

### Sub-Domain Taxonomy (`models.py`)

14 standard sub-domains, each with associated arXiv keywords:
```
quantization, distillation, pruning, sparsity, distributed_training,
parallelism, serving, speculative_decoding, kv_cache, moe, compiler,
memory_optimization, communication, scheduling
```

`SUB_DOMAINS` dict maps each sub-domain to its keyword list. The scorer emits 1-3 `sub_domain_tags` per paper.

### Multi-User Config (`config.py`)

Config structure (no backward compat with single-user format):
```python
AppConfig
├── FetchConfig       (global: categories, keywords, max_results, days_back)
├── ScoringConfig     (global: model, batch_size)
├── users: list[UserConfig]    # ← per-user
│   └── UserConfig
│       ├── user_id, display_name
│       ├── SubscriptionConfig (sub_domains: ["all"] or specific list)
│       ├── UserNotifyConfig   (email, wecom, feishu, dingtalk)
│       └── UserThresholdsConfig (min_relevance, min_quality, top_n)
├── ScheduleConfig    (global)
├── StorageConfig     (global)
└── LoggingConfig     (global)
```

Duplicate `user_id` values are rejected by a Pydantic validator.

### Scoring (`scorer/claude_scorer.py`)

Uses Claude's `tool_use` with `tool_choice={"type": "tool", "name": "score_papers"}` for guaranteed structured output. The `SCORE_TOOL` schema includes:
- `relevance_score` (0-10): AI Infra relevance
- `quality_score` (0-10): overall quality
- `summary_zh`: Chinese summary
- `sub_domain_tags` (1-3 tags from the enum): sub-domain classification

Papers are scored in batches (default 10) to reduce API calls.

### Storage (`storage/database.py`)

Two-table schema:
```sql
papers (arxiv_id PK)       -- score cache, shared across users
sent_papers (user_id, arxiv_id PK) -- per-user delivery tracking
```

Key methods:
- `filter_uncached(ids)`: IDs not yet scored (need Claude API call)
- `cache_papers(scored)`: store scored papers
- `load_cached_papers(ids)`: retrieve previously scored papers
- `filter_unsent_for_user(user_id, ids)`: IDs not yet sent to specific user
- `mark_sent(user_id, papers)`: record delivery

### Notifier Plugins (`notifier/`)

Protocol-based (structural typing). `create_notifiers_for_user(UserNotifyConfig)` builds a notifier list for one user. Each notifier handles platform-specific quirks:
- **Email**: SMTP + HTML templates
- **企业微信**: Markdown, 4096-byte limit → auto-splits
- **飞书**: Rich text `post` format (structured JSON)
- **钉钉**: Markdown + HMAC-SHA256 signature

## Environment Variables

Required:
- `ANTHROPIC_API_KEY`: Claude API key

Optional (per-user webhook/SMTP credentials configured in config.yaml):
- `FEISHU_WEBHOOK_<USER>`, `WECOM_WEBHOOK`, `DINGTALK_WEBHOOK`, `DINGTALK_SECRET`
- `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_SENDER`

## Config Migration

The config format changed from single-user to multi-user. Old `config.yaml` files with a top-level `notify:` section must be rewritten using the new `users:` list format. See `config.example.yaml` for the current structure.
