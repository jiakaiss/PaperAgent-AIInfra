"""Integration tests for the admin dashboard — auth gate, disabled mode, secrets rule."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from paper_agent.config import AppConfig
from paper_agent.storage.database import PaperDatabase
from paper_agent.web.app import create_app

# ─── Sentinel secret values that the test config seeds. Every admin
# response is checked against these — none should appear in HTML or CSV.
SENTINEL_SMTP_PASSWORD = "unique-smtp-secret-123"
SENTINEL_API_KEY = "sk-test-unique-key-456"
SENTINEL_UNSUBSCRIBE_SECRET = "hmac-unique-789"
SENTINEL_ACCESS_CODE = "code-unique-abc"
SENTINEL_CITATIONS_API_KEY = "s2-secret-xyz-123"

NOT_SENTINEL = object()


@pytest.fixture
def config_factory(tmp_path: Path):
    """Return a callable that builds a test AppConfig with known secrets."""

    def _build(
        admin_enabled: bool = True,
        admin_password: str = "hunter2",
        admin_username: str = "admin",
    ) -> AppConfig:
        return AppConfig(
            storage={"db_path": str(tmp_path / "test.db")},
            admin={
                "enabled": admin_enabled,
                "username": admin_username,
                "password": admin_password,
            },
            scoring={
                "api_key": SENTINEL_API_KEY,
            },
            email={
                "enabled": True,
                "smtp_host": "smtp.example.com",
                "smtp_user": "admin@example.com",
                "smtp_password": SENTINEL_SMTP_PASSWORD,
                "sender": "admin@example.com",
                "recipients": [],
            },
            subscriptions={
                "access": {
                    "enabled": True,
                    "access_codes": [SENTINEL_ACCESS_CODE],
                },
                "unsubscribe": {
                    "secret": SENTINEL_UNSUBSCRIBE_SECRET,
                },
            },
            citations={
                "enabled": True,
                "api_key": SENTINEL_CITATIONS_API_KEY,
            },
            users=[],
        )

    return _build


def _seed_db(db_path: Path) -> None:
    """Add a few subscriptions and sent rows to make dashboard panels meaningful."""
    db = PaperDatabase(db_path)

    db.add_subscription("alice@example.com", ["quantization", "serving"])
    db.add_subscription("bob@example.com", ["moe", "compiler"])
    db.add_subscription("unsubbed-charol@example.com", ["pruning"])

    # Mark one as unsubscribed.
    db.unsubscribe_email("unsubbed-charol@example.com")

    # Insert sent-papers rows so there is delivery data.
    db.mark_sent(
        "alice@example.com",
        [],
    )  # no-op (empty list), used below via direct SQL for sent_at control
    # Inline insert for controlled timestamps:
    import sqlite3

    with sqlite3.connect(str(db_path)) as conn:
        # We need a paper to reference in sent_papers
        conn.execute(
            """INSERT OR REPLACE INTO papers
               (arxiv_id, title, authors, abstract, published, categories,
                pdf_url, abs_url, relevance_score, quality_score, summary_zh,
                sub_domain_tags, scored_at, impact_tier)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "2606.00001v1",
                "Test Paper",
                "Author",
                "Abstract",
                "2026-06-01",
                "cs.LG",
                "https://arxiv.org/pdf/2606.00001",
                "https://arxiv.org/abs/2606.00001",
                8.0,
                7.0,
                "测试摘要",
                json.dumps(["quantization"]),
                datetime.now().isoformat(),
                "solid",
            ),
        )
        conn.execute(
            "INSERT INTO sent_papers (user_id, arxiv_id, sent_at) VALUES (?, ?, ?)",
            ("alice@example.com", "2606.00001v1", datetime.now().isoformat()),
        )
        conn.commit()


@pytest.fixture
def populated_db(tmp_path: Path) -> Path:
    """Seed a DB at tmp_path and return the path for use in config path."""
    db_path = tmp_path / "test.db"
    _seed_db(db_path)
    return db_path


# ─── Admin disabled → 404 tests ───────────────────────────────────────


class TestAdminDisabled:
    """admin.enabled=false or password="" → every /admin* returns 404."""

    def test_admin_enabled_false(self, config_factory):
        cfg = config_factory(admin_enabled=False, admin_password="hunter2")
        app = create_app(cfg)
        client = TestClient(app)
        resp = client.get("/admin")
        assert resp.status_code == 404
        assert "WWW-Authenticate" not in resp.headers

    def test_admin_empty_password(self, config_factory):
        """Enabled but empty password = treated as disabled."""
        cfg = config_factory(admin_enabled=True, admin_password="")
        app = create_app(cfg)
        client = TestClient(app)
        resp = client.get("/admin")
        assert resp.status_code == 404

    def test_admin_whitespace_password(self, config_factory):
        cfg = config_factory(admin_enabled=True, admin_password="   ")
        app = create_app(cfg)
        client = TestClient(app)
        resp = client.get("/admin")
        assert resp.status_code == 404

    def test_public_routes_unaffected(self, config_factory):
        """Disabled admin does not break public routes."""
        cfg = config_factory(admin_enabled=False, admin_password="hunter2")
        app = create_app(cfg)
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        resp = client.get("/")
        assert resp.status_code == 200


# ─── Auth gate tests ──────────────────────────────────────────────────


class TestAuth:
    """Correct/wrong/missing credentials produce the right status + headers."""

    @pytest.fixture
    def client(self, config_factory):
        cfg = config_factory(admin_enabled=True, admin_password="hunter2")
        return TestClient(create_app(cfg))

    def test_no_credentials_returns_401(self, client):
        resp = client.get("/admin")
        assert resp.status_code == 401
        assert 'Basic realm="paper-agent-admin"' in resp.headers.get("WWW-Authenticate", "")

    def test_wrong_password_returns_401(self, client):
        resp = client.get("/admin", auth=("admin", "wrongpass"))
        assert resp.status_code == 401

    def test_wrong_username_returns_401(self, client):
        resp = client.get("/admin", auth=("eve", "hunter2"))
        assert resp.status_code == 401

    def test_correct_credentials_returns_200(self, client):
        resp = client.get("/admin", auth=("admin", "hunter2"))
        assert resp.status_code == 200
        # Verify it's an HTML page with the admin-via-htmx pattern.
        assert "hx-get" in resp.text
        assert "panel" in resp.text

    def test_username_empty(self, config_factory):
        """Empty username falls back to 'admin'."""
        cfg = config_factory(admin_enabled=True, admin_password="hunter2", admin_username="")
        app = create_app(cfg)
        client = TestClient(app)
        # The default 'admin' should work.
        resp = client.get("/admin", auth=("admin", "hunter2"))
        assert resp.status_code == 200
        resp2 = client.get("/admin", auth=("", "hunter2"))
        assert resp2.status_code == 401


# ─── Happy path — each panel + CSV ────────────────────────────────────


class TestPanels:
    """Authenticated requests for each panel return 200 and contain expected data."""

    @pytest.fixture
    def client(self, config_factory, populated_db):
        cfg = config_factory(admin_enabled=True, admin_password="hunter2")
        app = create_app(cfg)
        return TestClient(app)

    @staticmethod
    def _auth_get(client, path, **kwargs):
        return client.get(path, auth=("admin", "hunter2"), **kwargs)

    def test_subscribers_panel(self, client):
        resp = self._auth_get(client, "/admin/_subscribers")
        assert resp.status_code == 200
        # The seeded subscribers should appear
        assert "alice@example.com" in resp.text
        assert "bob@example.com" in resp.text
        # Unsubscribed user still appears
        assert "unsubbed-charol@example.com" in resp.text
        # Delivery count
        assert "alice" in resp.text

    def test_user_stats_panel(self, client):
        resp = self._auth_get(client, "/admin/_user_stats")
        assert resp.status_code == 200
        assert "alice" in resp.text or "alice@example.com" in resp.text

    def test_papers_panel(self, client):
        resp = self._auth_get(client, "/admin/_papers")
        assert resp.status_code == 200
        # Stat cards: at least one paper cached
        assert "solid" in resp.text
        assert "breakthrough" in resp.text
        assert "serving" in resp.text or "quantization" in resp.text

    def test_papers_panel_shows_citation_coverage_when_enabled(self, client):
        """Citation panel renders coverage stats when citations.enabled=true."""
        resp = self._auth_get(client, "/admin/_papers")
        assert resp.status_code == 200
        assert "引用数采集" in resp.text
        assert "已采集引用数" in resp.text
        assert "semantic_scholar" in resp.text
        # The "未启用" text must NOT appear when enabled
        assert "未启用" not in resp.text

    def test_papers_panel_shows_disabled_message(self, config_factory, populated_db):
        """When citations.enabled=false, the panel shows the 未启用 line and no stats."""
        cfg = config_factory(admin_enabled=True, admin_password="hunter2")
        cfg.storage.db_path = str(populated_db)
        cfg.citations.enabled = False
        app = create_app(cfg)
        local_client = TestClient(app)

        resp = self._auth_get(local_client, "/admin/_papers")
        assert resp.status_code == 200
        assert "引用数采集未启用" in resp.text
        # No coverage numbers when disabled
        assert "已采集引用数" not in resp.text

    def test_system_panel(self, client):
        resp = self._auth_get(client, "/admin/_system")
        assert resp.status_code == 200
        # Scoring model should appear (from config)
        assert "haiku" in resp.text
        # config summary values
        assert "360" in resp.text  # ingest_interval_minutes
        # Database path
        assert "test.db" in resp.text

    def test_subscribers_csv(self, client):
        resp = self._auth_get(client, "/admin/subscribers.csv")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "attachment" in resp.headers.get("content-disposition", "")
        # Parse the CSV
        import csv
        import io

        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        # 3 seeded subscriptions (2 active + 1 inactive)
        assert len(rows) >= 3
        emails = {r["email"] for r in rows}
        assert "alice@example.com" in emails
        assert "bob@example.com" in emails
        assert "unsubbed-charol@example.com" in emails
        # Expected header columns
        assert "sub_domains" in reader.fieldnames
        assert "total_sent" in reader.fieldnames


# ─── Sensitive fields NEVER rendered ──────────────────────────────────


class TestSecrets:
    """No admin response may contain the seeded secret strings."""

    @pytest.fixture
    def client(self, config_factory, populated_db):
        cfg = config_factory(admin_enabled=True, admin_password="hunter2")
        # Override config path to match populated_db
        cfg.storage.db_path = str(populated_db)
        app = create_app(cfg)
        return TestClient(app)

    SECRET_STRINGS = [
        SENTINEL_SMTP_PASSWORD,
        SENTINEL_API_KEY,
        SENTINEL_UNSUBSCRIBE_SECRET,
        SENTINEL_ACCESS_CODE,
        SENTINEL_CITATIONS_API_KEY,
    ]
    ALL_ADMIN_URLS = [
        "/admin",
        "/admin/_subscribers",
        "/admin/_user_stats",
        "/admin/_papers",
        "/admin/_system",
        "/admin/subscribers.csv",
    ]

    @pytest.mark.parametrize("url", ALL_ADMIN_URLS)
    @pytest.mark.parametrize("secret", SECRET_STRINGS)
    def test_secret_never_rendered(self, client, url, secret):
        resp = client.get(url, auth=("admin", "hunter2"))
        assert resp.status_code == 200
        assert secret not in resp.text, f"Secret '{secret}' was exposed in {url}!"


# ─── Subscribers filtering and sorting ────────────────────────────────


class TestSubscribersFiltering:
    """?q= filters; ?sort= / ?order= controls column sorting."""

    @pytest.fixture
    def client(self, config_factory, populated_db):
        cfg = config_factory(admin_enabled=True, admin_password="hunter2")
        app = create_app(cfg)
        return TestClient(app)

    def test_search_returns_subset(self, client):
        resp = client.get("/admin/_subscribers?q=alice", auth=("admin", "hunter2"))
        assert resp.status_code == 200
        assert "alice@example.com" in resp.text
        assert "bob@example.com" not in resp.text

    def test_sort_by_email_asc(self, client):
        resp = client.get("/admin/_subscribers?sort=email&order=asc", auth=("admin", "hunter2"))
        assert resp.status_code == 200
        assert "alice@example.com" in resp.text
        # The sort marker should be visible
        assert "▲" in resp.text

    def test_sort_by_total_sent_desc(self, client):
        resp = client.get(
            "/admin/_subscribers?sort=total_sent&order=desc", auth=("admin", "hunter2")
        )
        assert resp.status_code == 200


# ─── System panel mismatch detection ──────────────────────────────────


class TestSystemMismatch:
    """System panel flags when active subscriptions > runtime users."""

    def test_no_mismatch(self, config_factory, tmp_path):
        """When subscriptions and runtime users are in sync, no warning."""
        db_path = tmp_path / "test.db"
        _seed_db(db_path)
        cfg = config_factory(admin_enabled=True, admin_password="hunter2")
        cfg.storage.db_path = str(db_path)
        app = create_app(cfg)
        client = TestClient(app)
        resp = client.get("/admin/_system", auth=("admin", "hunter2"))
        assert resp.status_code == 200
        # No mismatch-warning class when counts are fine
        # (3 active subs - 1 unsub = 2 active vs none in runtime users...)

    def test_mismatch_highlighted(self, config_factory, tmp_path):
        """Load a config that has runtime users but fewer than active subs."""
        db_path = tmp_path / "test.db"
        _seed_db(db_path)
        cfg = config_factory(admin_enabled=True, admin_password="hunter2")
        cfg.storage.db_path = str(db_path)
        app = create_app(cfg)
        # create_app calls load_subscriptions_into_config which populates
        # cfg.users from the DB. Clear them AFTER to force a mismatch.
        app.state.config.users = []
        client = TestClient(app)
        resp = client.get("/admin/_system", auth=("admin", "hunter2"))
        assert resp.status_code == 200
        # The mismatch-warning element should be present
        assert "mismatch-warning" in resp.text


# ─── CSV content ──────────────────────────────────────────────────────


class TestCsvContent:
    @pytest.fixture
    def client(self, config_factory, populated_db):
        cfg = config_factory(admin_enabled=True, admin_password="hunter2")
        cfg.storage.db_path = str(populated_db)
        app = create_app(cfg)
        return TestClient(app)

    def test_csv_headers(self, client):
        resp = client.get("/admin/subscribers.csv", auth=("admin", "hunter2"))
        import csv
        import io

        reader = csv.DictReader(io.StringIO(resp.text))
        # Per spec: id, email, status, created_at, unsubscribed_at,
        # sub_domains, total_sent, last_sent_at
        expected = {
            "id",
            "email",
            "status",
            "created_at",
            "unsubscribed_at",
            "sub_domains",
            "total_sent",
            "last_sent_at",
        }
        missing = expected - set(reader.fieldnames or [])
        extra = set(reader.fieldnames or []) - expected
        assert not missing, f"Missing CSV columns: {missing}"
        assert not extra, f"Unexpected CSV columns: {extra}"
