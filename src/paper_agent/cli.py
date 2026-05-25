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


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="Config file path")
@click.option("--dry-run", is_flag=True, help="Fetch and score but skip notification")
@click.option("--days-back", "-d", type=int, help="Override days_back config")
@click.option("--top", "-n", type=int, help="Override top_n config")
def run(config: str, dry_run: bool, days_back: int | None, top: int | None):
    """Run the paper pipeline once."""
    from paper_agent.config import load_config
    from paper_agent.pipeline import Pipeline

    try:
        cfg = load_config(config)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    setup_logging(cfg.logging.level, cfg.logging.file)
    pipeline = Pipeline(cfg)
    results = pipeline.run(dry_run=dry_run, days_back=days_back, top_n=top)

    click.echo(f"\n✅ Pipeline complete. {len(results)} papers processed.")


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="Config file path")
@click.option("--no-run", is_flag=True, help="Don't run pipeline on startup")
def daemon(config: str, no_run: bool):
    """Start the scheduler daemon for periodic runs."""
    from paper_agent.config import load_config

    try:
        cfg = load_config(config)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    setup_logging(cfg.logging.level, cfg.logging.file)

    if not cfg.schedule.enabled:
        click.echo("Error: Scheduler is disabled in config.", err=True)
        sys.exit(1)

    from paper_agent.scheduler import start_daemon

    start_daemon(cfg)


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="Config file path")
@click.option(
    "--notifier",
    "-n",
    type=click.Choice(["email", "wecom", "feishu", "dingtalk", "all"]),
    required=True,
    help="Which notifier to test",
)
def test(config: str, notifier: str):
    """Send a test notification to verify config."""
    from paper_agent.config import load_config
    from paper_agent.notifier import create_notifiers, get_notifier_by_name

    try:
        cfg = load_config(config)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    setup_logging(cfg.logging.level, cfg.logging.file)

    if notifier == "all":
        notifiers = create_notifiers(cfg.notify)
        if not notifiers:
            click.echo("No notifiers enabled in config.", err=True)
            sys.exit(1)
        for n in notifiers:
            click.echo(f"Testing {n.name}...")
            if hasattr(n, "send_test"):
                ok = n.send_test()
                status = "✅ Success" if ok else "❌ Failed"
                click.echo(f"  {status}")
            else:
                click.echo(f"  ⚠️ No test method available")
    else:
        n = get_notifier_by_name(notifier, cfg.notify)
        if not n:
            click.echo(f"Unknown notifier: {notifier}", err=True)
            sys.exit(1)

        click.echo(f"Testing {notifier}...")
        if hasattr(n, "send_test"):
            ok = n.send_test()
            status = "✅ Success" if ok else "❌ Failed"
            click.echo(status)
        else:
            click.echo("⚠️ No test method available")


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="Config file path")
def stats(config: str):
    """Show database statistics."""
    from paper_agent.config import load_config
    from paper_agent.storage.database import PaperDatabase

    try:
        cfg = load_config(config)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    db = PaperDatabase(cfg.storage.db_path)
    info = db.get_stats()

    click.echo("\n📊 Paper Agent Statistics")
    click.echo("-" * 30)
    click.echo(f"  Database:    {info['db_path']}")
    click.echo(f"  Total sent:  {info['total_papers']}")
    click.echo(f"  Sent today:  {info['sent_today']}")
    click.echo(f"  Last sent:   {info['last_sent']}")
    click.echo()


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
        # Fallback: look relative to package
        template = Path(__file__).parent.parent / "config.example.yaml"

    if not template.exists():
        # Generate inline
        from paper_agent.config import AppConfig

        import yaml

        cfg = AppConfig()
        content = yaml.dump(cfg.model_dump(), default_flow_style=False, allow_unicode=True)
        output_path.write_text(content, encoding="utf-8")
    else:
        shutil.copy(template, output_path)

    click.echo(f"✅ Config template created: {output_path}")
    click.echo("Edit the file and fill in your API keys / webhook URLs.")


if __name__ == "__main__":
    cli()
