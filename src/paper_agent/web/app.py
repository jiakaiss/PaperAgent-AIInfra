"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from paper_agent.config import AppConfig

WEB_DIR = Path(__file__).parent


def create_app(config: AppConfig) -> FastAPI:
    """Build and return a configured FastAPI application."""
    app = FastAPI(title="Paper Agent", docs_url=None, redoc_url=None)
    app.state.config = config

    # Mount static assets
    app.mount(
        "/static",
        StaticFiles(directory=str(WEB_DIR / "static")),
        name="static",
    )

    # Jinja2 templates
    templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))
    app.state.templates = templates

    # Register route handlers
    from paper_agent.web.routes import router

    app.include_router(router)

    return app
