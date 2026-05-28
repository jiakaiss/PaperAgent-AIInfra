"""FastAPI dependency injection helpers."""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Request

from paper_agent.config import AppConfig
from paper_agent.storage.database import PaperDatabase


def get_config(request: Request) -> AppConfig:
    """Return the :class:`AppConfig` stored on the FastAPI app state."""
    return request.app.state.config


def get_db(request: Request) -> Generator[PaperDatabase, None, None]:
    """Yield a per-request :class:`PaperDatabase` instance."""
    config: AppConfig = request.app.state.config
    db = PaperDatabase(config.storage.db_path)
    try:
        yield db
    finally:
        # PaperDatabase opens/closes per _connect() call; nothing to close here.
        pass
