"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from paper_agent.config import AppConfig
from paper_agent.subscriptions import load_subscriptions_into_config

WEB_DIR = Path(__file__).parent


def create_app(config: AppConfig) -> FastAPI:
    """Build and return a configured FastAPI application."""
    app = FastAPI(title="Paper Agent", docs_url=None, redoc_url=None)
    app.state.config = config

    # Load subscriptions from database on startup
    load_subscriptions_into_config(config)

    # Mount static assets
    static_dir = WEB_DIR / "static"
    app.mount(
        "/static",
        StaticFiles(directory=str(static_dir)),
        name="static",
    )

    # Jinja2 templates
    templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))
    # Cache-busting versions for /static/* files — derived from file mtime so
    # any edit auto-invalidates the browser cache without manual refresh.
    def _file_version(filename: str) -> str:
        try:
            return str(int((static_dir / filename).stat().st_mtime))
        except OSError:
            return "0"

    templates.env.globals["style_version"] = _file_version("style.css")
    templates.env.globals["prefs_version"] = _file_version("preferences.js")
    templates.env.globals["app_version"] = _file_version("app.js")
    app.state.templates = templates

    # Register route handlers
    from paper_agent.web.routes import router

    app.include_router(router)

    return app
