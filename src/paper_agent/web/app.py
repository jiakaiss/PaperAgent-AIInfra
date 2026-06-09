"""FastAPI application factory."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from paper_agent.config import AppConfig
from paper_agent.subscriptions import load_subscriptions_into_config

logger = logging.getLogger(__name__)

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
    templates.env.globals["admin_css_version"] = _file_version("admin.css")
    app.state.templates = templates

    # Register route handlers
    from paper_agent.web.routes import router

    app.include_router(router)

    # Admin dashboard — registered only when explicitly enabled AND a
    # non-empty password is configured. When disabled, every /admin* URL
    # falls through to FastAPI's default 404 (by design — never advertise
    # that the surface exists when it's not actually configured).
    if config.admin.is_active:
        # Defensive normalization: a misconfig with an empty username
        # would compare against an empty bytes object and accept any
        # client-provided empty username. compare_digest is constant-time
        # but the underlying behavior is still wrong. Force the default.
        if not config.admin.username.strip():
            logger.warning("admin enabled with empty username — falling back to 'admin'")
            config.admin.username = "admin"

        from paper_agent.web.admin import router as admin_router

        app.include_router(admin_router)
        logger.info("Admin dashboard enabled at /admin (user=%s)", config.admin.username)
    else:
        logger.info(
            "Admin dashboard disabled (admin.enabled=%s, password set=%s)",
            config.admin.enabled,
            bool(config.admin.password.strip()),
        )

    return app
