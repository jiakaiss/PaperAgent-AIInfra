"""Tests for subscription access control API behavior."""

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from paper_agent.config import (
    AppConfig,
    EmailNotifierConfig,
    StorageConfig,
    SubscriptionAccessConfig,
    SubscriptionDefaultsConfig,
)
from paper_agent.storage.database import PaperDatabase
from paper_agent.web.app import create_app


def _configured_email() -> EmailNotifierConfig:
    return EmailNotifierConfig(
        enabled=True,
        smtp_host="smtp.example.com",
        smtp_user="system@example.com",
        smtp_password="secret",
        sender="noreply@example.com",
    )


def _client(access_enabled: bool = False):
    tmpdir = tempfile.TemporaryDirectory()
    db_path = Path(tmpdir.name) / "test.db"
    config = AppConfig(
        email=_configured_email(),
        storage=StorageConfig(db_path=str(db_path)),
        subscriptions=SubscriptionDefaultsConfig(
            send_initial_digest_on_signup=False,
            access=SubscriptionAccessConfig(
                enabled=access_enabled,
                access_codes=["let-me-in"] if access_enabled else [],
            ),
        ),
    )
    app = create_app(config)
    return tmpdir, TestClient(app), config, db_path


def test_access_gate_disabled_does_not_require_code():
    tmpdir, client, _, _ = _client(access_enabled=False)
    try:
        response = client.post(
            "/api/subscribe",
            data={"email": "user@example.com", "sub_domain": ["quantization"]},
        )
        assert response.status_code == 200
        assert "成功" in response.text
    finally:
        tmpdir.cleanup()


def test_access_gate_valid_code_allows_subscription():
    tmpdir, client, _, _ = _client(access_enabled=True)
    try:
        response = client.post(
            "/api/subscribe",
            data={
                "email": "user@example.com",
                "sub_domain": ["quantization"],
                "access_code": "let-me-in",
            },
        )
        assert response.status_code == 200
        assert "成功" in response.text
    finally:
        tmpdir.cleanup()


def test_access_gate_missing_code_rejects_without_write():
    tmpdir, client, _, db_path = _client(access_enabled=True)
    try:
        response = client.post(
            "/api/subscribe",
            data={"email": "user@example.com", "sub_domain": ["quantization"]},
        )
        assert response.status_code == 200
        assert "授权码" in response.text
        assert not PaperDatabase(db_path).is_email_subscribed("user@example.com")
    finally:
        tmpdir.cleanup()


def test_access_gate_invalid_code_rejects_without_write():
    tmpdir, client, _, db_path = _client(access_enabled=True)
    try:
        response = client.post(
            "/api/subscribe",
            data={
                "email": "user@example.com",
                "sub_domain": ["quantization"],
                "access_code": "wrong",
            },
        )
        assert response.status_code == 200
        assert "授权码" in response.text
        assert not PaperDatabase(db_path).is_email_subscribed("user@example.com")
    finally:
        tmpdir.cleanup()
