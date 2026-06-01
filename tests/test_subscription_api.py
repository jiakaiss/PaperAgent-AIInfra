"""Tests for subscription API endpoint."""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from paper_agent.config import AppConfig, EmailNotifierConfig, FetchConfig, ScoringConfig, StorageConfig, UserConfig
from paper_agent.web.app import create_app


@pytest.fixture
def app_with_db():
    """Create a test app with temporary database and properly configured email."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        config = AppConfig(
            fetch=FetchConfig(),
            scoring=ScoringConfig(api_key="test-key"),
            email=EmailNotifierConfig(
                enabled=True,
                smtp_host="smtp.example.com",
                smtp_user="system@example.com",
                smtp_password="secret",
                sender="noreply@example.com",
            ),
            users=[
                UserConfig(
                    user_id="admin@example.com",
                    display_name="Admin",
                    subscriptions={"sub_domains": ["all"]},
                )
            ],
            storage=StorageConfig(db_path=str(db_path)),
        )
        app = create_app(config)
        client = TestClient(app)
        yield client, config


def test_subscribe_page_loads(app_with_db):
    """Test that subscription page loads successfully."""
    client, _ = app_with_db
    response = client.get("/subscribe")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    # Should contain form elements
    assert "email" in response.text.lower()
    assert "submit" in response.text.lower() or "订阅" in response.text


def test_subscribe_success(app_with_db):
    """Test successful subscription submission."""
    client, config = app_with_db

    response = client.post(
        "/api/subscribe",
        data={"email": "newuser@example.com", "sub_domain": ["quantization", "distillation"]},
    )

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    # Should contain success message
    assert "success" in response.text.lower() or "成功" in response.text
    assert "newuser@example.com" in response.text
    # Should mention email delivery
    assert "配置好的邮箱" in response.text or "定期为您推送" in response.text

    # Verify user was added to runtime config
    user_ids = [u.user_id for u in config.users]
    assert "newuser@example.com" in user_ids


def test_subscribe_invalid_email(app_with_db):
    """Test subscription with invalid email format."""
    client, _ = app_with_db

    response = client.post(
        "/api/subscribe",
        data={"email": "not-an-email", "sub_domain": ["quantization"]},
    )

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    # Should contain error message
    assert "error" in response.text.lower() or "invalid" in response.text.lower() or "错误" in response.text


def test_subscribe_invalid_sub_domain(app_with_db):
    """Test subscription with invalid sub-domain."""
    client, _ = app_with_db

    response = client.post(
        "/api/subscribe",
        data={"email": "user@example.com", "sub_domain": ["invalid_domain"]},
    )

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    # Should contain error message about invalid sub-domain
    assert "error" in response.text.lower() or "invalid" in response.text.lower()


def test_subscribe_duplicate_email(app_with_db):
    """Test subscription with already-registered email."""
    client, _ = app_with_db

    # First subscription should succeed
    response1 = client.post(
        "/api/subscribe",
        data={"email": "duplicate@example.com", "sub_domain": ["quantization"]},
    )
    assert response1.status_code == 200
    assert "success" in response1.text.lower() or "成功" in response1.text

    # Second subscription with same email should indicate already subscribed
    response2 = client.post(
        "/api/subscribe",
        data={"email": "duplicate@example.com", "sub_domain": ["distillation"]},
    )
    assert response2.status_code == 200
    assert "already" in response2.text.lower() or "已经" in response2.text


def test_subscribe_empty_sub_domains(app_with_db):
    """Test subscription with no sub-domains selected."""
    client, _ = app_with_db

    response = client.post(
        "/api/subscribe",
        data={"email": "user@example.com", "sub_domain": []},
    )

    assert response.status_code == 200
    # Should contain error message
    assert "error" in response.text.lower() or "invalid" in response.text.lower()


def test_subscribe_multiple_sub_domains(app_with_db):
    """Test subscription with multiple valid sub-domains."""
    client, config = app_with_db

    sub_domains = ["quantization", "distillation", "pruning", "sparsity"]
    response = client.post(
        "/api/subscribe",
        data={"email": "multi@example.com", "sub_domain": sub_domains},
    )

    assert response.status_code == 200
    assert "success" in response.text.lower() or "成功" in response.text

    # Verify all sub-domains were saved
    user = next((u for u in config.users if u.user_id == "multi@example.com"), None)
    assert user is not None
    assert set(user.subscriptions.sub_domains) == set(sub_domains)


def test_subscribe_email_case_insensitive(app_with_db):
    """Test that email validation is case-insensitive."""
    client, config = app_with_db

    # Subscribe with uppercase email
    response = client.post(
        "/api/subscribe",
        data={"email": "UpperCase@Example.COM", "sub_domain": ["quantization"]},
    )
    assert response.status_code == 200
    assert "success" in response.text.lower() or "成功" in response.text

    # Email should be stored in lowercase
    user_ids = [u.user_id for u in config.users]
    assert "uppercase@example.com" in user_ids
    assert "UpperCase@Example.COM" not in user_ids


# ─── Email config validation tests ───


def test_subscribe_rejected_when_email_not_enabled():
    """Test that subscription is rejected when global email config is not enabled."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        config = AppConfig(
            email=EmailNotifierConfig(enabled=False),
            storage=StorageConfig(db_path=str(db_path)),
        )
        app = create_app(config)
        client = TestClient(app)

        response = client.post(
            "/api/subscribe",
            data={"email": "user@example.com", "sub_domain": ["quantization"]},
        )

        assert response.status_code == 200
        assert "系统未配置邮件发送功能" in response.text
        assert "请联系管理员" in response.text


def test_subscribe_rejected_when_smtp_host_missing():
    """Test that subscription is rejected when smtp_host is missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        config = AppConfig(
            email=EmailNotifierConfig(
                enabled=True,
                smtp_host="",  # missing
                smtp_user="system@example.com",
                smtp_password="secret",
            ),
            storage=StorageConfig(db_path=str(db_path)),
        )
        app = create_app(config)
        client = TestClient(app)

        response = client.post(
            "/api/subscribe",
            data={"email": "user@example.com", "sub_domain": ["quantization"]},
        )

        assert response.status_code == 200
        assert "邮件配置不完整" in response.text
        assert "smtp_host" in response.text


def test_subscribe_rejected_when_smtp_user_missing():
    """Test that subscription is rejected when smtp_user is missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        config = AppConfig(
            email=EmailNotifierConfig(
                enabled=True,
                smtp_host="smtp.example.com",
                smtp_user="",  # missing
                smtp_password="secret",
            ),
            storage=StorageConfig(db_path=str(db_path)),
        )
        app = create_app(config)
        client = TestClient(app)

        response = client.post(
            "/api/subscribe",
            data={"email": "user@example.com", "sub_domain": ["quantization"]},
        )

        assert response.status_code == 200
        assert "邮件配置不完整" in response.text
        assert "smtp_user" in response.text


def test_subscribe_rejected_when_smtp_password_missing():
    """Test that subscription is rejected when smtp_password is missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        config = AppConfig(
            email=EmailNotifierConfig(
                enabled=True,
                smtp_host="smtp.example.com",
                smtp_user="system@example.com",
                smtp_password="",  # missing
            ),
            storage=StorageConfig(db_path=str(db_path)),
        )
        app = create_app(config)
        client = TestClient(app)

        response = client.post(
            "/api/subscribe",
            data={"email": "user@example.com", "sub_domain": ["quantization"]},
        )

        assert response.status_code == 200
        assert "邮件配置不完整" in response.text
        assert "smtp_password" in response.text


def test_subscribe_accepted_when_email_configured(app_with_db):
    """Test that subscription is accepted when global email config is properly configured."""
    client, config = app_with_db

    response = client.post(
        "/api/subscribe",
        data={"email": "newuser@example.com", "sub_domain": ["quantization"]},
    )

    assert response.status_code == 200
    assert "success" in response.text.lower() or "成功" in response.text

    # Verify user was added with SMTP credentials
    user = next((u for u in config.users if u.user_id == "newuser@example.com"), None)
    assert user is not None
    assert user.notify.email.enabled is True
    assert user.notify.email.smtp_host == "smtp.example.com"
    assert user.notify.email.smtp_user == "system@example.com"
    assert user.notify.email.smtp_password == "secret"
    assert user.notify.email.sender == "noreply@example.com"
