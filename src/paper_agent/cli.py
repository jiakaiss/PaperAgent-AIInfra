"""CLI entry point for Paper Agent."""

from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

import click

from paper_agent import __version__
from paper_agent.subscriptions import load_subscriptions_into_config


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
    load_subscriptions_into_config(cfg)

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
@click.option(
    "--log-file",
    default=None,
    help="Override config.logging.file (e.g. logs/daemon.log)",
)
def daemon(config: str, user: tuple[str, ...], log_file: str | None):
    """Start the scheduler daemon for periodic runs."""
    from paper_agent.config import load_config

    try:
        cfg = load_config(config)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    setup_logging(cfg.logging.level, log_file or cfg.logging.file)

    # Load subscriptions from database
    load_subscriptions_into_config(cfg)

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
    type=click.Choice(["email"]),
    required=True,
    help="Which notifier to test (only email supported)",
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

    # Load subscriptions from database (users come from subscription system)
    load_subscriptions_into_config(cfg)

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

    # Show configured users (from subscription system)
    load_subscriptions_into_config(cfg)
    if cfg.users:
        click.echo("\n👥 Subscribed Users:")
        for u in cfg.users:
            display = u.display_name or u.user_id
            subs = ", ".join(u.subscriptions.sub_domains)
            notifier_str = "email" if u.notify.email.enabled else "none"
            click.echo(f"  • {display} ({u.user_id}): [{subs}] → {notifier_str}")
    click.echo()


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="Config file path")
@click.option("--host", "-h", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
@click.option("--port", "-p", default=8000, type=int, help="Bind port (default: 8000)")
@click.option(
    "--log-file",
    default=None,
    help="Override config.logging.file (e.g. logs/web.log)",
)
def web(config: str, host: str, port: int, log_file: str | None):
    """Launch the web UI server."""
    import uvicorn

    from paper_agent.config import load_config

    try:
        cfg = load_config(config)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    setup_logging(cfg.logging.level, log_file or cfg.logging.file)

    from paper_agent.web.app import create_app

    app = create_app(cfg)
    click.echo(f"🌐 Paper Agent web UI starting on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="Config file path")
def doctor(config: str):
    """Check deployment readiness."""
    from paper_agent.config import load_config
    from paper_agent.storage.database import PaperDatabase
    from paper_agent.subscriptions import missing_email_config_fields

    ok = True

    def pass_(message: str) -> None:
        click.echo(f"✅ {message}")

    def fail(message: str) -> None:
        nonlocal ok
        ok = False
        click.echo(f"❌ {message}", err=True)

    def warn(message: str) -> None:
        click.echo(f"⚠️  {message}")

    config_path = Path(config)
    if not config_path.exists():
        fail(f"Config file not found: {config_path}")
        sys.exit(1)

    try:
        cfg = load_config(config_path)
        pass_(f"Config loads: {config_path}")
    except Exception as e:
        fail(f"Config validation failed: {e}")
        sys.exit(1)

    try:
        db_path = Path(cfg.storage.db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        PaperDatabase(db_path)
        pass_(f"SQLite database initializes: {db_path}")
    except Exception as e:
        fail(f"Storage check failed: {e}")

    web_dir = Path(__file__).parent / "web"
    required_assets = [
        web_dir / "templates" / "base.html",
        web_dir / "templates" / "index.html",
        web_dir / "templates" / "subscribe.html",
        web_dir / "static" / "style.css",
        web_dir / "static" / "preferences.js",
        web_dir / "static" / "vendor" / "htmx.min.js",
    ]
    missing_assets = [p for p in required_assets if not p.exists()]
    if missing_assets:
        fail("Missing web assets: " + ", ".join(str(p) for p in missing_assets))
    else:
        pass_("Web templates and static assets exist")

    if cfg.email.enabled:
        missing = missing_email_config_fields(cfg.email)
        if missing:
            fail("Email config incomplete; missing: " + ", ".join(missing))
        else:
            pass_("Global email config is ready for subscriptions")
    else:
        warn("Global email is disabled; public subscriptions cannot receive emails")

    if cfg.schedule.enabled:
        pass_(
            f"Schedule enabled at "
            f"{cfg.schedule.cron_hour:02d}:{cfg.schedule.cron_minute:02d} "
            f"{cfg.schedule.timezone}"
        )
    else:
        warn("Schedule disabled; daemon will not send periodic digests")

    if ok:
        click.echo("\n✅ Doctor checks passed")
    else:
        click.echo("\n❌ Doctor checks failed", err=True)
        sys.exit(1)


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


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="Config file path")
@click.option(
    "--missing-fields",
    is_flag=True,
    help="Re-score papers that lack structured-insight fields",
)
def rescore(config: str, missing_fields: bool):
    """Re-score cached papers whose structured-insight fields are missing.

    Only useful after upgrading from a version before the
    ``key_contributions`` / ``impact_tier`` / ``problem_statement_zh`` /
    ``methods_zh`` columns were added. Each batch is written in its own
    transaction so interruption is safe.
    """
    if not missing_fields:
        click.echo("Error: Specify --missing-fields to re-score legacy papers.", err=True)
        sys.exit(1)

    from paper_agent.config import load_config
    from paper_agent.scorer.claude_scorer import ClaudeScorer
    from paper_agent.storage.database import PaperDatabase

    try:
        cfg = load_config(config)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    setup_logging(cfg.logging.level, cfg.logging.file)

    db = PaperDatabase(cfg.storage.db_path)
    total = db.count_papers_missing_insights()
    if total == 0:
        click.echo("✅ No papers with missing fields found. Nothing to do.")
        return

    scorer = ClaudeScorer(config=cfg.scoring)
    processed = 0
    batch_size = cfg.scoring.batch_size

    click.echo(f"Found {total} papers with missing structured-insight fields.")
    click.echo(f"Processing in batches of {batch_size}...")

    while True:
        # Always query offset=0 — each successful batch writes the new fields
        # back, so the "missing" set shrinks naturally. Using a non-zero offset
        # would skip rows because the rows we just fixed are no longer in the
        # result set.
        batch = db.get_papers_missing_insights(limit=batch_size, offset=0)
        if not batch:
            break

        papers_to_score = [sp.paper for sp in batch]
        click.echo(f"  Batch {processed // batch_size + 1}: {len(papers_to_score)} papers...")

        # Score + write in a single try block. ANY exception here (including
        # the API call, the DB write, or a downstream echo) means we don't
        # know if persistence succeeded — bail out so the operator can rerun
        # and resume from a clean checkpoint instead of silently skipping.
        try:
            rescored = scorer.score(papers_to_score)
            db.cache_papers(rescored)
        except Exception as e:
            # ASCII-only message: Windows GBK console can't print emoji.
            click.echo(f"  [FAIL] Batch failed: {e}", err=True)
            click.echo("  Stopping; rerun the command to resume.", err=True)
            sys.exit(1)

        # If the scorer returned fewer rows than we sent (e.g. the model
        # skipped some), those rows stay NULL and we'd loop forever. Bail
        # out so the operator can investigate rather than spinning.
        if not rescored:
            click.echo(
                f"  [FAIL] Batch returned 0 scored papers ({len(papers_to_score)} sent). "
                "Stopping; check scorer logs.",
                err=True,
            )
            sys.exit(1)

        processed += len(rescored)
        click.echo(f"  [OK] Saved {len(rescored)} papers (total {processed}/{total})")

    click.echo(f"\nDone. Processed {processed}/{total} papers.")


if __name__ == "__main__":
    cli()
