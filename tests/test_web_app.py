"""Tests for the FastAPI app factory, /health, and basic / rendering."""

import os
import tempfile
from datetime import datetime

import pytest
from starlette.testclient import TestClient

from paper_agent.config import AppConfig, StorageConfig
from paper_agent.models import Paper, ScoredPaper
from paper_agent.storage.database import PaperDatabase
from paper_agent.web.app import create_app


def _make_scored_paper(arxiv_id: str = "2401.00001v1") -> ScoredPaper:
    paper = Paper(
        arxiv_id=arxiv_id,
        title="Test Paper on Quantization",
        authors=["Alice", "Bob"],
        abstract="Test abstract",
        published=datetime(2024, 1, 15),
        categories=["cs.DC"],
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        abs_url=f"https://arxiv.org/abs/{arxiv_id}",
    )
    return ScoredPaper(
        paper=paper,
        relevance_score=8.0,
        quality_score=7.0,
        summary_zh="测试论文",
        sub_domain_tags=("quantization",),
    )


@pytest.fixture
def db_path():
    """Yield a temp DB path pre-seeded with one paper."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    db = PaperDatabase(path)
    db.cache_papers([_make_scored_paper()])
    yield path
    os.unlink(path)


@pytest.fixture
def client(db_path):
    cfg = AppConfig(storage=StorageConfig(db_path=db_path))
    app = create_app(cfg)
    return TestClient(app)


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_index_returns_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Paper Agent" in resp.text


def test_index_contains_paper_list_container(client):
    resp = client.get("/")
    assert "paper-list-container" in resp.text


def test_paper_list_fragment(client):
    resp = client.get("/_paper_list")
    assert resp.status_code == 200
    assert "Test Paper on Quantization" in resp.text
    assert "quantization" in resp.text


def test_static_css_served(client):
    resp = client.get("/static/style.css")
    assert resp.status_code == 200
    assert "text/css" in resp.headers["content-type"]


def test_static_preferences_js_served(client):
    resp = client.get("/static/preferences.js")
    assert resp.status_code == 200
    assert "PaperAgentPrefs" in resp.text
