"""SQLite storage for deduplication and history tracking."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator

from paper_agent.models import ScoredPaper


class PaperDatabase:
    """SQLite database for tracking sent papers."""

    def __init__(self, db_path: str | Path = "paper_agent.db"):
        self.db_path = Path(db_path)
        self._ensure_tables()

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sent_papers (
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
                    sent_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sent_at
                ON sent_papers(sent_at)
            """)

    def is_sent(self, arxiv_id: str) -> bool:
        """Check if a paper has already been sent."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM sent_papers WHERE arxiv_id = ?", (arxiv_id,)
            ).fetchone()
            return row is not None

    def filter_new(self, arxiv_ids: list[str]) -> list[str]:
        """Return only the IDs that haven't been sent yet."""
        if not arxiv_ids:
            return []
        with self._connect() as conn:
            placeholders = ",".join("?" * len(arxiv_ids))
            rows = conn.execute(
                f"SELECT arxiv_id FROM sent_papers WHERE arxiv_id IN ({placeholders})",
                arxiv_ids,
            ).fetchall()
            sent_ids = {row["arxiv_id"] for row in rows}
            return [aid for aid in arxiv_ids if aid not in sent_ids]

    def mark_sent(self, papers: list[ScoredPaper]) -> None:
        """Mark papers as sent after successful notification."""
        now = datetime.now().isoformat()
        with self._connect() as conn:
            for sp in papers:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO sent_papers
                    (arxiv_id, title, authors, abstract, published, categories,
                     pdf_url, abs_url, relevance_score, quality_score, summary_zh, sent_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        now,
                    ),
                )

    def get_stats(self) -> dict:
        """Get database statistics."""
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) as cnt FROM sent_papers").fetchone()["cnt"]
            today = conn.execute(
                "SELECT COUNT(*) as cnt FROM sent_papers WHERE date(sent_at) = date('now')"
            ).fetchone()["cnt"]
            last_sent = conn.execute(
                "SELECT MAX(sent_at) as last FROM sent_papers"
            ).fetchone()["last"]
            return {
                "total_papers": total,
                "sent_today": today,
                "last_sent": last_sent or "never",
                "db_path": str(self.db_path),
            }
