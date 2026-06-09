"""Admin dashboard — HTTP Basic Auth gated read-only operator surface.

Registered conditionally by :func:`paper_agent.web.app.create_app`. When
``AppConfig.admin.is_active`` is false the router is NOT registered and
every ``/admin*`` URL falls through to FastAPI's default 404 — by design,
so an unconfigured deployment does not advertise that the admin surface
exists.

All routes inherit the :func:`verify_admin` dependency via the router-level
``dependencies`` list, so adding a new admin route requires zero auth
boilerplate.

The hard rule: **no admin response may contain sensitive credentials.**
Enforced by ``tests/test_admin.py::test_admin_responses_omit_sensitive_fields``.
Never pass raw config objects into a template; always project the specific
fields the template needs.
"""

from __future__ import annotations

import csv
import io
import logging
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from paper_agent.config import AppConfig
from paper_agent.daemon_heartbeat import assess_health
from paper_agent.models import IMPACT_TIERS, SUB_DOMAINS
from paper_agent.storage.database import PaperDatabase
from paper_agent.web.deps import get_db

logger = logging.getLogger(__name__)

REALM = "paper-agent-admin"
_BASIC = HTTPBasic(realm=REALM, auto_error=False)
_CHALLENGE = {"WWW-Authenticate": f'Basic realm="{REALM}"'}

# Sortable columns for /admin/_subscribers. Anything not in this whitelist
# falls back to "created_at" so an attacker can't inject column names.
_SUBSCRIBER_SORT_COLUMNS = {
    "created_at",
    "email",
    "status",
    "total_sent",
    "last_sent_at",
}


def verify_admin(
    request: Request,
    credentials: HTTPBasicCredentials | None = Depends(_BASIC),
) -> str:
    """Validate HTTP Basic credentials against ``config.admin``.

    Returns the authenticated username on success.

    Always runs ``compare_digest`` on BOTH username and password — even
    when the username is wrong — so a wrong username and a wrong password
    take indistinguishable time. Prevents a timing channel that would
    otherwise reveal which fields exist.
    """
    config: AppConfig = request.app.state.config
    expected_user = config.admin.username.encode("utf-8")
    expected_pass = config.admin.password.encode("utf-8")

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers=_CHALLENGE,
        )

    given_user = credentials.username.encode("utf-8")
    given_pass = credentials.password.encode("utf-8")
    user_ok = secrets.compare_digest(given_user, expected_user)
    pass_ok = secrets.compare_digest(given_pass, expected_pass)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers=_CHALLENGE,
        )
    return credentials.username


router = APIRouter(prefix="/admin", dependencies=[Depends(verify_admin)])


# ─── Helpers ──────────────────────────────────────────────────────────


def _format_ts(ts: str | None) -> str:
    """Render an ISO timestamp as ``YYYY-MM-DD HH:MM`` for the dashboard."""
    if not ts:
        return "—"
    try:
        return datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return str(ts)


def _format_bytes(n: int) -> str:
    """Human-readable byte count (binary units)."""
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    size = float(n)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024
    return f"{n} B"


def _format_duration(seconds: float | None) -> str:
    """Render a duration as a compact, Chinese-friendly string.

    Examples: ``45 秒``, ``3 分钟``, ``2 小时 15 分钟``, ``5 天 3 小时``.
    """
    if seconds is None or seconds < 0:
        return "—"
    s = int(seconds)
    if s < 60:
        return f"{s} 秒"
    minutes, sec = divmod(s, 60)
    if minutes < 60:
        return f"{minutes} 分钟"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} 小时 {minutes} 分钟" if minutes else f"{hours} 小时"
    days, hours = divmod(hours, 24)
    return f"{days} 天 {hours} 小时" if hours else f"{days} 天"


# ─── Routes ───────────────────────────────────────────────────────────


@router.get("", response_class=HTMLResponse, include_in_schema=False)
@router.get("/", response_class=HTMLResponse)
def admin_dashboard(request: Request) -> HTMLResponse:
    """Render the dashboard shell — four panels populated by HTMX."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="admin/dashboard.html",
        context={},
    )


@router.get("/_subscribers", response_class=HTMLResponse)
def admin_subscribers(
    request: Request,
    db: PaperDatabase = Depends(get_db),
    q: str | None = Query(None),
    sort: str = Query("created_at"),
    order: str = Query("desc"),
) -> HTMLResponse:
    """Subscriber table partial with email search + sortable columns."""
    templates = request.app.state.templates

    # Whitelist the sort column to prevent injection / silent fallbacks.
    sort_col = sort if sort in _SUBSCRIBER_SORT_COLUMNS else "created_at"
    sort_order = "asc" if order == "asc" else "desc"

    subs_by_email = {s["email"]: s for s in db.list_subscriptions()}
    stats_by_user = {s["user_id"]: s for s in db.get_user_stats()}

    # Merge: one row per subscription, augmented with delivery stats.
    # Sent-only users (e.g. test_user) are intentionally excluded here —
    # this panel is about subscribers; the user-stats panel shows everyone.
    rows: list[dict] = []
    for email, sub in subs_by_email.items():
        stat = stats_by_user.get(email, {})
        rows.append(
            {
                "id": sub["id"],
                "email": email,
                "status": sub["status"],
                "created_at": sub["created_at"],
                "unsubscribed_at": sub["unsubscribed_at"],
                "sub_domains": sub["sub_domains"],
                "sub_domain_count": len(sub["sub_domains"]),
                "total_sent": stat.get("total_sent", 0),
                "last_sent_at": stat.get("last_sent_at"),
            }
        )

    if q:
        needle = q.strip().lower()
        rows = [r for r in rows if needle in r["email"].lower()]

    # Sort. ``None`` values (e.g. last_sent_at for never-delivered) sort
    # last regardless of direction by mapping them to a tuple key.
    def _key(row: dict):
        v = row.get(sort_col)
        return (v is None, v if v is not None else "")

    rows.sort(key=_key, reverse=(sort_order == "desc"))

    return templates.TemplateResponse(
        request=request,
        name="admin/_subscribers.html",
        context={
            "rows": rows,
            "q": q or "",
            "sort": sort_col,
            "order": sort_order,
            "format_ts": _format_ts,
        },
    )


@router.get("/_user_stats", response_class=HTMLResponse)
def admin_user_stats(
    request: Request,
    db: PaperDatabase = Depends(get_db),
) -> HTMLResponse:
    """Per-user delivery stats + 7-day total trend."""
    templates = request.app.state.templates

    user_stats = db.get_user_stats()
    # Sort by total_sent desc so the heaviest recipients lead.
    user_stats.sort(key=lambda r: (-r["total_sent"], r["user_id"]))

    daily = db.get_daily_sent_counts(days=7)
    daily_total = sum(r["count"] for r in daily)

    return templates.TemplateResponse(
        request=request,
        name="admin/_user_stats.html",
        context={
            "users": user_stats,
            "daily": daily,
            "daily_total": daily_total,
            "format_ts": _format_ts,
        },
    )


@router.get("/_papers", response_class=HTMLResponse)
def admin_papers(
    request: Request,
    db: PaperDatabase = Depends(get_db),
) -> HTMLResponse:
    """Paper-library overview: stat cards, tier distribution, sub-domain mix, daily."""
    templates = request.app.state.templates

    total = db.count_papers()
    today_iso = date.today().isoformat()
    week_ago_iso = (date.today() - timedelta(days=6)).isoformat()

    daily_papers = db.get_daily_paper_counts(days=7)
    # The first entry is today by construction (most-recent-first).
    today_count = daily_papers[0]["count"] if daily_papers else 0
    week_count = sum(r["count"] for r in daily_papers)

    tier_counts = db.get_tier_distribution()
    tier_total = sum(tier_counts.values()) or 1  # avoid division by zero
    tier_rows = [
        {
            "tier": tier,
            "count": tier_counts.get(tier, 0),
            "pct": round(tier_counts.get(tier, 0) * 100 / tier_total, 1),
        }
        for tier in IMPACT_TIERS
    ]

    sub_counts = db.get_sub_domain_counts()
    sub_max = max(sub_counts.values()) if sub_counts else 1
    sub_max = sub_max or 1  # avoid /0 when all zero
    # Order by descending count, stable on key name.
    sub_rows = sorted(
        (
            {
                "tag": tag,
                "count": cnt,
                "pct": round(cnt * 100 / sub_max, 1),
            }
            for tag, cnt in sub_counts.items()
        ),
        key=lambda r: (-r["count"], r["tag"]),
    )
    # Ensure every standard sub-domain is present, even with zero count.
    seen = {r["tag"] for r in sub_rows}
    for tag in SUB_DOMAINS:
        if tag not in seen:
            sub_rows.append({"tag": tag, "count": 0, "pct": 0.0})

    return templates.TemplateResponse(
        request=request,
        name="admin/_papers.html",
        context={
            "total": total,
            "today_count": today_count,
            "week_count": week_count,
            "today_iso": today_iso,
            "week_ago_iso": week_ago_iso,
            "tier_rows": tier_rows,
            "sub_rows": sub_rows,
            "daily_papers": daily_papers,
        },
    )


@router.get("/_system", response_class=HTMLResponse)
def admin_system(
    request: Request,
    db: PaperDatabase = Depends(get_db),
) -> HTMLResponse:
    """Runtime / config snapshot. Sensitive credentials are NEVER rendered."""
    templates = request.app.state.templates
    config: AppConfig = request.app.state.config

    db_path = Path(config.storage.db_path)
    try:
        db_size = db_path.stat().st_size
        db_size_human = _format_bytes(db_size)
    except OSError:
        db_size_human = "—"

    active_subs = db.count_active_subscriptions()
    runtime_users = len(config.users)
    # Subscription users are merged into config.users at startup. If active
    # subscriptions > runtime users, something failed to load. (Runtime can
    # legitimately exceed active subs by however many static CLI-configured
    # users exist in config.yaml, so we don't flag the > case.)
    is_mismatched = active_subs > runtime_users

    # Build a hand-picked, sensitive-free config summary. Never pass the raw
    # config object to a template — that would risk leaking secrets via
    # accidental ``{{ config }}`` rendering.
    cfg_summary = {
        "scoring_model": config.scoring.model,
        "ingest_interval_minutes": config.schedule.ingest_interval_minutes,
        "digest_time": f"{config.schedule.digest_hour:02d}:{config.schedule.digest_minute:02d}",
        "timezone": config.schedule.timezone,
        "smtp_host": config.email.smtp_host if config.email.enabled else "(disabled)",
        "smtp_port": config.email.smtp_port if config.email.enabled else "—",
        "email_enabled": config.email.enabled,
        "subscription_access_enabled": config.subscriptions.access.enabled,
    }

    # Daemon health: PID liveness + heartbeat freshness. The dashboard's
    # primary "is the background still running?" signal — better than
    # inferring from last_ingest_at, which only updates when new papers
    # actually land in the cache.
    daemon = assess_health(
        config.storage.db_path,
        config.schedule.ingest_interval_minutes,
    )
    daemon["uptime_human"] = (
        _format_duration(
            (datetime.now() - datetime.fromisoformat(daemon["started_at"])).total_seconds()
        )
        if daemon.get("started_at")
        else "—"
    )
    daemon["last_heartbeat_human"] = (
        _format_duration(daemon["age_seconds"]) + " 前"
        if daemon.get("age_seconds") is not None
        else "—"
    )

    return templates.TemplateResponse(
        request=request,
        name="admin/_system.html",
        context={
            "cfg": cfg_summary,
            "db_path": str(db_path),
            "db_size_human": db_size_human,
            "last_ingest_at": _format_ts(db.get_last_ingest_at()),
            "last_digest_at": _format_ts(db.get_last_digest_at()),
            "active_subs": active_subs,
            "runtime_users": runtime_users,
            "is_mismatched": is_mismatched,
            "daemon": daemon,
        },
    )


@router.get("/subscribers.csv")
def admin_subscribers_csv(db: PaperDatabase = Depends(get_db)) -> Response:
    """Download the full subscriber list as CSV (active + inactive)."""
    subs = db.list_subscriptions()
    stats_by_user = {s["user_id"]: s for s in db.get_user_stats()}

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "id",
            "email",
            "status",
            "created_at",
            "unsubscribed_at",
            "sub_domains",
            "total_sent",
            "last_sent_at",
        ]
    )
    for sub in subs:
        stat = stats_by_user.get(sub["email"], {})
        writer.writerow(
            [
                sub["id"],
                sub["email"],
                sub["status"],
                sub["created_at"] or "",
                sub["unsubscribed_at"] or "",
                ";".join(sub["sub_domains"]),
                stat.get("total_sent", 0),
                stat.get("last_sent_at") or "",
            ]
        )

    filename = f"subscribers-{date.today():%Y%m%d}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
