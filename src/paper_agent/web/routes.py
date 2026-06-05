"""Web route handlers."""

from __future__ import annotations

import logging
import math
import sqlite3
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from paper_agent.config import AppConfig, SubscriptionRequest
from paper_agent.models import SUB_DOMAINS
from paper_agent.storage.database import PaperDatabase
from paper_agent.subscriptions import missing_email_config_fields, subscription_to_user_config
from paper_agent.web.deps import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

PAGE_SIZE = 25
VALID_MODES = {"all", "custom"}

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
    page: int,
    page_size: int = PAGE_SIZE,
) -> dict:
    """Build the template context dict for the paper list + pagination."""
    total = db.count_papers(sub_domains=sub_domains, search=search, published_after=published_after)
    total_pages = max(1, math.ceil(total / page_size))
    page = max(1, min(page, total_pages))
    offset = (page - 1) * page_size
    papers = db.list_papers(
        sub_domains=sub_domains,
        search=search,
        published_after=published_after,
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

    search = q.strip() if q else None
    published_after = _parse_since(since)
    list_ctx = _compute_page_context(db, sub_domain_set, search, published_after, page)
    sub_domain_counts = db.get_sub_domain_counts()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "mode": active_mode,
            "active_sub_domains": active_tags,
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
    q: str | None = Query(None),
    since: str | None = Query(None),
    page: int = Query(1, ge=1),
) -> HTMLResponse:
    """HTMX partial: just the paper list + pagination."""
    templates = request.app.state.templates

    active_tags = _validate_sub_domains(sub_domain or [])
    sub_domain_set = set(active_tags) if active_tags else None
    search = q.strip() if q else None
    published_after = _parse_since(since)
    list_ctx = _compute_page_context(db, sub_domain_set, search, published_after, page)

    return templates.TemplateResponse(
        request=request,
        name="_paper_list.html",
        context={
            **list_ctx,
            "search": search or "",
            "active_sub_domains": active_tags,
            "since": since,
            "has_filters": bool(active_tags or search or published_after),
        },
    )


@router.get("/subscribe", response_class=HTMLResponse)
def subscribe_page(request: Request) -> HTMLResponse:
    """Serve the subscription signup form page."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="subscribe.html",
        context={
            "all_sub_domains": list(SUB_DOMAINS.keys()),
        },
    )


@router.post("/api/subscribe", response_class=HTMLResponse)
def subscribe_api(
    request: Request,
    db: PaperDatabase = Depends(get_db),
    email: str = Form(...),
    sub_domain: list[str] = Form([]),
) -> HTMLResponse:
    """Handle subscription form submission.

    Returns HTML fragment for HTMX to display success/error message.
    """
    templates = request.app.state.templates

    # Validate global email config before accepting subscription
    config: AppConfig | None = getattr(request.app.state, "config", None)
    if config is None or not config.email.enabled:
        return templates.TemplateResponse(
            request=request,
            name="_subscribe_result.html",
            context={
                "success": False,
                "error": "系统未配置邮件发送功能，请联系管理员",
            },
        )

    missing = missing_email_config_fields(config.email)
    if missing:
        return templates.TemplateResponse(
            request=request,
            name="_subscribe_result.html",
            context={
                "success": False,
                "error": f"邮件配置不完整（缺少 {', '.join(missing)}），请联系管理员",
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

    # Check for duplicate email
    if db.is_email_subscribed(sub_req.email):
        existing = db.get_subscription(sub_req.email)
        return templates.TemplateResponse(
            request=request,
            name="_subscribe_result.html",
            context={
                "success": False,
                "already_subscribed": True,
                "email": sub_req.email,
                "sub_domains": existing["sub_domains"] if existing else [],
            },
        )

    # Add subscription to database
    try:
        db.add_subscription(sub_req.email, sub_req.sub_domains)
    except sqlite3.IntegrityError:
        # Race condition: another request added the same email
        return templates.TemplateResponse(
            request=request,
            name="_subscribe_result.html",
            context={
                "success": False,
                "already_subscribed": True,
                "email": sub_req.email,
                "sub_domains": sub_req.sub_domains,
            },
        )

    # Add to runtime config with SMTP credentials from global config
    user_config = subscription_to_user_config(sub_req.email, sub_req.sub_domains, config.email)
    config.users.append(user_config)
    logger.info(f"Added subscription user '{sub_req.email}' to runtime config")

    # Return success response
    return templates.TemplateResponse(
        request=request,
        name="_subscribe_result.html",
        context={
            "success": True,
            "email": sub_req.email,
            "sub_domains": sub_req.sub_domains,
        },
    )
