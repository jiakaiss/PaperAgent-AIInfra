"""Tests for unsubscribe flow."""

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from paper_agent.config import (
    AppConfig,
    EmailNotifierConfig,
    StorageConfig,
    SubscriptionDefaultsConfig,
    UnsubscribeConfig,
    WebConfig,
)
from paper_agent.storage.database import PaperDatabase
from paper_agent.unsubscribe import sign_unsubscribe_token
from paper_agent.web.app import create_app


def _app_with_subscription():
    tmpdir = tempfile.TemporaryDirectory()
    db_path = Path(tmpdir.name) / "test.db"
    db = PaperDatabase(db_path)
    db.add_subscription("user@example.com", ["quantization"])
    config = AppConfig(
        email=EmailNotifierConfig(
            enabled=True,
            smtp_host="smtp.example.com",
            smtp_user="system@example.com",
            smtp_password="secret",
        ),
        storage=StorageConfig(db_path=str(db_path)),
        subscriptions=SubscriptionDefaultsConfig(
            unsubscribe=UnsubscribeConfig(secret="secret", token_max_age_hours=720)
        ),
        web=WebConfig(public_base_url="https://papers.example.com"),
    )
    app = create_app(config)
    return tmpdir, TestClient(app), db_path, config


def test_valid_unsubscribe_link_displays_confirmation():
    tmpdir, client, _, _ = _app_with_subscription()
    try:
        token = sign_unsubscribe_token("user@example.com", "secret")
        response = client.get(f"/unsubscribe?email=user@example.com&token={token}")
        assert response.status_code == 200
        assert "确认取消" in response.text
        assert "user@example.com" in response.text
    finally:
        tmpdir.cleanup()


def test_invalid_unsubscribe_token_rejected():
    tmpdir, client, db_path, _ = _app_with_subscription()
    try:
        response = client.get("/unsubscribe?email=user@example.com&token=bad")
        assert response.status_code == 200
        assert "无效或已过期" in response.text
        assert PaperDatabase(db_path).get_subscription("user@example.com")["status"] == "active"
    finally:
        tmpdir.cleanup()


def test_confirm_unsubscribe_marks_inactive_and_removes_runtime_user():
    tmpdir, client, db_path, config = _app_with_subscription()
    try:
        assert "user@example.com" in [u.user_id for u in config.users]
        token = sign_unsubscribe_token("user@example.com", "secret")
        response = client.post(
            "/unsubscribe",
            data={"email": "user@example.com", "token": token},
        )
        assert response.status_code == 200
        assert "已取消订阅" in response.text
        sub = PaperDatabase(db_path).get_subscription("user@example.com")
        assert sub["status"] == "inactive"
        assert sub["unsubscribed_at"] is not None
        assert "user@example.com" not in [u.user_id for u in config.users]
    finally:
        tmpdir.cleanup()


def test_unsubscribe_already_inactive_is_successful():
    tmpdir, client, db_path, _ = _app_with_subscription()
    try:
        db = PaperDatabase(db_path)
        assert db.unsubscribe_email("user@example.com") is True
        token = sign_unsubscribe_token("user@example.com", "secret")
        response = client.post(
            "/unsubscribe",
            data={"email": "user@example.com", "token": token},
        )
        assert response.status_code == 200
        assert "已取消订阅" in response.text
        assert db.get_subscription("user@example.com")["status"] == "inactive"
    finally:
        tmpdir.cleanup()
