"""Web route handlers."""

from __future__ import annotations

import math

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse

from paper_agent.models import SUB_DOMAINS
from paper_agent.storage.database import PaperDatabase
from paper_agent.web.deps import get_db

router = APIRouter()

PAGE_SIZE = 25
VALID_MODES = {"all", "custom"}


def _validate_sub_domains(tags: list[str]) -> list[str]:
    """Return only tags that are valid SUB_DOMAINS keys."""
    return [t for t in tags if t in SUB_DOMAINS]


def _compute_page_context(
    db: PaperDatabase,
    sub_domains: set[str] | None,
    search: str | None,
    page: int,
    page_size: int = PAGE_SIZE,
) -> dict:
    """Build the template context dict for the paper list + pagination."""
    total = db.count_papers(sub_domains=sub_domains, search=search)
    total_pages = max(1, math.ceil(total / page_size))
    page = max(1, min(page, total_pages))
    offset = (page - 1) * page_size
    papers = db.list_papers(
        sub_domains=sub_domains,
        search=search,
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
    list_ctx = _compute_page_context(db, sub_domain_set, search, page)
    sub_domain_counts = db.get_sub_domain_counts()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "mode": active_mode,
            "active_sub_domains": active_tags,
            "search": search or "",
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
    page: int = Query(1, ge=1),
) -> HTMLResponse:
    """HTMX partial: just the paper list + pagination."""
    templates = request.app.state.templates

    active_tags = _validate_sub_domains(sub_domain or [])
    sub_domain_set = set(active_tags) if active_tags else None
    search = q.strip() if q else None
    list_ctx = _compute_page_context(db, sub_domain_set, search, page)

    return templates.TemplateResponse(
        request=request,
        name="_paper_list.html",
        context={
            **list_ctx,
            "has_filters": bool(active_tags or search),
        },
    )
