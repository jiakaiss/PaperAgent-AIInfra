"""CLI entry point for Paper Agent."""

from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

import click

from paper_agent import __version__


def setup_logging(level: str = "INFO", log_file: str | None = None) -> None:
    """Configure logging."""
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


@click.group()
@click.version_option(__version__)
def cli():
    """Paper Agent - AI Infra 论文智能推送系统"""
    pass


def _load_subscriptions_into_config(config: "AppConfig") -> None:
    """Load active subscriptions from database and add to config.users.

    Avoids duplicates by checking existing user_ids.
    """
    from paper_agent.config import UserConfig
    from paper_agent.storage.database import PaperDatabase

    db = PaperDatabase(config.storage.db_path)
    subscriptions = db.load_active_subscriptions()

    existing_user_ids = {u.user_id for u in config.users}

    for sub in subscriptions:
        email = sub["email"]
        if email not in existing_user_ids:
            user_config = UserConfig(
                user_id=email,
                display_name=email,
                subscriptions={"sub_domains": sub["sub_domains"]},
                notify={"email": {"enabled": True, "recipients": [email]}},
            )
            config.users.append(user_config)
            existing_user_ids.add(email)
            logging.getLogger(__name__).info(f"Loaded subscription user '{email}' from database")

    if subscriptions:
        logging.getLogger(__name__).info(f"Loaded {len(subscriptions)} subscription(s) from database")


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="Config file path")
@click.option("--dry-run", is_flag=True, help="Fetch and score but skip notification")
@click.option("--days-back", "-d", type=int, help="Override days_back config")
@click.option("--user", "-u", multiple=True, help="Run for specific user(s) only")
def run(config: str, dry_run: bool, days_back: int | None, user: tuple[str, ...]):
    """Run the paper pipeline once."""
    from paper_agent.config import load_config
    from paper_agent.pipeline import Pipeline

    try:
        cfg = load_config(config)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    setup_logging(cfg.logging.level, cfg.logging.file)

    # Load subscriptions from database
    _load_subscriptions_into_config(cfg)

    if not cfg.users:
        click.echo("Error: No users configured. Edit config.yaml to add users.", err=True)
        sys.exit(1)

    pipeline = Pipeline(cfg)
    user_ids = list(user) if user else None
    results = pipeline.run(dry_run=dry_run, days_back=days_back, user_ids=user_ids)

    total = sum(len(v) for v in results.values())
    click.echo(f"\n✅ Pipeline complete. {total} papers across {len(results)} user(s).")


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="Config file path")
@click.option("--user", "-u", multiple=True, help="Run for specific user(s) only")
def daemon(config: str, user: tuple[str, ...]):
    """Start the scheduler daemon for periodic runs."""
    from paper_agent.config import load_config

    try:
        cfg = load_config(config)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    setup_logging(cfg.logging.level, cfg.logging.file)

    # Load subscriptions from database
    _load_subscriptions_into_config(cfg)

    if not cfg.schedule.enabled:
        click.echo("Error: Scheduler is disabled in config.", err=True)
        sys.exit(1)

    if not cfg.users:
        click.echo("Error: No users configured.", err=True)
        sys.exit(1)

    from paper_agent.scheduler import start_daemon

    user_ids = list(user) if user else None
    start_daemon(cfg, user_ids=user_ids)


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="Config file path")
@click.option(
    "--notifier",
    "-n",
    type=click.Choice(["email", "wecom", "feishu", "dingtalk"]),
    required=True,
    help="Which notifier to test",
)
@click.option(
    "--user",
    "-u",
    required=True,
    help="User ID to test (must exist in config)",
)
def test(config: str, notifier: str, user: str):
    """Send a test notification to verify config for a specific user."""
    from paper_agent.config import load_config
    from paper_agent.notifier import get_notifier_by_name

    try:
        cfg = load_config(config)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    setup_logging(cfg.logging.level, cfg.logging.file)

    # Find the user
    user_cfg = None
    for u in cfg.users:
        if u.user_id == user:
            user_cfg = u
            break

    if not user_cfg:
        available = ", ".join(u.user_id for u in cfg.users)
        click.echo(f"Error: User '{user}' not found. Available: {available}", err=True)
        sys.exit(1)

    n = get_notifier_by_name(notifier, user_cfg.notify)
    if not n:
        click.echo(f"Error: Unknown notifier: {notifier}", err=True)
        sys.exit(1)

    click.echo(f"Testing {notifier} for user '{user}'...")
    if hasattr(n, "send_test"):
        ok = n.send_test()
        status = "✅ Success" if ok else "❌ Failed"
        click.echo(status)
    else:
        click.echo("⚠️ No test method available")


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="Config file path")
@click.option("--user", "-u", default=None, help="Show stats for specific user")
def stats(config: str, user: str | None):
    """Show database statistics."""
    from paper_agent.config import load_config
    from paper_agent.storage.database import PaperDatabase

    try:
        cfg = load_config(config)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    db = PaperDatabase(cfg.storage.db_path)
    info = db.get_stats(user_id=user)

    click.echo("\n📊 Paper Agent Statistics")
    click.echo("-" * 30)
    click.echo(f"  Database:       {info['db_path']}")
    click.echo(f"  Cached papers:  {info['total_cached']}")
    click.echo(f"  Total sent:     {info['total_sent']}")
    click.echo(f"  Sent today:     {info['sent_today']}")
    click.echo(f"  Last sent:      {info['last_sent']}")
    click.echo(f"  Users:          {info['user_count']}")
    if user:
        click.echo(f"  Filtered for:   {user}")

    # Show configured users
    if cfg.users:
        click.echo("\n👥 Configured Users:")
        for u in cfg.users:
            display = u.display_name or u.user_id
            subs = ", ".join(u.subscriptions.sub_domains)
            notifiers = []
            if u.notify.email.enabled:
                notifiers.append("email")
            if u.notify.wecom.enabled:
                notifiers.append("wecom")
            if u.notify.feishu.enabled:
                notifiers.append("feishu")
            if u.notify.dingtalk.enabled:
                notifiers.append("dingtalk")
            notifier_str = ", ".join(notifiers) if notifiers else "none"
            click.echo(f"  • {display} ({u.user_id}): [{subs}] → {notifier_str}")
    click.echo()


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="Config file path")
@click.option("--host", "-h", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
@click.option("--port", "-p", default=8000, type=int, help="Bind port (default: 8000)")
def web(config: str, host: str, port: int):
    """Launch the web UI server."""
    import uvicorn

    from paper_agent.config import load_config

    try:
        cfg = load_config(config)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    setup_logging(cfg.logging.level, cfg.logging.file)

    from paper_agent.web.app import create_app

    app = create_app(cfg)
    click.echo(f"🌐 Paper Agent web UI starting on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


@cli.command()
@click.option("--output", "-o", default="config.yaml", help="Output path")
def init(output: str):
    """Create a template config file."""
    output_path = Path(output)
    if output_path.exists():
        if not click.confirm(f"{output} already exists. Overwrite?"):
            return

    template = Path(__file__).parent.parent.parent / "config.example.yaml"
    if not template.exists():
        template = Path(__file__).parent.parent / "config.example.yaml"

    if not template.exists():
        # Generate inline with defaults
        import yaml

        from paper_agent.config import AppConfig

        cfg = AppConfig()
        content = yaml.dump(cfg.model_dump(), default_flow_style=False, allow_unicode=True)
        output_path.write_text(content, encoding="utf-8")
    else:
        shutil.copy(template, output_path)

    click.echo(f"✅ Config template created: {output_path}")
    click.echo("Edit the file to configure users, subscriptions, and notification channels.")


if __name__ == "__main__":
    cli()
