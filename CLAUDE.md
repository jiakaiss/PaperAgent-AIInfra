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
paper-agent web -c config.yaml                     # launch web UI on 127.0.0.1:8000
paper-agent web --host 0.0.0.0 --port 9000 -c config.yaml  # custom bind
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
├── ScoringConfig     (global: model, batch_size, api_key, base_url, max_tokens,
│                      temperature, tool_choice, abstract_max_length,
│                      relevance_weight, quality_weight, prompts: PromptsConfig)
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

Uses Claude's `tool_use` for structured output. The `SCORE_TOOL` schema includes:
- `relevance_score` (0-10): AI Infra relevance
- `quality_score` (0-10): overall quality
- `summary_zh`: Chinese summary
- `sub_domain_tags` (1-3 tags from the enum): sub-domain classification

Papers are scored in batches (default 10) to reduce API calls.

**Configurable `ScoringConfig` fields** (all optional, with sensible defaults matching prior hardcoded values):
- `api_key` / `base_url`: LLM API connection. Supports `${ENV_VAR}` interpolation. `api_key=None` falls back to `ANTHROPIC_API_KEY` env var.
- `max_tokens` (default 4096), `temperature` (default `None` = omitted from API call), `tool_choice` (`"auto"` or `"tool"`).
- `abstract_max_length` (default 800): chars to keep when truncating abstracts.
- `relevance_weight` / `quality_weight` (default 0.6 / 0.4): used by `ScoreWeights` / `sort_by_score(papers, weights=...)` for per-user sorting. A warning is logged when the sum isn't ~1.0.
- `prompts.system_prompt` / `prompts.user_message_template`: optional overrides for the scoring prompts. The user-message template supports `{paper_count}` and `{papers}` placeholders. `None` or empty falls back to the built-in defaults (`SYSTEM_PROMPT`, etc.).

`ScoredPaper.total_score` remains a property using default 0.6/0.4 weights for backward compatibility. Pipeline-level weighted sorting goes through `sort_by_score(papers, weights=ScoreWeights.from_scoring_config(config.scoring))`.

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
- `list_papers(sub_domains, search, limit, offset)`: paginated filtered list (web UI)
- `count_papers(sub_domains, search)`: matching count for pagination
- `get_sub_domain_counts()`: per-tag paper counts for chip badges

Connections are opened with WAL journal mode and a 30-second busy timeout so the web server can read concurrently while the daemon writes.

### Web Frontend (`web/`)

A FastAPI + Jinja2 + HTMX web UI launched by `paper-agent web`. The server is a **stateless reader** over the existing `papers` table — it does not own user identity, sessions, or preference storage.

**Files:**
- `web/app.py`: `create_app(config)` factory; mounts `/static` and Jinja2 templates.
- `web/routes.py`: `/` (full page), `/_paper_list` (HTMX partial), `/health`.
- `web/deps.py`: `get_db()` dependency (per-request `PaperDatabase`).
- `web/templates/`: `base.html`, `index.html`, `_paper_list.html`.
- `web/static/`: `style.css`, `preferences.js`, `app.js`, `vendor/htmx.min.js`.

**Preferences live in browser `localStorage`** under the key `paper_agent_prefs` with shape `{ mode: "all" | "custom", subDomains: string[] }`. The client JS (`preferences.js`) reads prefs on load, validates sub-domain tags against `SUB_DOMAINS` keys, and translates them into URL query params (`?sub_domain=...&q=...`) when fetching `/_paper_list` via HTMX. A `?mode=all|custom` URL override writes the value to `localStorage` and strips the param from the address bar.

**Sub-domain chip filter** on the main page and the **preferences panel checkboxes** share the same `subDomains` array in `localStorage`. Toggling either updates the other and re-fetches the paper list.

### Notifier Plugins (`notifier/`)

Protocol-based (structural typing). `create_notifiers_for_user(UserNotifyConfig)` builds a notifier list for one user. Each notifier handles platform-specific quirks:
- **Email**: SMTP + HTML templates
- **企业微信**: Markdown, 4096-byte limit → auto-splits
- **飞书**: Rich text `post` format (structured JSON)
- **钉钉**: Markdown + HMAC-SHA256 signature

## Environment Variables

Required (unless `scoring.api_key` is set in `config.yaml`):
- `ANTHROPIC_API_KEY`: Claude API key

Optional (per-user webhook/SMTP credentials configured in config.yaml):
- `FEISHU_WEBHOOK_<USER>`, `WECOM_WEBHOOK`, `DINGTALK_WEBHOOK`, `DINGTALK_SECRET`
- `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_SENDER`

## Config Migration

The config format changed from single-user to multi-user. Old `config.yaml` files with a top-level `notify:` section must be rewritten using the new `users:` list format. See `config.example.yaml` for the current structure.
