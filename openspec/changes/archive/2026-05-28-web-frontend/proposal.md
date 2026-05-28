## Why

Today `paper-agent` is push-only: the pipeline runs on a schedule and blasts per-user digests to email / 飞书 / 钉钉 / 企微. Users can only tune their interests by editing `config.yaml` — painful on mobile, impossible to experiment with quickly. There is no way to *browse* the corpus of papers the agent has already scored, no way to preview what a different subscription would look like, and no interactive surface for the product at all.

Adding a lightweight web UI lets users self-serve their paper feed, flip between "my chosen sub-domains" and "everything" without touching config, and actually *see* what the agent is doing — turning a background cron job into a usable product.

## What Changes

- Add a **FastAPI-based web server** with Jinja2 templates, launched via a new CLI command `paper-agent web [--host] [--port]`. The existing `run` / `daemon` / `test` / `stats` commands are untouched.
- Add **browser-side preferences** stored in `localStorage`: each visitor has a chosen *mode* (`custom` vs `all`) and a list of selected sub-domain keywords from the 14 predefined options. No login, no custom free-text keywords. Preferences live in the browser; the server stays stateless with respect to user identity.
- Add a **paper browsing UI** that lists scored papers with filters (mode-aware, sub-domain chips, search by title, pagination). Each paper card shows title, authors, Chinese summary, sub-domain tags, relevance / quality scores, and arXiv link.
- Add a **mode toggle** on the page: "只看我的关键词" ↔ "查看全部论文". The preference is persisted in the browser's localStorage.
- Add new **query methods** to `PaperDatabase` (list/filter/paginate) so the web layer can read the existing `papers` table without re-scoring.
- The **core pipeline is unchanged**: fetch → dedup → score → cache → per-user filter → notify still runs exactly as today. The web UI reads the *same* cache that the pipeline writes.

## Capabilities

### New Capabilities
- `web-server`: FastAPI application, Jinja2 templates, static assets, and the `paper-agent web` CLI command that launches it. No session/auth layer.
- `user-preferences`: Client-side preference store (localStorage): chosen mode (`custom` / `all`) and selected sub-domain keywords. Includes a preferences UI (modal/panel) for editing and a JS module for reading/writing.
- `paper-browsing`: Paginated, filterable paper list endpoint and template; supports sub-domain filtering, title search, mode-aware filtering (custom vs all), and per-paper detail.

### Modified Capabilities

## Impact

- **New dependencies**: `fastapi`, `uvicorn[standard]`, `python-multipart`, `starlette` (transitive). Jinja2 is already present.
- **New package**: `src/paper_agent/web/` with `app.py`, `routes.py`, `templates/`, `static/`.
- **Storage layer**: `storage/database.py` gains ~5 new read/query methods (`list_papers`, `count_papers`, `get_sub_domain_counts`, etc.). The existing `papers` and `sent_papers` tables are unchanged in schema. **No new tables.**
- **CLI**: new `paper-agent web` command in `cli.py`.
- **Tests**: new test files under `tests/` for routes, preferences, and browsing queries.
- **Deployment**: the web server is a separate long-running process; it can run alongside `paper-agent daemon` (they share the same SQLite file). No breaking changes to existing configs or commands.
