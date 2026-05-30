"""SQLite storage for paper caching and per-user delivery tracking."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from paper_agent.models import Paper, ScoredPaper


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

    def cache_papers(self, papers: list[ScoredPaper]) -> None:
        """Store scored papers in the cache (upsert)."""
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
                     sub_domain_tags, scored_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

        results = []
        for row in rows:
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
            results.append(
                ScoredPaper(
                    paper=paper,
                    relevance_score=row["relevance_score"],
                    quality_score=row["quality_score"],
                    summary_zh=row["summary_zh"],
                    sub_domain_tags=tuple(tags),
                )
            )
        return results

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
    ) -> tuple[str, list[str]]:
        """Build a WHERE clause and parameter list for paper filtering.

        Returns ``(clause, params)`` where ``clause`` is either an empty string
        or starts with `` WHERE ...``.
        """
        conditions: list[str] = []
        params: list[str] = []

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
        return ScoredPaper(
            paper=paper,
            relevance_score=row["relevance_score"],
            quality_score=row["quality_score"],
            summary_zh=row["summary_zh"],
            sub_domain_tags=tuple(tags),
        )

    def list_papers(
        self,
        sub_domains: set[str] | None = None,
        search: str | None = None,
        published_after: str | None = None,
        limit: int = 25,
        offset: int = 0,
    ) -> list[ScoredPaper]:
        """Return scored papers matching the given filters, sorted by total score.

        Papers are sorted highest-score-first. ``limit`` and ``offset`` control
        pagination.
        """
        where, params = self._build_filter_clause(sub_domains, search, published_after)
        order = " ORDER BY (relevance_score * 0.6 + quality_score * 0.4) DESC"
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
    ) -> int:
        """Return the number of scored papers matching the given filters."""
        where, params = self._build_filter_clause(sub_domains, search, published_after)
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
