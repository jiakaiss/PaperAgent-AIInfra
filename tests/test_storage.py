"""Tests for SQLite storage with two-table schema."""

import os
import tempfile
from datetime import datetime

from paper_agent.models import Paper, ScoredPaper
from paper_agent.storage.database import PaperDatabase


def _make_scored_paper(arxiv_id: str = "2401.00001v1", tags=("quantization",)) -> ScoredPaper:
    paper = Paper(
        arxiv_id=arxiv_id,
        title="Test Paper",
        authors=["Alice"],
        abstract="Test abstract",
        published=datetime(2024, 1, 15),
        categories=["cs.DC"],
        pdf_url="https://arxiv.org/pdf/" + arxiv_id,
        abs_url="https://arxiv.org/abs/" + arxiv_id,
    )
    return ScoredPaper(
        paper=paper,
        relevance_score=8.0,
        quality_score=7.0,
        summary_zh="测试论文",
        sub_domain_tags=tags,
    )


def test_cache_and_filter_uncached():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = PaperDatabase(db_path)
        sp1 = _make_scored_paper("2401.00001v1")
        sp2 = _make_scored_paper("2401.00002v1")

        # Initially all uncached
        uncached = db.filter_uncached(["2401.00001v1", "2401.00002v1", "2401.00003v1"])
        assert len(uncached) == 3

        # Cache some papers
        db.cache_papers([sp1, sp2])

        # Now only 00003 should be uncached
        uncached = db.filter_uncached(["2401.00001v1", "2401.00002v1", "2401.00003v1"])
        assert uncached == ["2401.00003v1"]
    finally:
        os.unlink(db_path)


def test_load_cached_papers():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = PaperDatabase(db_path)
        sp = _make_scored_paper("2401.00001v1", tags=("quantization", "sparsity"))
        db.cache_papers([sp])

        loaded = db.load_cached_papers(["2401.00001v1"])
        assert len(loaded) == 1
        assert loaded[0].paper.arxiv_id == "2401.00001v1"
        assert loaded[0].sub_domain_tags == ("quantization", "sparsity")
        assert loaded[0].relevance_score == 8.0
    finally:
        os.unlink(db_path)


def test_per_user_sent_tracking():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = PaperDatabase(db_path)
        sp1 = _make_scored_paper("2401.00001v1")
        sp2 = _make_scored_paper("2401.00002v1")

        # Mark as sent for alice only
        db.mark_sent("alice", [sp1, sp2])

        # Alice has seen both
        unsent_alice = db.filter_unsent_for_user("alice", ["2401.00001v1", "2401.00002v1"])
        assert unsent_alice == []

        # Bob hasn't seen any
        unsent_bob = db.filter_unsent_for_user("bob", ["2401.00001v1", "2401.00002v1"])
        assert set(unsent_bob) == {"2401.00001v1", "2401.00002v1"}
    finally:
        os.unlink(db_path)


def test_mark_sent_idempotent():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = PaperDatabase(db_path)
        sp = _make_scored_paper("2401.00001v1")

        # Mark twice should not error
        db.mark_sent("alice", [sp])
        db.mark_sent("alice", [sp])

        unsent = db.filter_unsent_for_user("alice", ["2401.00001v1"])
        assert unsent == []
    finally:
        os.unlink(db_path)


def test_stats_global():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = PaperDatabase(db_path)
        stats = db.get_stats()
        assert stats["total_cached"] == 0
        assert stats["total_sent"] == 0
        assert stats["sent_today"] == 0
        assert stats["last_sent"] == "never"
        assert stats["user_count"] == 0
    finally:
        os.unlink(db_path)


def test_stats_per_user():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = PaperDatabase(db_path)
        sp = _make_scored_paper("2401.00001v1")
        db.cache_papers([sp])
        db.mark_sent("alice", [sp])

        stats_alice = db.get_stats(user_id="alice")
        assert stats_alice["total_sent"] == 1

        stats_bob = db.get_stats(user_id="bob")
        assert stats_bob["total_sent"] == 0
    finally:
        os.unlink(db_path)


# ─── Structured-insights schema migration + tier-aware queries ───


def _make_scored_paper_full(
    arxiv_id: str = "2401.99999v1",
    tags=("quantization",),
    relevance: float = 8.0,
    quality: float = 7.0,
    impact_tier: str = "solid",
    key_contributions=("贡献 A",),
    problem_zh: str = "问题",
    methods_zh: str = "方法",
) -> ScoredPaper:
    """Like _make_scored_paper but exercises the new structured fields too."""
    paper = Paper(
        arxiv_id=arxiv_id,
        title=f"Paper {arxiv_id}",
        authors=["Alice"],
        abstract="Abstract",
        published=datetime(2024, 1, 15),
        categories=["cs.DC"],
        pdf_url="https://arxiv.org/pdf/" + arxiv_id,
        abs_url="https://arxiv.org/abs/" + arxiv_id,
    )
    return ScoredPaper(
        paper=paper,
        relevance_score=relevance,
        quality_score=quality,
        summary_zh="摘要",
        sub_domain_tags=tags,
        key_contributions=key_contributions,
        problem_statement_zh=problem_zh,
        methods_zh=methods_zh,
        impact_tier=impact_tier,
    )


def test_migration_adds_structured_insight_columns_to_legacy_db():
    """A pre-existing legacy schema (no new columns) gets ALTER TABLE'd in place."""
    import sqlite3

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        # Construct a "legacy" papers table by hand — only the original columns.
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """
                CREATE TABLE papers (
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
                """
            )
            conn.execute(
                """
                INSERT INTO papers (arxiv_id, title, authors, abstract, published,
                  categories, pdf_url, abs_url, relevance_score, quality_score,
                  summary_zh, sub_domain_tags, scored_at)
                VALUES (?, 't', 'A', 'abs', ?, 'cs.DC', 'p', 'a', 8.0, 7.0,
                        'sum', '["quantization"]', ?)
                """,
                ("legacy-1", "2024-01-01T00:00:00", "2024-01-02T00:00:00"),
            )
            conn.commit()
        finally:
            conn.close()

        # Opening through PaperDatabase should add the 4 new columns and leave
        # the existing row in place with NULLs for the new fields.
        db = PaperDatabase(db_path)
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(papers)").fetchall()}
        assert {
            "key_contributions",
            "problem_statement_zh",
            "methods_zh",
            "impact_tier",
        } <= cols

        # Existing row reads back with default values for the new fields.
        loaded = db.load_cached_papers(["legacy-1"])
        assert len(loaded) == 1
        sp = loaded[0]
        assert sp.key_contributions == ()
        assert sp.problem_statement_zh == ""
        assert sp.methods_zh == ""
        assert sp.impact_tier == "solid"
    finally:
        try:
            os.unlink(db_path)
        except PermissionError:
            pass  # Windows may hold a lock; clean up at directory level.


def test_migration_is_idempotent_across_restarts():
    """Opening the DB twice doesn't error or duplicate columns."""
    import sqlite3

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        PaperDatabase(db_path)
        # Second open — would raise OperationalError if ALTER weren't guarded.
        PaperDatabase(db_path)
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cols = [r["name"] for r in conn.execute("PRAGMA table_info(papers)").fetchall()]
        # Each new column should appear exactly once.
        for name in ("key_contributions", "problem_statement_zh", "methods_zh", "impact_tier"):
            assert cols.count(name) == 1
    finally:
        try:
            os.unlink(db_path)
        except PermissionError:
            pass


def test_cache_and_load_preserves_structured_insights():
    """Round-trip: cache a paper with full insights → load → identical fields."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = PaperDatabase(db_path)
        sp = _make_scored_paper_full(
            arxiv_id="round-trip",
            key_contributions=("贡献 1", "贡献 2"),
            impact_tier="breakthrough",
        )
        db.cache_papers([sp])
        [loaded] = db.load_cached_papers(["round-trip"])
        assert loaded.key_contributions == ("贡献 1", "贡献 2")
        assert loaded.problem_statement_zh == "问题"
        assert loaded.methods_zh == "方法"
        assert loaded.impact_tier == "breakthrough"
    finally:
        try:
            os.unlink(db_path)
        except PermissionError:
            pass


def test_list_papers_orders_by_tier_then_score():
    """Tier ordering wins over total_score; ties broken by score DESC."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = PaperDatabase(db_path)
        # An incremental paper with the highest raw score still loses to a
        # low-scoring breakthrough.
        db.cache_papers(
            [
                _make_scored_paper_full(
                    "inc-top", relevance=10.0, quality=10.0, impact_tier="incremental"
                ),
                _make_scored_paper_full(
                    "brk-low", relevance=4.0, quality=4.0, impact_tier="breakthrough"
                ),
                _make_scored_paper_full("sol-mid", relevance=7.0, quality=7.0, impact_tier="solid"),
                _make_scored_paper_full("sol-low", relevance=5.0, quality=5.0, impact_tier="solid"),
            ]
        )
        ordered = [p.paper.arxiv_id for p in db.list_papers(limit=10)]
        assert ordered == ["brk-low", "sol-mid", "sol-low", "inc-top"]
    finally:
        try:
            os.unlink(db_path)
        except PermissionError:
            pass


def test_list_papers_tier_filter():
    """Passing tiers={...} restricts the result set; legacy rows count as solid."""
    import sqlite3

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = PaperDatabase(db_path)
        db.cache_papers(
            [
                _make_scored_paper_full("brk", impact_tier="breakthrough"),
                _make_scored_paper_full("sol", impact_tier="solid"),
                _make_scored_paper_full("inc", impact_tier="incremental"),
            ]
        )
        # Inject a legacy row whose impact_tier column is NULL (mimicking a
        # paper scored before this change shipped).
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """
                INSERT INTO papers (arxiv_id, title, authors, abstract, published,
                  categories, pdf_url, abs_url, relevance_score, quality_score,
                  summary_zh, sub_domain_tags, scored_at)
                VALUES ('legacy', 't', 'A', 'abs', ?, 'cs.DC', 'p', 'a',
                        9.0, 9.0, 'sum', '[]', ?)
                """,
                ("2024-01-01T00:00:00", "2024-01-02T00:00:00"),
            )
            conn.commit()
        finally:
            conn.close()

        only_breakthrough = {
            p.paper.arxiv_id for p in db.list_papers(tiers={"breakthrough"}, limit=10)
        }
        assert only_breakthrough == {"brk"}

        # Legacy NULL row appears under the 'solid' filter.
        solid_set = {p.paper.arxiv_id for p in db.list_papers(tiers={"solid"}, limit=10)}
        assert "sol" in solid_set
        assert "legacy" in solid_set
        assert "brk" not in solid_set
        assert "inc" not in solid_set

        # Combined OR filter
        combined = {
            p.paper.arxiv_id for p in db.list_papers(tiers={"breakthrough", "solid"}, limit=10)
        }
        assert combined == {"brk", "sol", "legacy"}

        # Count matches filtered set
        assert db.count_papers(tiers={"breakthrough"}) == 1
        assert db.count_papers(tiers={"breakthrough", "solid"}) == 3
    finally:
        try:
            os.unlink(db_path)
        except PermissionError:
            pass


def test_list_papers_unknown_tier_filter_value_is_ignored():
    """Unknown tier strings are dropped from the IN clause."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = PaperDatabase(db_path)
        db.cache_papers([_make_scored_paper_full("a", impact_tier="solid")])
        # Only unknown values → behaves as no filter (returns the one paper).
        results = db.list_papers(tiers={"legendary"}, limit=10)
        assert [p.paper.arxiv_id for p in results] == ["a"]
        # Mixed known + unknown → keeps the known.
        results = db.list_papers(tiers={"legendary", "solid"}, limit=10)
        assert [p.paper.arxiv_id for p in results] == ["a"]
    finally:
        try:
            os.unlink(db_path)
        except PermissionError:
            pass


# ─── Backfill query helpers (rescore --missing-fields) ───


def test_count_papers_missing_insights_returns_only_legacy_rows():
    """Modern rows (full insights) don't count; NULL impact_tier rows do."""
    import sqlite3

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = PaperDatabase(db_path)
        db.cache_papers([_make_scored_paper_full("modern", impact_tier="solid")])
        # Inject two legacy rows with NULL columns
        conn = sqlite3.connect(db_path)
        try:
            for aid in ("legacy-1", "legacy-2"):
                conn.execute(
                    """
                    INSERT INTO papers (arxiv_id, title, authors, abstract, published,
                      categories, pdf_url, abs_url, relevance_score, quality_score,
                      summary_zh, sub_domain_tags, scored_at)
                    VALUES (?, 't', 'A', 'abs', '2024-01-01', 'cs.DC', 'p', 'a',
                            8.0, 7.0, 'sum', '[]', '2024-01-02')
                    """,
                    (aid,),
                )
            conn.commit()
        finally:
            conn.close()

        assert db.count_papers_missing_insights() == 2
    finally:
        try:
            os.unlink(db_path)
        except PermissionError:
            pass


def test_get_papers_missing_insights_skips_modern_rows():
    """get_papers_missing_insights returns only rows with NULL columns."""
    import sqlite3

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = PaperDatabase(db_path)
        db.cache_papers([_make_scored_paper_full("modern", impact_tier="solid")])
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """
                INSERT INTO papers (arxiv_id, title, authors, abstract, published,
                  categories, pdf_url, abs_url, relevance_score, quality_score,
                  summary_zh, sub_domain_tags, scored_at)
                VALUES ('legacy', 't', 'A', 'abs', '2024-01-01', 'cs.DC', 'p', 'a',
                        8.0, 7.0, 'sum', '[]', '2024-01-02')
                """
            )
            conn.commit()
        finally:
            conn.close()

        results = db.get_papers_missing_insights(limit=10)
        ids = {sp.paper.arxiv_id for sp in results}
        assert ids == {"legacy"}
        # The "modern" row has impact_tier=solid and key_contributions=[] (not NULL),
        # so it should be excluded.
    finally:
        try:
            os.unlink(db_path)
        except PermissionError:
            pass


def test_backfill_pagination_resumable():
    """Limit + offset let the caller resume after partial processing."""
    import sqlite3

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        db = PaperDatabase(db_path)
        conn = sqlite3.connect(db_path)
        try:
            for i in range(5):
                conn.execute(
                    """
                    INSERT INTO papers (arxiv_id, title, authors, abstract, published,
                      categories, pdf_url, abs_url, relevance_score, quality_score,
                      summary_zh, sub_domain_tags, scored_at)
                    VALUES (?, 't', 'A', 'abs', '2024-01-01', 'cs.DC', 'p', 'a',
                            8.0, 7.0, 'sum', '[]', '2024-01-02')
                    """,
                    (f"legacy-{i}",),
                )
            conn.commit()
        finally:
            conn.close()

        assert db.count_papers_missing_insights() == 5
        # First batch of 2
        batch1 = db.get_papers_missing_insights(limit=2, offset=0)
        assert len(batch1) == 2
        # Second batch starting from offset 2
        batch2 = db.get_papers_missing_insights(limit=2, offset=2)
        assert len(batch2) == 2
        # No overlap
        ids1 = {sp.paper.arxiv_id for sp in batch1}
        ids2 = {sp.paper.arxiv_id for sp in batch2}
        assert ids1.isdisjoint(ids2)
    finally:
        try:
            os.unlink(db_path)
        except PermissionError:
            pass
