"""SQLite storage for paper caching and per-user delivery tracking."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from paper_agent.models import DEFAULT_TIER, IMPACT_TIERS, Paper, ScoredPaper

# Schema additions for the enhance-paper-display-and-retrieval change and
# the citation-aware-scoring change. Listed centrally so
# _ensure_papers_columns and write/read paths stay in sync.
_PAPERS_NEW_COLUMNS: tuple[tuple[str, str], ...] = (
    ("key_contributions", "TEXT"),
    ("problem_statement_zh", "TEXT"),
    ("methods_zh", "TEXT"),
    ("impact_tier", "TEXT"),
    # citation-aware-scoring change. citation_count is the live count from
    # Semantic Scholar; citation_count_at_score is the snapshot captured the
    # last time Claude scored this paper, used to detect growth for the
    # dynamic re-scoring path.
    ("citation_count", "INTEGER"),
    ("influential_citation_count", "INTEGER"),
    ("citations_updated_at", "TEXT"),
    ("citation_count_at_score", "INTEGER"),
    ("paper_kind", "TEXT"),
)

# SQL fragment that orders papers by impact tier (breakthrough < solid <
# incremental) and then by descending weighted score. NULL / unknown tier is
# treated as 'solid' to keep legacy rows visible.
_TIER_ORDER_SQL = (
    "CASE COALESCE(impact_tier, 'solid') "
    "WHEN 'breakthrough' THEN 0 "
    "WHEN 'solid' THEN 1 "
    "WHEN 'incremental' THEN 2 "
    "ELSE 1 END ASC, "
    "(relevance_score * 0.6 + quality_score * 0.4) DESC"
)


def _row_get(row: sqlite3.Row, key: str) -> str | None:
    """Safely access a column that may not exist in the row.

    Uses ``keys()`` introspection so this works even with ``SELECT *`` from
    a table that hasn't been migrated yet (e.g. in unit tests constructing
    ad-hoc rows). Returns ``None`` when the column is missing.
    """
    return row[key] if key in row.keys() else None


class PaperDatabase:
    """SQLite database with two tables:
    - papers: cache of scored papers (shared across users)
    - sent_papers: per-user delivery tracking
    """

    def __init__(self, db_path: str | Path = "paper_agent.db"):
        self.db_path = Path(db_path)
        self._ensure_tables()

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ensure_tables(self) -> None:
        with self._connect() as conn:
            # Papers cache: scored once, shared across all users
            conn.execute("""
                CREATE TABLE IF NOT EXISTS papers (
                    arxiv_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    authors TEXT NOT NULL,
                    abstract TEXT NOT NULL,
                    published TEXT NOT NULL,
                    categories TEXT NOT NULL,
                    pdf_url TEXT NOT NULL,
                    abs_url TEXT NOT NULL,
                    relevance_score REAL NOT NULL,
                    quality_score REAL NOT NULL,
                    summary_zh TEXT NOT NULL,
                    sub_domain_tags TEXT NOT NULL,
                    scored_at TEXT NOT NULL
                )
            """)
            self._ensure_papers_columns(conn)

            # Per-user delivery tracking
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sent_papers (
                    user_id TEXT NOT NULL,
                    arxiv_id TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, arxiv_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sent_user
                ON sent_papers(user_id, sent_at)
            """)

            # User subscriptions
            conn.execute("""
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    sub_domains TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    unsubscribed_at TEXT
                )
            """)
            self._ensure_subscription_columns(conn)

    def _ensure_papers_columns(self, conn: sqlite3.Connection) -> None:
        """Apply idempotent migrations for the structured-insights columns.

        Each ALTER TABLE is independent; SQLite raises OperationalError when a
        column already exists, which we swallow so repeat startup is a no-op.
        """
        rows = conn.execute("PRAGMA table_info(papers)").fetchall()
        existing = {row["name"] for row in rows}
        for name, col_type in _PAPERS_NEW_COLUMNS:
            if name in existing:
                continue
            conn.execute(f"ALTER TABLE papers ADD COLUMN {name} {col_type}")

    def _ensure_subscription_columns(self, conn: sqlite3.Connection) -> None:
        """Apply idempotent migrations for subscription metadata columns."""
        rows = conn.execute("PRAGMA table_info(subscriptions)").fetchall()
        columns = {row["name"] for row in rows}
        if "unsubscribed_at" not in columns:
            conn.execute("ALTER TABLE subscriptions ADD COLUMN unsubscribed_at TEXT")

    def is_cached(self, arxiv_id: str) -> bool:
        """Check if a paper is already in the cache (scored)."""
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM papers WHERE arxiv_id = ?", (arxiv_id,)).fetchone()
            return row is not None

    def filter_uncached(self, arxiv_ids: list[str]) -> list[str]:
        """Return IDs that are NOT yet in the papers cache (need scoring)."""
        if not arxiv_ids:
            return []
        with self._connect() as conn:
            placeholders = ",".join("?" * len(arxiv_ids))
            rows = conn.execute(
                f"SELECT arxiv_id FROM papers WHERE arxiv_id IN ({placeholders})",
                arxiv_ids,
            ).fetchall()
            cached_ids = {row["arxiv_id"] for row in rows}
            return [aid for aid in arxiv_ids if aid not in cached_ids]

    def get_papers_missing_insights(
        self,
        limit: int = 500,
        offset: int = 0,
    ) -> list[ScoredPaper]:
        """Return cached papers whose ``impact_tier`` or ``key_contributions`` is NULL.

        Used by ``paper-agent rescore --missing-fields`` to find legacy papers
        scored before the structured-insights columns were added. Paginated so
        the backfill can be interrupted and resumed.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM papers
                   WHERE impact_tier IS NULL OR key_contributions IS NULL
                   LIMIT ? OFFSET ?""",
                (limit, offset),
            ).fetchall()
        return [self._row_to_scored_paper(r) for r in rows]

    def count_papers_missing_insights(self) -> int:
        """Count how many cached papers lack the structured-insight fields."""
        with self._connect() as conn:
            row = conn.execute(
                """SELECT COUNT(*) as cnt FROM papers
                   WHERE impact_tier IS NULL OR key_contributions IS NULL"""
            ).fetchone()
            return row["cnt"]

    # ─── Citation-aware-scoring methods ────────────────────────────────────

    def get_stale_citations(
        self,
        limit: int,
        stale_after_hours: float,
    ) -> list[str]:
        """Return arxiv_ids whose citation data is stale or never fetched.

        A row is considered stale when ``citations_updated_at`` is NULL
        (never refreshed) OR older than ``stale_after_hours`` ago. Results
        are capped by ``limit`` so a single tick can't drown the provider.
        Order: NULL first (oldest priority), then by oldest update.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT arxiv_id FROM papers
                WHERE citations_updated_at IS NULL
                   OR datetime(citations_updated_at, ? || ' hours')
                      <= datetime('now', 'localtime')
                ORDER BY citations_updated_at IS NOT NULL,
                         citations_updated_at ASC
                LIMIT ?
                """,
                (f"+{stale_after_hours}", limit),
            ).fetchall()
        return [row["arxiv_id"] for row in rows]

    def update_citations(
        self,
        updates: list[tuple[str, int, int]],
        updated_at: str | None = None,
    ) -> int:
        """Bulk-update citation counts for refreshed papers.

        Each tuple is ``(arxiv_id, citation_count, influential_count)``.
        Returns the number of rows updated. Does NOT touch
        ``citation_count_at_score`` — that snapshot only moves when Claude
        re-scores the paper.
        """
        if not updates:
            return 0
        ts = updated_at or datetime.now().isoformat()
        with self._connect() as conn:
            cursor = conn.executemany(
                """
                UPDATE papers
                SET citation_count = ?,
                    influential_citation_count = ?,
                    citations_updated_at = ?
                WHERE arxiv_id = ?
                """,
                [(c, i, ts, aid) for aid, c, i in updates],
            )
            return cursor.rowcount

    def get_rescore_candidates(
        self,
        min_delta: int,
        min_ratio: float,
        min_interval_days: int,
        limit: int,
    ) -> list[ScoredPaper]:
        """Select papers eligible for dynamic re-scoring.

        Eligibility (ALL must hold):
          * citation growth since last score ≥ ``min_delta`` (absolute) OR
            ≥ ``min_ratio`` (relative to the last-score snapshot)
          * last scored more than ``min_interval_days`` days ago

        Ordered by largest absolute citation growth first so the per-run
        budget spends on biggest movers (where the LLM's prior judgment is
        most likely stale). NULL ``citation_count_at_score`` is treated as
        0 — a freshly-citation-fetched paper that has never seen a snapshot
        yet counts as having grown by its full current count.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM papers
                WHERE
                    -- absolute growth threshold
                    (
                        (citation_count - COALESCE(citation_count_at_score, 0)) >= ?
                        OR
                        -- relative growth threshold (avoid /0 with MAX(1, ...))
                        (
                            CAST(citation_count - COALESCE(citation_count_at_score, 0) AS REAL)
                            /
                            CAST(MAX(1, COALESCE(citation_count_at_score, 0)) AS REAL)
                        ) >= ?
                    )
                    -- "scored at least N days ago" — express as scored_at +
                    -- N days <= now so positive, zero, and negative interval
                    -- arguments all work. Use <= (not <) because second-level
                    -- truncation in datetime() makes a row scored milliseconds
                    -- ago compare equal at min_interval_days=0. The 'localtime'
                    -- modifier matches the local-naive timestamps written by
                    -- cache_papers via datetime.now().isoformat().
                    AND datetime(scored_at, ? || ' days')
                        <= datetime('now', 'localtime')
                ORDER BY
                    (citation_count - COALESCE(citation_count_at_score, 0)) DESC
                LIMIT ?
                """,
                (min_delta, min_ratio, f"+{min_interval_days}", limit),
            ).fetchall()
        return [self._row_to_scored_paper(r) for r in rows]

    def get_citation_coverage(self) -> dict:
        """Aggregate stats for the admin dashboard.

        Returns a dict with:
          * ``total`` — total cached papers
          * ``refreshed`` — papers with non-NULL ``citations_updated_at``
          * ``with_citations`` — papers with ``citation_count > 0``
          * ``last_refresh_at`` — most recent ``citations_updated_at`` (or None)
        """
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN citations_updated_at IS NOT NULL THEN 1 ELSE 0 END)
                        AS refreshed,
                    SUM(CASE WHEN citation_count IS NOT NULL AND citation_count > 0
                             THEN 1 ELSE 0 END) AS with_citations,
                    MAX(citations_updated_at) AS last_refresh_at
                FROM papers
                """
            ).fetchone()
        return {
            "total": row["total"] or 0,
            "refreshed": row["refreshed"] or 0,
            "with_citations": row["with_citations"] or 0,
            "last_refresh_at": row["last_refresh_at"],
        }

    # ──────────────────────────────────────────────────────────────────────

    def cache_papers(self, papers: list[ScoredPaper]) -> None:
        """Store scored papers in the cache (upsert).

        ⚠️ INSERT OR REPLACE rewrites the entire row, so EVERY column must be
        listed here — including the citation columns. If a re-scored paper
        is passed without its current citation values, those columns would
        be wiped to NULL. The caller (rescore_dynamic) is responsible for
        merging the existing citation_count into the new ScoredPaper before
        passing it back to cache_papers.
        """
        if not papers:
            return
        now = datetime.now().isoformat()
        with self._connect() as conn:
            for sp in papers:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO papers
                    (arxiv_id, title, authors, abstract, published, categories,
                     pdf_url, abs_url, relevance_score, quality_score, summary_zh,
                     sub_domain_tags, scored_at,
                     key_contributions, problem_statement_zh, methods_zh, impact_tier,
                     citation_count, influential_citation_count, citations_updated_at,
                     citation_count_at_score, paper_kind)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sp.paper.arxiv_id,
                        sp.paper.title,
                        ", ".join(sp.paper.authors),
                        sp.paper.abstract,
                        sp.paper.published.isoformat(),
                        ", ".join(sp.paper.categories),
                        sp.paper.pdf_url,
                        sp.paper.abs_url,
                        sp.relevance_score,
                        sp.quality_score,
                        sp.summary_zh,
                        json.dumps(list(sp.sub_domain_tags)),
                        now,
                        json.dumps(list(sp.key_contributions)),
                        sp.problem_statement_zh,
                        sp.methods_zh,
                        sp.impact_tier,
                        sp.citation_count,
                        sp.influential_citation_count,
                        sp.citations_updated_at,
                        # On every score (first or re-score), snapshot the
                        # current citation_count so the next growth check
                        # measures from this baseline.
                        sp.citation_count,
                        sp.paper_kind,
                    ),
                )

    def load_cached_papers(self, arxiv_ids: list[str]) -> list[ScoredPaper]:
        """Load previously scored papers from cache."""
        if not arxiv_ids:
            return []
        with self._connect() as conn:
            placeholders = ",".join("?" * len(arxiv_ids))
            rows = conn.execute(
                f"""SELECT * FROM papers
                    WHERE arxiv_id IN ({placeholders})""",
                arxiv_ids,
            ).fetchall()
        return [self._row_to_scored_paper(row) for row in rows]

    def filter_unsent_for_user(self, user_id: str, arxiv_ids: list[str]) -> list[str]:
        """Return IDs not yet sent to this specific user."""
        if not arxiv_ids:
            return []
        with self._connect() as conn:
            placeholders = ",".join("?" * len(arxiv_ids))
            rows = conn.execute(
                f"""SELECT arxiv_id FROM sent_papers
                    WHERE user_id = ? AND arxiv_id IN ({placeholders})""",
                [user_id] + arxiv_ids,
            ).fetchall()
            sent_ids = {row["arxiv_id"] for row in rows}
            return [aid for aid in arxiv_ids if aid not in sent_ids]

    def mark_sent(self, user_id: str, papers: list[ScoredPaper]) -> None:
        """Mark papers as sent to this user."""
        if not papers:
            return
        now = datetime.now().isoformat()
        with self._connect() as conn:
            for sp in papers:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO sent_papers (user_id, arxiv_id, sent_at)
                    VALUES (?, ?, ?)
                    """,
                    (user_id, sp.paper.arxiv_id, now),
                )

    def _build_filter_clause(
        self,
        sub_domains: set[str] | None = None,
        search: str | None = None,
        published_after: str | None = None,
        min_quality: float | None = None,
        tiers: set[str] | None = None,
        older: str | None = None,
    ) -> tuple[str, list[str | float]]:
        """Build a WHERE clause and parameter list for paper filtering.

        Returns ``(clause, params)`` where ``clause`` is either an empty string
        or starts with `` WHERE ...``.

        ``older`` accepts ``"only"`` (paper_kind = 'older'), ``"exclude"``
        (paper_kind = 'fresh' OR NULL — legacy rows count as fresh), or
        ``"include"`` / ``None`` (no kind filter, pre-change default).
        Any other value is treated as ``"include"``.
        """
        conditions: list[str] = []
        params: list[str | float] = []

        if min_quality is not None and min_quality > 0:
            conditions.append("quality_score >= ?")
            params.append(min_quality)

        if published_after:
            conditions.append("published >= ?")
            params.append(published_after)

        if sub_domains:
            tag_clauses = []
            for tag in sub_domains:
                tag_clauses.append("sub_domain_tags LIKE ?")
                params.append(f'%"{tag}"%')
            conditions.append(f"({' OR '.join(tag_clauses)})")

        if search:
            conditions.append("title LIKE ?")
            params.append(f"%{search}%")

        if tiers:
            # Coerce NULL / unknown impact_tier to 'solid' so legacy rows match
            # naturally when 'solid' is in the requested set.
            valid_tiers = [t for t in tiers if t in IMPACT_TIERS]
            if valid_tiers:
                placeholders = ",".join("?" * len(valid_tiers))
                conditions.append(f"COALESCE(impact_tier, 'solid') IN ({placeholders})")
                params.extend(valid_tiers)

        if older == "only":
            conditions.append("paper_kind = 'older'")
        elif older == "exclude":
            # Legacy rows have NULL paper_kind; treat them as fresh.
            conditions.append("(paper_kind IS NULL OR paper_kind = 'fresh')")
        # "include" / None / unknown → no kind filter

        if conditions:
            return " WHERE " + " AND ".join(conditions), params
        return "", params

    def _row_to_scored_paper(self, row: sqlite3.Row) -> ScoredPaper:
        """Convert a ``papers`` table row into a :class:`ScoredPaper`."""
        tags = json.loads(row["sub_domain_tags"]) if row["sub_domain_tags"] else []
        paper = Paper(
            arxiv_id=row["arxiv_id"],
            title=row["title"],
            authors=[a.strip() for a in row["authors"].split(",")],
            abstract=row["abstract"],
            published=datetime.fromisoformat(row["published"]),
            categories=[c.strip() for c in row["categories"].split(",")],
            pdf_url=row["pdf_url"],
            abs_url=row["abs_url"],
        )
        # The structured-insight columns were added later; legacy rows have
        # NULL values that we coerce to safe defaults. _row_get tolerates rows
        # produced by old SELECT * statements that don't include them at all.
        contribs_raw = _row_get(row, "key_contributions")
        contribs = tuple(json.loads(contribs_raw)) if contribs_raw else ()
        # Citation columns added in citation-aware-scoring change. Legacy rows
        # read back as 0 / None / "fresh" so existing behavior is preserved.
        cit_count_raw = _row_get(row, "citation_count")
        infl_count_raw = _row_get(row, "influential_citation_count")
        cit_at_score_raw = _row_get(row, "citation_count_at_score")
        return ScoredPaper(
            paper=paper,
            relevance_score=row["relevance_score"],
            quality_score=row["quality_score"],
            summary_zh=row["summary_zh"],
            sub_domain_tags=tuple(tags),
            key_contributions=contribs,
            problem_statement_zh=_row_get(row, "problem_statement_zh") or "",
            methods_zh=_row_get(row, "methods_zh") or "",
            impact_tier=_row_get(row, "impact_tier") or DEFAULT_TIER,
            citation_count=int(cit_count_raw) if cit_count_raw is not None else 0,
            influential_citation_count=int(infl_count_raw) if infl_count_raw is not None else 0,
            citations_updated_at=_row_get(row, "citations_updated_at"),
            citation_count_at_score=(
                int(cit_at_score_raw) if cit_at_score_raw is not None else None
            ),
            paper_kind=_row_get(row, "paper_kind") or "fresh",
        )

    def list_papers(
        self,
        sub_domains: set[str] | None = None,
        search: str | None = None,
        published_after: str | None = None,
        min_quality: float | None = None,
        tiers: set[str] | None = None,
        older: str | None = None,
        limit: int = 25,
        offset: int = 0,
    ) -> list[ScoredPaper]:
        """Return scored papers matching the given filters, sorted by tier-then-score.

        Ordering: impact_tier ASC (breakthrough → solid → incremental, with
        NULL / unknown coerced to ``solid``), then weighted total score DESC.
        ``limit`` and ``offset`` control pagination. ``older`` accepts
        ``"only" | "include" | "exclude" | None`` — see ``_build_filter_clause``.
        """
        where, params = self._build_filter_clause(
            sub_domains, search, published_after, min_quality, tiers, older
        )
        order = f" ORDER BY {_TIER_ORDER_SQL}"
        paging = " LIMIT ? OFFSET ?"
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM papers{where}{order}{paging}",
                [*params, limit, offset],
            ).fetchall()
        return [self._row_to_scored_paper(r) for r in rows]

    def count_papers(
        self,
        sub_domains: set[str] | None = None,
        search: str | None = None,
        published_after: str | None = None,
        min_quality: float | None = None,
        tiers: set[str] | None = None,
        older: str | None = None,
    ) -> int:
        """Return the number of scored papers matching the given filters."""
        where, params = self._build_filter_clause(
            sub_domains, search, published_after, min_quality, tiers, older
        )
        with self._connect() as conn:
            row = conn.execute(f"SELECT COUNT(*) as cnt FROM papers{where}", params).fetchone()
            return row["cnt"]

    def get_sub_domain_counts(self) -> dict[str, int]:
        """Return per-sub-domain paper counts for chip badges.

        A paper with multiple tags contributes to each tag's count.
        """
        from paper_agent.models import SUB_DOMAINS

        counts: dict[str, int] = {tag: 0 for tag in SUB_DOMAINS}
        with self._connect() as conn:
            rows = conn.execute("SELECT sub_domain_tags FROM papers").fetchall()
        for row in rows:
            tags = json.loads(row["sub_domain_tags"]) if row["sub_domain_tags"] else []
            for tag in tags:
                if tag in counts:
                    counts[tag] += 1
        return counts

    def add_subscription(self, email: str, sub_domains: list[str]) -> None:
        """Add a new subscription to the database.

        Args:
            email: User's email address (must be unique)
            sub_domains: List of sub-domain names the user is interested in

        Raises:
            sqlite3.IntegrityError: If email already exists
        """
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO subscriptions (email, sub_domains, created_at, status)
                VALUES (?, ?, ?, 'active')
                """,
                (email, json.dumps(sub_domains), now),
            )

    def update_subscription(self, email: str, sub_domains: list[str]) -> bool:
        """Update sub-domain preferences for an active subscription."""
        with self._connect() as conn:
            cur = conn.execute(
                """UPDATE subscriptions
                   SET sub_domains = ?
                   WHERE email = ? AND status = 'active'""",
                (json.dumps(sub_domains), email),
            )
            return cur.rowcount > 0

    def is_email_subscribed(self, email: str) -> bool:
        """Check if an email address is already subscribed.

        Args:
            email: Email address to check

        Returns:
            True if email exists with status='active', False otherwise
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM subscriptions WHERE email = ? AND status = 'active'",
                (email,),
            ).fetchone()
            return row is not None

    def get_subscription(self, email: str) -> dict | None:
        """Get subscription details by email.

        Args:
            email: Email address to look up

        Returns:
            Dict with email, sub_domains, created_at, status if exists; None otherwise
        """
        with self._connect() as conn:
            row = conn.execute(
                """SELECT email, sub_domains, created_at, status, unsubscribed_at
                   FROM subscriptions WHERE email = ?""",
                (email,),
            ).fetchone()
            if row is None:
                return None
            return {
                "email": row["email"],
                "sub_domains": json.loads(row["sub_domains"]),
                "created_at": row["created_at"],
                "status": row["status"],
                "unsubscribed_at": row["unsubscribed_at"],
            }

    def unsubscribe_email(self, email: str) -> bool:
        """Mark a subscription inactive without deleting its row.

        Returns True when a subscription row exists, including rows that were
        already inactive.
        """
        now = datetime.now().isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM subscriptions WHERE email = ?",
                (email,),
            ).fetchone()
            if row is None:
                return False
            conn.execute(
                """UPDATE subscriptions
                   SET status = 'inactive', unsubscribed_at = COALESCE(unsubscribed_at, ?)
                   WHERE email = ?""",
                (now, email),
            )
            return True

    def load_active_subscriptions(self) -> list[dict]:
        """Load all active subscriptions from the database.

        Returns:
            List of dicts with email, sub_domains, created_at, status
        """
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT email, sub_domains, created_at, status, unsubscribed_at
                   FROM subscriptions WHERE status = 'active'"""
            ).fetchall()
            return [
                {
                    "email": row["email"],
                    "sub_domains": json.loads(row["sub_domains"]),
                    "created_at": row["created_at"],
                    "status": row["status"],
                    "unsubscribed_at": row["unsubscribed_at"],
                }
                for row in rows
            ]

    def get_stats(self, user_id: str | None = None) -> dict:
        """Get database statistics, optionally filtered by user."""
        with self._connect() as conn:
            total_cached = conn.execute("SELECT COUNT(*) as cnt FROM papers").fetchone()["cnt"]

            if user_id:
                total_sent = conn.execute(
                    "SELECT COUNT(*) as cnt FROM sent_papers WHERE user_id = ?",
                    (user_id,),
                ).fetchone()["cnt"]
                today_sent = conn.execute(
                    """SELECT COUNT(*) as cnt FROM sent_papers
                       WHERE user_id = ? AND date(sent_at) = date('now')""",
                    (user_id,),
                ).fetchone()["cnt"]
                last_sent = conn.execute(
                    "SELECT MAX(sent_at) as last FROM sent_papers WHERE user_id = ?",
                    (user_id,),
                ).fetchone()["last"]
            else:
                total_sent = conn.execute("SELECT COUNT(*) as cnt FROM sent_papers").fetchone()[
                    "cnt"
                ]
                today_sent = conn.execute(
                    """SELECT COUNT(*) as cnt FROM sent_papers
                       WHERE date(sent_at) = date('now')"""
                ).fetchone()["cnt"]
                last_sent = conn.execute("SELECT MAX(sent_at) as last FROM sent_papers").fetchone()[
                    "last"
                ]

            # Count unique users
            user_count = conn.execute(
                "SELECT COUNT(DISTINCT user_id) as cnt FROM sent_papers"
            ).fetchone()["cnt"]

            return {
                "total_cached": total_cached,
                "total_sent": total_sent,
                "sent_today": today_sent,
                "last_sent": last_sent or "never",
                "user_count": user_count,
                "user_id": user_id,
                "db_path": str(self.db_path),
            }

    # ─── Admin dashboard aggregates ───
    #
    # These methods power the operator dashboard. They are kept on
    # PaperDatabase (rather than a separate stats service) because they
    # are pure SQL aggregates over the same tables already owned here.

    def count_active_subscriptions(self) -> int:
        """Number of subscription rows whose ``status = 'active'``."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM subscriptions WHERE status = 'active'"
            ).fetchone()
            return int(row["cnt"])

    def get_user_stats(self) -> list[dict]:
        """Per-user delivery stats for the admin dashboard.

        Returns one record per user_id present in either the subscriptions
        table OR sent_papers. Subscribed users with zero deliveries appear
        with ``total_sent = sent_7d = sent_30d = 0`` and ``last_sent_at = None``.

        Each record: ``{user_id, total_sent, sent_7d, sent_30d, last_sent_at,
        status, sub_domains}``. The ``status`` is ``"active"`` /
        ``"inactive"`` for subscribers, or ``None`` for sent-only users
        (e.g. legacy CLI-configured users like ``test_user``).
        """
        today = date.today()
        cutoff_7d = (today - timedelta(days=7)).isoformat()
        cutoff_30d = (today - timedelta(days=30)).isoformat()

        with self._connect() as conn:
            # Subscription rows (active + inactive both surface in the dashboard
            # so the operator can see who unsubscribed and when).
            sub_rows = conn.execute(
                """SELECT email, sub_domains, status, created_at, unsubscribed_at
                   FROM subscriptions"""
            ).fetchall()
            sent_rows = conn.execute(
                """SELECT user_id,
                          COUNT(*) AS total_sent,
                          SUM(CASE WHEN sent_at >= ? THEN 1 ELSE 0 END) AS sent_7d,
                          SUM(CASE WHEN sent_at >= ? THEN 1 ELSE 0 END) AS sent_30d,
                          MAX(sent_at) AS last_sent_at
                   FROM sent_papers
                   GROUP BY user_id""",
                (cutoff_7d, cutoff_30d),
            ).fetchall()

        sent_by_user = {
            r["user_id"]: {
                "total_sent": int(r["total_sent"] or 0),
                "sent_7d": int(r["sent_7d"] or 0),
                "sent_30d": int(r["sent_30d"] or 0),
                "last_sent_at": r["last_sent_at"],
            }
            for r in sent_rows
        }

        result: list[dict] = []
        seen: set[str] = set()
        for sr in sub_rows:
            uid = sr["email"]
            seen.add(uid)
            agg = sent_by_user.get(uid, {})
            try:
                sub_domains = json.loads(sr["sub_domains"]) if sr["sub_domains"] else []
            except (json.JSONDecodeError, TypeError):
                sub_domains = []
            result.append(
                {
                    "user_id": uid,
                    "status": sr["status"],
                    "created_at": sr["created_at"],
                    "unsubscribed_at": sr["unsubscribed_at"],
                    "sub_domains": sub_domains,
                    "total_sent": agg.get("total_sent", 0),
                    "sent_7d": agg.get("sent_7d", 0),
                    "sent_30d": agg.get("sent_30d", 0),
                    "last_sent_at": agg.get("last_sent_at"),
                }
            )

        # Users that have received papers but aren't (or never were) in the
        # subscriptions table — e.g. the static `test_user` from config.yaml.
        # Surface them too so the dashboard reflects the full delivery picture.
        for uid, agg in sent_by_user.items():
            if uid in seen:
                continue
            result.append(
                {
                    "user_id": uid,
                    "status": None,
                    "created_at": None,
                    "unsubscribed_at": None,
                    "sub_domains": [],
                    "total_sent": agg["total_sent"],
                    "sent_7d": agg["sent_7d"],
                    "sent_30d": agg["sent_30d"],
                    "last_sent_at": agg["last_sent_at"],
                }
            )
        return result

    def _daily_counts(self, sql: str, days: int) -> list[dict]:
        """Run a per-day ``COUNT(*)`` aggregate and pad to ``days`` entries.

        The ``sql`` parameter must select ``(d TEXT, cnt INT)`` where ``d``
        is an ISO ``YYYY-MM-DD`` date string. We left-fill missing dates
        with ``count=0`` so the dashboard always renders ``days`` columns,
        ordered most-recent-first.
        """
        if days <= 0:
            return []
        today = date.today()
        cutoff = (today - timedelta(days=days - 1)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(sql, (cutoff,)).fetchall()
        by_date = {r["d"]: int(r["cnt"]) for r in rows}
        out: list[dict] = []
        for i in range(days):
            d = (today - timedelta(days=i)).isoformat()
            out.append({"date": d, "count": by_date.get(d, 0)})
        return out

    def get_daily_sent_counts(self, days: int = 7) -> list[dict]:
        """Per-day delivery counts for the past ``days`` calendar days.

        Returns ``[{date, count}, ...]`` ordered most-recent-first; days
        with no deliveries are present with ``count=0``.
        """
        return self._daily_counts(
            """SELECT DATE(sent_at) AS d, COUNT(*) AS cnt
               FROM sent_papers
               WHERE DATE(sent_at) >= ?
               GROUP BY DATE(sent_at)""",
            days,
        )

    def get_daily_paper_counts(self, days: int = 7) -> list[dict]:
        """Per-day newly-scored paper counts for the past ``days`` calendar days.

        Returns ``[{date, count}, ...]`` ordered most-recent-first; days
        with no scoring activity are present with ``count=0``.
        """
        return self._daily_counts(
            """SELECT DATE(scored_at) AS d, COUNT(*) AS cnt
               FROM papers
               WHERE DATE(scored_at) >= ?
               GROUP BY DATE(scored_at)""",
            days,
        )

    def get_tier_distribution(self) -> dict[str, int]:
        """Paper count per impact tier across the entire cache.

        NULL / unknown tiers fold into ``'solid'`` to match the rest of
        the codebase. Always returns one entry per tier in ``IMPACT_TIERS``
        even when the count is zero.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT COALESCE(impact_tier, 'solid') AS tier, COUNT(*) AS cnt
                   FROM papers GROUP BY COALESCE(impact_tier, 'solid')"""
            ).fetchall()
        counts: dict[str, int] = {tier: 0 for tier in IMPACT_TIERS}
        for row in rows:
            tier = row["tier"]
            if tier in counts:
                counts[tier] += int(row["cnt"])
        return counts

    def get_last_ingest_at(self) -> str | None:
        """ISO timestamp of the most recently scored paper, or None."""
        with self._connect() as conn:
            row = conn.execute("SELECT MAX(scored_at) AS m FROM papers").fetchone()
            return row["m"]

    def get_last_digest_at(self) -> str | None:
        """ISO timestamp of the most recently sent paper, or None."""
        with self._connect() as conn:
            row = conn.execute("SELECT MAX(sent_at) AS m FROM sent_papers").fetchone()
            return row["m"]

    def list_subscriptions(self) -> list[dict]:
        """Return every row in ``subscriptions`` (active + inactive).

        Used by the admin dashboard to render the full subscription list
        including users who have unsubscribed.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT id, email, sub_domains, created_at, status, unsubscribed_at
                   FROM subscriptions ORDER BY created_at"""
            ).fetchall()
        out: list[dict] = []
        for row in rows:
            try:
                sub_domains = json.loads(row["sub_domains"]) if row["sub_domains"] else []
            except (json.JSONDecodeError, TypeError):
                sub_domains = []
            out.append(
                {
                    "id": row["id"],
                    "email": row["email"],
                    "sub_domains": sub_domains,
                    "created_at": row["created_at"],
                    "status": row["status"],
                    "unsubscribed_at": row["unsubscribed_at"],
                }
            )
        return out
