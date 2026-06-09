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
# Admin dashboard lives at /admin (enable via config.admin + ADMIN_PASSWORD env var).
# See "Admin Dashboard" section below for details.

# Backfill cached papers scored before the structured-insights upgrade.
# Re-scores rows where impact_tier / key_contributions are NULL; safe to interrupt.
paper-agent rescore --missing-fields -c config.yaml
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
Filter by tier (min_tier) → Filter by sub_domain tags → Filter by thresholds → Dedup per-user → Notify → mark_sent
```

The `Pipeline._build_superset_keywords()` method unions all users' subscribed sub-domain keywords with global fetch keywords, so a single arXiv fetch covers everyone's interests.

### Dual-Track Retrieval (`fetcher/arxiv_fetcher.py`)

When `fetch.quality_floor_strategy = "per_keyword_cap"`, the fetcher runs two parallel paths in the same fetch:

- **Track 1 (keyword)** — one query per individual keyword, each capped at `max(min_per_keyword, max_results // num_queries)` so a noisy keyword like `"serving"` can't dominate the budget and starve precise ones.
- **Track 2 (cross-list)** — one query per category in `fetch.cross_list_categories` (default empty; recommended `["cs.LG", "cs.DC"]`) for recent papers regardless of keyword match. Catches papers whose terminology doesn't match any subscribed keyword.

Both tracks dedup by `arxiv_id`; Track-1 records win on conflict so keyword provenance is preserved for debugging. Legacy mode (`quality_floor_strategy = "none"`, the default for existing configs) groups keywords in batches of 8 and skips Track 2 — identical to pre-upgrade behavior.

### Sub-Domain Taxonomy (`models.py`)

14 standard sub-domains, each with associated arXiv keywords:
```
quantization, distillation, pruning, sparsity, distributed_training,
parallelism, serving, speculative_decoding, kv_cache, moe, compiler,
memory_optimization, communication, scheduling
```

`SUB_DOMAINS` dict maps each sub-domain to its keyword list. The scorer emits 1-3 `sub_domain_tags` per paper.

### Impact Tier (`models.py`)

A coarse categorical signal the scorer assigns to every paper, used for triage UI and digest sorting:

```
IMPACT_TIERS = ("breakthrough", "solid", "incremental")
```

- **`breakthrough`** — novel technique or result likely to be widely cited or change practice
- **`solid`** — well-executed, useful work incrementally advancing a clear baseline (the default; most papers)
- **`incremental`** — minor variation, narrow scope, or limited evaluation

The tier is judged by the LLM (not derived from numeric scores). `sort_by_score()` sorts by `(tier_rank ASC, total_score DESC)` so a breakthrough paper always outranks higher-scoring solid papers. Web UI excludes `incremental` by default; per-user digests obey `UserThresholdsConfig.min_tier` (default `"solid"`). Helpers: `tier_rank(tier) -> int`, `DEFAULT_TIER = "solid"`.

### Multi-User Config (`config.py`)

Config structure (no backward compat with single-user format):
```python
AppConfig
├── FetchConfig       (global: categories, keywords, max_results, days_back,
│                      quality_floor_strategy, min_per_keyword,
│                      cross_list_categories)
├── ScoringConfig     (global: model, batch_size, api_key, base_url, max_tokens,
│                      temperature, tool_choice, abstract_max_length,
│                      relevance_weight, quality_weight, prompts: PromptsConfig)
├── users: list[UserConfig]    # ← per-user
│   └── UserConfig
│       ├── user_id, display_name
│       ├── SubscriptionConfig (sub_domains: ["all"] or specific list)
│       ├── UserNotifyConfig   (email, wecom, feishu, dingtalk)
│       └── UserThresholdsConfig (min_relevance, min_quality, top_n,
│                                  per_sub_domain_top_n, min_tier)
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
- `key_contributions` (1-3 short bullets, each ≤ 120 chars): distinguishing contributions
- `problem_statement_zh` (1-2 sentences): the problem the paper addresses
- `methods_zh` (1-2 sentences): the methods or approach used
- `impact_tier` (`breakthrough` / `solid` / `incremental`): coarse impact tier

Papers are scored in batches (default 10). After each batch the scorer logs a `tier distribution: breakthrough=N solid=M incremental=K` line for spot-checking calibration. Bullets exceeding the cap are truncated with a warning; unknown `impact_tier` values fall back to `"solid"` with a warning. After upgrading, fresh scoring runs use roughly ~30% more output tokens per paper due to the new prose fields.

**`relevance_weight` / `quality_weight` interaction with tier**: weights still control how `total_score` is computed within a tier, but tier rank is the primary sort key. So tweaking the weights only changes ordering inside a tier — to elevate a paper *across* tiers you need the LLM to reclassify it (e.g. via a sharper `prompts.system_prompt`).

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

The `papers` table gained 4 columns in the structured-insights upgrade — `key_contributions` (JSON-encoded TEXT), `problem_statement_zh`, `methods_zh`, `impact_tier`. The migration runs on startup via idempotent `ALTER TABLE ADD COLUMN` (guarded by `PRAGMA table_info` so repeat starts are no-ops). Legacy rows with NULL values read back as `()` / `""` / `""` / `"solid"` so they render gracefully in the web UI without forcing a rescore. Use `paper-agent rescore --missing-fields` to opt-in to backfilling them.

Key methods:
- `filter_uncached(ids)`: IDs not yet scored (need Claude API call)
- `cache_papers(scored)`: store scored papers (writes all 17 columns)
- `load_cached_papers(ids)`: retrieve previously scored papers
- `filter_unsent_for_user(user_id, ids)`: IDs not yet sent to specific user
- `mark_sent(user_id, papers)`: record delivery
- `list_papers(sub_domains, search, tiers, limit, offset)`: paginated filtered list. Tier filter uses `COALESCE(impact_tier, 'solid') IN (...)` so legacy NULL rows count as solid. Order: `impact_tier` rank ASC, then `total_score` DESC.
- `count_papers(sub_domains, search, tiers)`: matching count for pagination
- `get_sub_domain_counts()`: per-tag paper counts for chip badges
- `count_papers_missing_insights()` / `get_papers_missing_insights(limit, offset)`: used by the rescore backfill CLI

Connections are opened with WAL journal mode and a 30-second busy timeout so the web server can read concurrently while the daemon writes.

### Web Frontend (`web/`)

A FastAPI + Jinja2 + HTMX web UI launched by `paper-agent web`. The server is a **stateless reader** over the existing `papers` table — it does not own user identity, sessions, or preference storage.

**Files:**
- `web/app.py`: `create_app(config)` factory; mounts `/static` and Jinja2 templates.
- `web/routes.py`: `/` (full page), `/_paper_list` (HTMX partial), `/health`.
- `web/deps.py`: `get_db()` dependency (per-request `PaperDatabase`).
- `web/templates/`: `base.html`, `index.html`, `_paper_list.html`.
- `web/static/`: `style.css`, `preferences.js`, `app.js`, `vendor/htmx.min.js`.

**Preferences live in browser `localStorage`** under the key `paper_agent_prefs` with shape `{ mode: "all" | "custom", subDomains: string[], minTier: "breakthrough" | "solid" | "incremental" }`. The client JS (`preferences.js`) reads prefs on load, validates sub-domain tags against `SUB_DOMAINS` keys, validates `minTier` against `IMPACT_TIERS`, and translates them into URL query params (`?sub_domain=...&tier=...&q=...`) when fetching `/_paper_list` via HTMX. A `?mode=all|custom` URL override writes the value to `localStorage` and strips the param from the address bar.

**Tier filtering**: `/` and `/_paper_list` accept repeated `?tier=<value>` params. When no `tier` is provided, the server defaults to `{breakthrough, solid}` (excludes `incremental`). The preferences panel has a "minimum tier" radio control bound to `localStorage.minTier`:
- `breakthrough` → client sends `?tier=breakthrough` only
- `solid` (default) → client omits `?tier=` (server default kicks in)
- `incremental` → client sends `?tier=breakthrough&tier=solid&tier=incremental` (everything)

**Sub-domain chip filter** on the main page and the **preferences panel checkboxes** share the same `subDomains` array in `localStorage`. Toggling either updates the other and re-fetches the paper list.

### Web Subscriptions (`web/app.py`, `web/routes.py`)

Users can subscribe to paper digests via the `/subscribe` web form. Subscriptions are stored in the `subscriptions` table (SQLite) and loaded into `AppConfig.users` at startup.

**Global Email Configuration** (`config.email`):
- Subscription users inherit SMTP credentials from the global `email` config section in `config.yaml`
- When creating a subscription, the system copies `smtp_host`, `smtp_port`, `smtp_user`, `smtp_password`, `sender`, and `use_tls` from `config.email` to the user's `notify.email` config
- If `config.email.enabled=false` or critical SMTP fields are missing, subscription creation is rejected with an error message

**Subscription to UserConfig conversion**:
- At startup, `_load_subscriptions_into_config()` loads active subscriptions and creates `UserConfig` objects
- Each subscription user has `notify.email.enabled=true` and `notify.email.recipients=[email]`
- SMTP credentials are copied from `config.email` at conversion time (not stored in database)

**Important**: Changes to `config.email` in `config.yaml` require app restart to affect existing subscription users. New subscriptions will use the updated config immediately.

### Notifier Plugins (`notifier/`)

Protocol-based (structural typing). `create_notifiers_for_user(UserNotifyConfig)` builds a notifier list for one user. Each notifier handles platform-specific quirks:
- **Email**: SMTP + HTML templates
- **企业微信**: Markdown, 4096-byte limit → auto-splits
- **飞书**: Rich text `post` format (structured JSON)
- **钉钉**: Markdown + HMAC-SHA256 signature

### Admin Dashboard (`web/admin.py`)

Operator-only read-only dashboard at `/admin`, gated by HTTP Basic Auth. Off by default. Disabled or unconfigured admin returns **404** (not 401) so the surface is invisible until enabled — this is intentional and tested.

**Enable:**
```yaml
# config.yaml
admin:
  enabled: true
  username: admin
  password: ${ADMIN_PASSWORD}   # or a literal string
```
Then `export ADMIN_PASSWORD=$(openssl rand -base64 24)` and restart the web server. Visit `/admin`; the browser pops the native Basic Auth prompt.

**Routes** (all under `/admin`, all share the `verify_admin` dependency):
| Path | Returns |
|------|---------|
| `GET /admin` | Shell page with 4 HTMX-loaded panels |
| `GET /admin/_subscribers` | Subscriber table (search by email, sortable columns) |
| `GET /admin/_user_stats` | Per-user 7d/30d/total counts + 7-day daily-totals table |
| `GET /admin/_papers` | Cache stat cards, tier distribution (CSS bars), sub-domain distribution, 7-day daily-scored table |
| `GET /admin/_system` | Scoring model, schedule, SMTP host, DB path+size, last ingest/digest, active-vs-runtime mismatch flag |
| `GET /admin/subscribers.csv` | Full subscriber list as CSV download |

**Data sources:** all read-only queries via `PaperDatabase` aggregate methods (`get_user_stats`, `get_daily_sent_counts`, `get_daily_paper_counts`, `get_tier_distribution`, `count_active_subscriptions`, `list_subscriptions`, `get_last_ingest_at`, `get_last_digest_at`). No mutations — to delete sent records, change thresholds, or trigger a digest, still use CLI/SQL.

**Security invariants** (enforced by tests; do not violate when adding panels):
- Admin responses NEVER render `scoring.api_key`, `email.smtp_password`, `subscriptions.unsubscribe.secret`, or `subscriptions.access.access_codes`. Tests parameterize over every admin URL × every sentinel secret. New panels added in violation will fail `test_admin.py::TestSecrets::test_secret_never_rendered`.
- Never pass the raw `AppConfig` to a template — always project specific fields (see `admin_system()` for the pattern).
- `verify_admin` compares BOTH username and password with `secrets.compare_digest` even when the username is wrong, so wrong-username and wrong-password take indistinguishable time (no enumeration timing channel).
- The dashboard MUST be served over HTTPS in production — HTTP Basic Auth credentials transit in clear over plain HTTP.

**Toggling at runtime:** not supported. `admin.enabled` is read once at `create_app` time; flipping it requires a web server restart.

**Disabled-mode behavior:** when `admin.enabled=false` OR `admin.password` is empty/whitespace, the admin router is **not registered**. Every `/admin*` URL returns FastAPI's default 404 with no `WWW-Authenticate` header. Startup logs the chosen mode at INFO.

## Environment Variables

Required (unless `scoring.api_key` is set in `config.yaml`):
- `ANTHROPIC_API_KEY`: Claude API key

Optional (per-user webhook/SMTP credentials configured in config.yaml):
- `FEISHU_WEBHOOK_<USER>`, `WECOM_WEBHOOK`, `DINGTALK_WEBHOOK`, `DINGTALK_SECRET`
- `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_SENDER`
- `ADMIN_PASSWORD`: Admin dashboard password (when `admin.password: ${ADMIN_PASSWORD}` in config)

## Config Migration

The config format changed from single-user to multi-user. Old `config.yaml` files with a top-level `notify:` section must be rewritten using the new `users:` list format. See `config.example.yaml` for the current structure.

## Troubleshooting

### Subscription users not receiving emails

**Symptom**: Users subscribe via `/subscribe` but don't receive paper digest emails.

**Checklist**:
1. Verify `config.email.enabled=true` in `config.yaml`
2. Verify all required SMTP fields are set: `smtp_host`, `smtp_user`, `smtp_password`, `sender`
3. Check logs for warnings: "Email config enabled but missing fields" or "Global email config not configured"
4. Test SMTP credentials manually: `paper-agent test --notifier email --user <subscription_email>`
5. Verify the subscription exists: check `subscriptions` table in database or use `paper-agent stats`

**Common causes**:
- `config.email.enabled=false` or missing SMTP credentials → subscription rejected at creation time
- SMTP credentials changed after subscription → existing users still use old credentials (restart app to update)
- Invalid SMTP credentials → check email notifier logs for "Failed to send email" errors
- Firewall/network issues → test SMTP connectivity from the server

**Solution**: Ensure `config.email` is properly configured with valid SMTP credentials before users subscribe. If credentials change, restart the app to update existing subscription users.
