"""Web route handlers."""

from __future__ import annotations

import logging
import math
import sqlite3
import threading
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from paper_agent.config import AppConfig, SubscriptionRequest
from paper_agent.models import IMPACT_TIERS, SUB_DOMAINS
from paper_agent.storage.database import PaperDatabase
from paper_agent.subscriptions import (
    build_unsubscribe_url,
    missing_email_config_fields,
    subscription_to_user_config,
)
from paper_agent.unsubscribe import verify_unsubscribe_token
from paper_agent.web.deps import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

PAGE_SIZE = 25
VALID_MODES = {"all", "custom"}

# Default tier set used when the client doesn't pass any ?tier= params.
# Excludes "incremental" so the front page reads as a curated digest; users
# who want everything pass ?tier=incremental (along with the others) or set
# minTier=incremental in their localStorage preferences.
DEFAULT_TIERS: set[str] = {"breakthrough", "solid"}

# Map relative time range codes to days
SINCE_MAP = {
    "1w": 7,
    "1m": 30,
    "3m": 90,
    "6m": 180,
    "1y": 365,
    "3y": 1095,
}


def _validate_sub_domains(tags: list[str]) -> list[str]:
    """Return only tags that are valid SUB_DOMAINS keys."""
    return [t for t in tags if t in SUB_DOMAINS]


def _resolve_tiers(raw: list[str] | None) -> set[str]:
    """Filter ?tier= values against IMPACT_TIERS; default when nothing valid.

    - No params and no valid params alike fall back to ``DEFAULT_TIERS``
      (breakthrough + solid). This matches the documented "default page
      hides incremental" behavior.
    - Unknown values are silently dropped (per the spec).
    """
    if not raw:
        return set(DEFAULT_TIERS)
    valid = {t for t in raw if t in IMPACT_TIERS}
    return valid if valid else set(DEFAULT_TIERS)


def _send_initial_digest(config: AppConfig, user_id: str) -> None:
    """Run one immediate pipeline pass for a newly subscribed user."""
    try:
        from paper_agent.pipeline import Pipeline

        logger.info(f"Running initial cached digest for new subscription user '{user_id}'")
        Pipeline(config).run_cached_for_user(user_id)
    except Exception as e:
        logger.error(f"Initial digest failed for subscription user '{user_id}': {e}", exc_info=True)


def _upsert_runtime_user(config: AppConfig, user_config) -> None:
    """Replace or append a runtime subscription user."""
    config.users = [u for u in config.users if u.user_id != user_config.user_id]
    config.users.append(user_config)


def _enqueue_initial_digest(request: Request, config: AppConfig, user_id: str) -> None:
    """Start the initial digest without blocking the subscription response."""
    if not config.subscriptions.send_initial_digest_on_signup:
        return
    if getattr(request.app.state, "run_initial_digest_inline", False):
        _send_initial_digest(config, user_id)
        return
    thread = threading.Thread(
        target=_send_initial_digest,
        args=(config, user_id),
        name=f"initial-digest-{user_id}",
        daemon=True,
    )
    thread.start()


def _parse_since(since: str | None) -> str | None:
    """Convert a relative time range code to an absolute date string.

    Returns the ISO date string (YYYY-MM-DD) for the cutoff date, or None
    if the value is missing or invalid.
    """
    if not since or since not in SINCE_MAP:
        return None
    days = SINCE_MAP[since]
    cutoff = date.today() - timedelta(days=days)
    return cutoff.isoformat()


def _compute_page_context(
    db: PaperDatabase,
    sub_domains: set[str] | None,
    search: str | None,
    published_after: str | None,
    min_quality: float | None,
    page: int,
    page_size: int = PAGE_SIZE,
    tiers: set[str] | None = None,
) -> dict:
    """Build the template context dict for the paper list + pagination."""
    total = db.count_papers(
        sub_domains=sub_domains,
        search=search,
        published_after=published_after,
        min_quality=min_quality,
        tiers=tiers,
    )
    total_pages = max(1, math.ceil(total / page_size))
    page = max(1, min(page, total_pages))
    offset = (page - 1) * page_size
    papers = db.list_papers(
        sub_domains=sub_domains,
        search=search,
        published_after=published_after,
        min_quality=min_quality,
        tiers=tiers,
        limit=page_size,
        offset=offset,
    )

    return {
        "papers": papers,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "page_size": page_size,
        "has_prev": page > 1,
        "has_next": page < total_pages,
    }


@router.get("/health")
def health() -> dict:
    """Liveness probe."""
    return {"status": "ok"}


@router.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    db: PaperDatabase = Depends(get_db),
    mode: str | None = Query(None),
    sub_domain: list[str] | None = Query(None),
    tier: list[str] | None = Query(None),
    q: str | None = Query(None),
    since: str | None = Query(None),
    page: int = Query(1, ge=1),
) -> HTMLResponse:
    """Full page: paper list with chrome."""
    templates = request.app.state.templates

    # Validate mode
    active_mode = mode if mode in VALID_MODES else None

    # Validate sub-domain tags
    active_tags = _validate_sub_domains(sub_domain or [])
    sub_domain_set = set(active_tags) if active_tags else None

    # _resolve_tiers always returns a non-empty set (defaults to DEFAULT_TIERS
    # when no valid tier param was provided), so the server always applies a
    # tier filter — never an unfiltered query.
    active_tiers = _resolve_tiers(tier)

    search = q.strip() if q else None
    published_after = _parse_since(since)
    config: AppConfig | None = getattr(request.app.state, "config", None)
    min_quality = config.web.min_quality if config else None
    list_ctx = _compute_page_context(
        db, sub_domain_set, search, published_after, min_quality, page, tiers=active_tiers
    )
    sub_domain_counts = db.get_sub_domain_counts()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "mode": active_mode,
            "active_sub_domains": active_tags,
            "active_tiers": sorted(active_tiers),
            "search": search or "",
            "since": since,
            **list_ctx,
            "sub_domain_counts": sub_domain_counts,
            "all_sub_domains": list(SUB_DOMAINS.keys()),
        },
    )


@router.get("/_paper_list", response_class=HTMLResponse)
def paper_list_fragment(
    request: Request,
    db: PaperDatabase = Depends(get_db),
    sub_domain: list[str] | None = Query(None),
    tier: list[str] | None = Query(None),
    q: str | None = Query(None),
    since: str | None = Query(None),
    page: int = Query(1, ge=1),
) -> HTMLResponse:
    """HTMX partial: just the paper list + pagination."""
    templates = request.app.state.templates

    active_tags = _validate_sub_domains(sub_domain or [])
    sub_domain_set = set(active_tags) if active_tags else None
    active_tiers = _resolve_tiers(tier)
    search = q.strip() if q else None
    published_after = _parse_since(since)
    config: AppConfig | None = getattr(request.app.state, "config", None)
    min_quality = config.web.min_quality if config else None
    list_ctx = _compute_page_context(
        db, sub_domain_set, search, published_after, min_quality, page, tiers=active_tiers
    )

    return templates.TemplateResponse(
        request=request,
        name="_paper_list.html",
        context={
            **list_ctx,
            "search": search or "",
            "active_sub_domains": active_tags,
            "active_tiers": sorted(active_tiers),
            "since": since,
            "has_filters": bool(active_tags or search or published_after),
        },
    )


@router.get("/subscribe", response_class=HTMLResponse)
def subscribe_page(request: Request) -> HTMLResponse:
    """Serve the subscription signup form page."""
    templates = request.app.state.templates
    config: AppConfig | None = getattr(request.app.state, "config", None)
    access_enabled = bool(config and config.subscriptions.access.enabled)
    admin_contact = config.web.admin_contact if config else ""
    return templates.TemplateResponse(
        request=request,
        name="subscribe.html",
        context={
            "all_sub_domains": list(SUB_DOMAINS.keys()),
            "access_enabled": access_enabled,
            "admin_contact": admin_contact,
        },
    )


def _admin_contact_suffix(contact: str) -> str:
    """Render the parenthetical after 管理员, or '' when no contact configured."""
    return f"（{contact}）" if contact else ""


@router.post("/api/subscribe", response_class=HTMLResponse)
def subscribe_api(
    request: Request,
    db: PaperDatabase = Depends(get_db),
    email: str = Form(...),
    sub_domain: list[str] = Form([]),
    access_code: str | None = Form(None),
    send_now: bool = Form(False),
) -> HTMLResponse:
    """Handle subscription form submission.

    Returns HTML fragment for HTMX to display success/error message.
    """
    templates = request.app.state.templates

    # Validate global email config before accepting subscription
    config: AppConfig | None = getattr(request.app.state, "config", None)
    admin_suffix = _admin_contact_suffix(config.web.admin_contact if config else "")
    if config is None or not config.email.enabled:
        return templates.TemplateResponse(
            request=request,
            name="_subscribe_result.html",
            context={
                "success": False,
                "error": f"系统未配置邮件发送功能，请联系管理员{admin_suffix}",
            },
        )

    missing = missing_email_config_fields(config.email)
    if missing:
        return templates.TemplateResponse(
            request=request,
            name="_subscribe_result.html",
            context={
                "success": False,
                "error": f"邮件配置不完整（缺少 {', '.join(missing)}），请联系管理员{admin_suffix}",
            },
        )

    if not config.subscriptions.access.is_valid_code(access_code):
        return templates.TemplateResponse(
            request=request,
            name="_subscribe_result.html",
            context={
                "success": False,
                "error": f"订阅需要有效授权码，请联系管理员{admin_suffix}获取访问权限",
            },
        )

    # Validate input using Pydantic model
    try:
        sub_req = SubscriptionRequest(email=email, sub_domains=sub_domain)
    except ValidationError as e:
        # Extract error messages
        errors = [err["msg"] for err in e.errors()]
        return templates.TemplateResponse(
            request=request,
            name="_subscribe_result.html",
            context={
                "success": False,
                "error": "; ".join(errors),
            },
        )

    existing = db.get_subscription(sub_req.email)
    is_update = existing is not None and existing["status"] == "active"
    if existing is not None and existing["status"] != "active":
        return templates.TemplateResponse(
            request=request,
            name="_subscribe_result.html",
            context={
                "success": False,
                "error": f"该邮箱已取消订阅，暂不支持直接重新激活，请联系管理员{admin_suffix}",
            },
        )

    if is_update:
        db.update_subscription(sub_req.email, sub_req.sub_domains)
    else:
        try:
            db.add_subscription(sub_req.email, sub_req.sub_domains)
        except sqlite3.IntegrityError:
            db.update_subscription(sub_req.email, sub_req.sub_domains)
            is_update = True

    # Add/update runtime config with SMTP credentials from global config
    unsubscribe_url = build_unsubscribe_url(
        sub_req.email,
        config.web.public_base_url,
        config.subscriptions.unsubscribe.secret,
    )
    if not unsubscribe_url:
        logger.warning(f"Unsubscribe link not configured for subscription user '{sub_req.email}'")
    user_config = subscription_to_user_config(
        sub_req.email,
        sub_req.sub_domains,
        config.email,
        default_top_n=config.subscriptions.default_top_n,
        unsubscribe_url=unsubscribe_url,
    )
    _upsert_runtime_user(config, user_config)
    action = "Updated" if is_update else "Added"
    logger.info(f"{action} subscription user '{sub_req.email}' in runtime config")
    sent_now = (not is_update and config.subscriptions.send_initial_digest_on_signup) or send_now
    if sent_now:
        _enqueue_initial_digest(request, config, sub_req.email)

    # Return success response
    return templates.TemplateResponse(
        request=request,
        name="_subscribe_result.html",
        context={
            "success": True,
            "updated": is_update,
            "sent_now": sent_now,
            "email": sub_req.email,
            "sub_domains": sub_req.sub_domains,
        },
    )


def _valid_unsubscribe_request(config: AppConfig | None, email: str, token: str) -> bool:
    if config is None or not config.subscriptions.unsubscribe.secret:
        return False
    return verify_unsubscribe_token(
        email,
        token,
        config.subscriptions.unsubscribe.secret,
        config.subscriptions.unsubscribe.token_max_age_hours * 3600,
    )


@router.get("/unsubscribe", response_class=HTMLResponse)
def unsubscribe_page(
    request: Request,
    email: str = Query(""),
    token: str = Query(""),
) -> HTMLResponse:
    """Show unsubscribe confirmation for a valid signed link."""
    templates = request.app.state.templates
    config: AppConfig | None = getattr(request.app.state, "config", None)
    if not _valid_unsubscribe_request(config, email, token):
        return templates.TemplateResponse(
            request=request,
            name="unsubscribe.html",
            context={"error": "取消订阅链接无效或已过期"},
        )
    return templates.TemplateResponse(
        request=request,
        name="unsubscribe.html",
        context={"email": email, "token": token},
    )


@router.post("/unsubscribe", response_class=HTMLResponse)
def unsubscribe_confirm(
    request: Request,
    db: PaperDatabase = Depends(get_db),
    email: str = Form(...),
    token: str = Form(...),
) -> HTMLResponse:
    """Deactivate a subscription after signed confirmation."""
    templates = request.app.state.templates
    config: AppConfig | None = getattr(request.app.state, "config", None)
    if not _valid_unsubscribe_request(config, email, token):
        return templates.TemplateResponse(
            request=request,
            name="unsubscribe.html",
            context={"error": "取消订阅链接无效或已过期"},
        )

    db.unsubscribe_email(email)
    if config is not None:
        config.users = [u for u in config.users if u.user_id != email]
    return templates.TemplateResponse(
        request=request,
        name="unsubscribe.html",
        context={"success": True, "email": email},
    )
