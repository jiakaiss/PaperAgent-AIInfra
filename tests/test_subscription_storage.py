"""Tests for subscription storage methods."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from paper_agent.storage.database import PaperDatabase


@pytest.fixture
def db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield PaperDatabase(db_path)


def test_add_subscription(db):
    """Test adding a new subscription."""
    email = "test@example.com"
    sub_domains = ["quantization", "distillation"]

    db.add_subscription(email, sub_domains)

    # Verify subscription was added
    assert db.is_email_subscribed(email)
    sub = db.get_subscription(email)
    assert sub is not None
    assert sub["email"] == email
    assert sub["sub_domains"] == sub_domains
    assert sub["status"] == "active"
    assert "created_at" in sub


def test_add_subscription_duplicate_email(db):
    """Test that duplicate email raises IntegrityError."""
    email = "test@example.com"
    sub_domains = ["quantization"]

    db.add_subscription(email, sub_domains)

    # Attempt to add duplicate should raise IntegrityError
    with pytest.raises(sqlite3.IntegrityError):
        db.add_subscription(email, ["distillation"])


def test_is_email_subscribed_not_found(db):
    """Test is_email_subscribed returns False for non-existent email."""
    assert not db.is_email_subscribed("nonexistent@example.com")


def test_get_subscription_not_found(db):
    """Test get_subscription returns None for non-existent email."""
    assert db.get_subscription("nonexistent@example.com") is None


def test_load_active_subscriptions_empty(db):
    """Test loading subscriptions when none exist."""
    subs = db.load_active_subscriptions()
    assert subs == []


def test_load_active_subscriptions_multiple(db):
    """Test loading multiple active subscriptions."""
    db.add_subscription("user1@example.com", ["quantization"])
    db.add_subscription("user2@example.com", ["distillation", "pruning"])

    subs = db.load_active_subscriptions()

    assert len(subs) == 2
    emails = {s["email"] for s in subs}
    assert "user1@example.com" in emails
    assert "user2@example.com" in emails

    # Verify sub_domains are correctly loaded
    for sub in subs:
        assert isinstance(sub["sub_domains"], list)
        assert "created_at" in sub
        assert sub["status"] == "active"


def test_subscription_sub_domains_json_serialization(db):
    """Test that sub_domains are correctly serialized/deserialized as JSON."""
    email = "test@example.com"
    sub_domains = ["quantization", "distillation", "pruning", "sparsity"]

    db.add_subscription(email, sub_domains)

    sub = db.get_subscription(email)
    assert sub["sub_domains"] == sub_domains
    assert isinstance(sub["sub_domains"], list)


def test_subscription_created_at_timestamp(db):
    """Test that created_at is set to a valid ISO timestamp."""
    email = "test@example.com"
    db.add_subscription(email, ["quantization"])

    sub = db.get_subscription(email)
    assert "created_at" in sub
    # Should be a valid ISO format string
    from datetime import datetime

    datetime.fromisoformat(sub["created_at"])  # Should not raise


# ─── SMTP credentials inheritance tests ───


def test_load_subscriptions_inherits_smtp_credentials(db):
    """Test that _load_subscriptions_into_config copies SMTP credentials from global config."""
    from paper_agent.config import AppConfig, EmailNotifierConfig
    from paper_agent.subscriptions import load_subscriptions_into_config

    # Add a subscription to database
    db.add_subscription("subscriber@example.com", ["quantization", "distillation"])

    # Create config with global email settings
    config = AppConfig(
        storage={"db_path": str(db.db_path)},
        email=EmailNotifierConfig(
            enabled=True,
            smtp_host="smtp.example.com",
            smtp_port=465,
            smtp_user="system@example.com",
            smtp_password="secret123",
            sender="noreply@example.com",
            use_tls=False,
        ),
    )

    # Load subscriptions into config
    load_subscriptions_into_config(config)

    # Verify the subscription user was added with SMTP credentials
    assert len(config.users) == 1
    user = config.users[0]
    assert user.user_id == "subscriber@example.com"
    assert user.display_name == "subscriber@example.com"
    assert user.subscriptions.sub_domains == ["quantization", "distillation"]

    # Verify SMTP credentials were inherited
    assert user.notify.email.enabled is True
    assert user.notify.email.recipients == ["subscriber@example.com"]
    assert user.notify.email.smtp_host == "smtp.example.com"
    assert user.notify.email.smtp_port == 465
    assert user.notify.email.smtp_user == "system@example.com"
    assert user.notify.email.smtp_password == "secret123"
    assert user.notify.email.sender == "noreply@example.com"
    assert user.notify.email.use_tls is False


def test_load_subscriptions_email_not_configured(db, caplog):
    """Subscriptions load with email disabled when global email is disabled."""
    import logging

    from paper_agent.config import AppConfig, EmailNotifierConfig
    from paper_agent.subscriptions import load_subscriptions_into_config

    # Add a subscription to database
    db.add_subscription("subscriber@example.com", ["quantization"])

    # Create config with email disabled
    config = AppConfig(
        storage={"db_path": str(db.db_path)},
        email=EmailNotifierConfig(enabled=False),
    )

    # Load subscriptions with log capture
    with caplog.at_level(logging.WARNING, logger="paper_agent.subscriptions"):
        load_subscriptions_into_config(config)

    # Verify the subscription user was added with email disabled
    assert len(config.users) == 1
    user = config.users[0]
    assert user.user_id == "subscriber@example.com"
    assert user.notify.email.enabled is False
    assert user.notify.email.recipients == ["subscriber@example.com"]

    # Verify warning was logged
    assert any("will not receive emails" in rec.message for rec in caplog.records)


def test_load_subscriptions_missing_smtp_credentials_warning(db, caplog):
    """Test that a warning is logged when global email config is enabled but missing credentials."""
    import logging

    from paper_agent.config import AppConfig, EmailNotifierConfig
    from paper_agent.subscriptions import load_subscriptions_into_config

    # Add a subscription to database
    db.add_subscription("subscriber@example.com", ["quantization"])

    # Create config with email enabled but missing smtp_user
    config = AppConfig(
        storage={"db_path": str(db.db_path)},
        email=EmailNotifierConfig(
            enabled=True,
            smtp_host="smtp.example.com",
            smtp_user="",  # missing
            smtp_password="secret",
        ),
    )

    # Load subscriptions with log capture
    with caplog.at_level(logging.WARNING, logger="paper_agent.subscriptions"):
        load_subscriptions_into_config(config)

    # Verify warning was logged about missing fields
    assert any("missing fields" in rec.message for rec in caplog.records)
    assert any("smtp_user" in rec.message for rec in caplog.records)


def test_load_subscriptions_multiple_with_smtp(db):
    """Test loading multiple subscriptions with SMTP credentials."""
    from paper_agent.config import AppConfig, EmailNotifierConfig
    from paper_agent.subscriptions import load_subscriptions_into_config

    # Add multiple subscriptions
    db.add_subscription("user1@example.com", ["quantization"])
    db.add_subscription("user2@example.com", ["distillation", "pruning"])

    # Create config with global email settings
    config = AppConfig(
        storage={"db_path": str(db.db_path)},
        email=EmailNotifierConfig(
            enabled=True,
            smtp_host="smtp.example.com",
            smtp_user="system@example.com",
            smtp_password="secret",
        ),
    )

    # Load subscriptions
    load_subscriptions_into_config(config)

    # Verify both users were added with SMTP credentials
    assert len(config.users) == 2
    for user in config.users:
        assert user.notify.email.enabled is True
        assert user.notify.email.smtp_host == "smtp.example.com"
        assert user.notify.email.smtp_user == "system@example.com"
        assert user.notify.email.smtp_password == "secret"


def test_unsubscribe_email_marks_inactive(db):
    """Unsubscribe keeps row but marks it inactive."""
    db.add_subscription("user@example.com", ["quantization"])

    assert db.unsubscribe_email("user@example.com") is True
    sub = db.get_subscription("user@example.com")
    assert sub["status"] == "inactive"
    assert sub["unsubscribed_at"] is not None
    assert not db.is_email_subscribed("user@example.com")


def test_load_active_subscriptions_skips_inactive(db):
    """Inactive subscriptions are not loaded for runtime delivery."""
    db.add_subscription("active@example.com", ["quantization"])
    db.add_subscription("inactive@example.com", ["moe"])
    db.unsubscribe_email("inactive@example.com")

    subs = db.load_active_subscriptions()
    emails = {s["email"] for s in subs}
    assert emails == {"active@example.com"}


def test_update_subscription_changes_sub_domains(db):
    """Active subscription preferences can be updated."""
    db.add_subscription("user@example.com", ["quantization"])

    assert db.update_subscription("user@example.com", ["moe", "serving"]) is True

    sub = db.get_subscription("user@example.com")
    assert sub["sub_domains"] == ["moe", "serving"]


def test_update_subscription_inactive_returns_false(db):
    """Inactive subscriptions are not updated as active preferences."""
    db.add_subscription("user@example.com", ["quantization"])
    db.unsubscribe_email("user@example.com")

    assert db.update_subscription("user@example.com", ["moe"]) is False
    assert db.get_subscription("user@example.com")["sub_domains"] == ["quantization"]
