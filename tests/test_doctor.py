"""Tests for the doctor CLI command."""

from click.testing import CliRunner

from paper_agent.cli import cli


def test_doctor_success(tmp_path):
    config_path = tmp_path / "config.yaml"
    db_path = tmp_path / "paper_agent.db"
    config_path.write_text(
        f"""
fetch:
  max_results: 1
scoring:
  api_key: test-key
email:
  enabled: true
  smtp_host: smtp.example.com
  smtp_user: user@example.com
  smtp_password: secret
  sender: user@example.com
storage:
  db_path: {db_path.as_posix()}
users: []
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(cli, ["doctor", "-c", str(config_path)])

    assert result.exit_code == 0
    assert "Doctor checks passed" in result.output
    assert "Config loads" in result.output
    assert "SQLite database initializes" in result.output


def test_doctor_missing_config_exits_nonzero(tmp_path):
    missing = tmp_path / "missing.yaml"

    result = CliRunner().invoke(cli, ["doctor", "-c", str(missing)])

    assert result.exit_code != 0
    assert "Config file not found" in result.output


def test_doctor_email_missing_credentials_exits_nonzero(tmp_path):
    config_path = tmp_path / "config.yaml"
    db_path = tmp_path / "paper_agent.db"
    config_path.write_text(
        f"""
email:
  enabled: true
  smtp_host: smtp.example.com
  smtp_user: user@example.com
  smtp_password: ''
storage:
  db_path: {db_path.as_posix()}
users: []
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(cli, ["doctor", "-c", str(config_path)])

    assert result.exit_code != 0
    assert "Email config incomplete" in result.output
    assert "smtp_password" in result.output
