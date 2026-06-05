"""Tests for the multi-user pipeline."""

import os
import tempfile
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from paper_agent.config import (
    AppConfig,
    FetchConfig,
    PromptsConfig,
    ScheduleConfig,
    ScoringConfig,
    StorageConfig,
    SubscriptionConfig,
    UserConfig,
    UserThresholdsConfig,
)
from paper_agent.models import Paper, ScoredPaper, ScoreWeights
from paper_agent.pipeline import Pipeline


def _make_paper(arxiv_id: str = "2401.00001v1") -> Paper:
    return Paper(
        arxiv_id=arxiv_id,
        title=f"Test Paper {arxiv_id}",
        authors=["Alice", "Bob"],
        abstract="Test abstract about quantization and pruning.",
        published=datetime(2024, 1, 15, tzinfo=UTC),
        categories=["cs.DC", "cs.LG"],
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        abs_url=f"https://arxiv.org/abs/{arxiv_id}",
    )


def _make_scored_paper(
    arxiv_id: str = "2401.00001v1",
    relevance: float = 8.0,
    quality: float = 7.0,
    tags: tuple = ("quantization",),
) -> ScoredPaper:
    return ScoredPaper(
        paper=_make_paper(arxiv_id),
        relevance_score=relevance,
        quality_score=quality,
        summary_zh="测试论文",
        sub_domain_tags=tags,
    )


def _make_config(users: list[UserConfig]) -> AppConfig:
    return AppConfig(
        fetch=FetchConfig(max_results=10, days_back=3),
        scoring=ScoringConfig(batch_size=5),
        users=users,
        schedule=ScheduleConfig(enabled=False),
        storage=StorageConfig(db_path=":memory:"),
    )


@patch("paper_agent.pipeline.ArxivFetcher")
@patch("paper_agent.pipeline.ClaudeScorer")
def test_pipeline_multi_user_filter(mock_scorer_cls, mock_fetcher_cls):
    """Different users get different papers based on sub-domain subscriptions."""
    # Setup mocks
    mock_fetcher = MagicMock()
    mock_fetcher.fetch.return_value = [
        _make_paper("001"),
        _make_paper("002"),
        _make_paper("003"),
    ]
    mock_fetcher_cls.return_value = mock_fetcher

    mock_scorer = MagicMock()
    mock_scorer.score.return_value = [
        _make_scored_paper("001", tags=("quantization",)),
        _make_scored_paper("002", tags=("distillation",)),
        _make_scored_paper("003", tags=("quantization", "sparsity")),
    ]
    mock_scorer_cls.return_value = mock_scorer

    users = [
        UserConfig(
            user_id="alice",
            subscriptions=SubscriptionConfig(sub_domains=["quantization"]),
            thresholds=UserThresholdsConfig(min_relevance=6.0, min_quality=5.0, top_n=10),
        ),
        UserConfig(
            user_id="bob",
            subscriptions=SubscriptionConfig(sub_domains=["distillation"]),
            thresholds=UserThresholdsConfig(min_relevance=6.0, min_quality=5.0, top_n=10),
        ),
    ]

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        config = AppConfig(
            fetch=FetchConfig(max_results=10, days_back=3),
            scoring=ScoringConfig(batch_size=5),
            users=users,
            schedule=ScheduleConfig(enabled=False),
            storage=StorageConfig(db_path=db_path),
        )

        pipeline = Pipeline(config)
        results = pipeline.run(dry_run=True)

        # Alice should get papers 001 and 003 (quantization)
        assert "alice" in results
        alice_ids = {sp.paper.arxiv_id for sp in results["alice"]}
        assert alice_ids == {"001", "003"}

        # Bob should get paper 002 (distillation)
        assert "bob" in results
        bob_ids = {sp.paper.arxiv_id for sp in results["bob"]}
        assert bob_ids == {"002"}
    finally:
        os.unlink(db_path)


@patch("paper_agent.pipeline.ArxivFetcher")
@patch("paper_agent.pipeline.ClaudeScorer")
def test_pipeline_all_subscription(mock_scorer_cls, mock_fetcher_cls):
    """User with 'all' subscription gets all papers that pass thresholds."""
    mock_fetcher = MagicMock()
    mock_fetcher.fetch.return_value = [_make_paper("001"), _make_paper("002")]
    mock_fetcher_cls.return_value = mock_fetcher

    mock_scorer = MagicMock()
    mock_scorer.score.return_value = [
        _make_scored_paper("001", tags=("quantization",)),
        _make_scored_paper("002", tags=("distillation",)),
    ]
    mock_scorer_cls.return_value = mock_scorer

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        config = AppConfig(
            fetch=FetchConfig(max_results=10, days_back=3),
            scoring=ScoringConfig(batch_size=5),
            users=[
                UserConfig(
                    user_id="team",
                    subscriptions=SubscriptionConfig(sub_domains=["all"]),
                    thresholds=UserThresholdsConfig(min_relevance=6.0, min_quality=5.0, top_n=10),
                ),
            ],
            schedule=ScheduleConfig(enabled=False),
            storage=StorageConfig(db_path=db_path),
        )

        pipeline = Pipeline(config)
        results = pipeline.run(dry_run=True)

        # Team should get both papers
        assert len(results["team"]) == 2
    finally:
        os.unlink(db_path)


@patch("paper_agent.pipeline.ArxivFetcher")
@patch("paper_agent.pipeline.ClaudeScorer")
def test_pipeline_threshold_filter(mock_scorer_cls, mock_fetcher_cls):
    """Per-user thresholds filter out low-scoring papers."""
    mock_fetcher = MagicMock()
    mock_fetcher.fetch.return_value = [_make_paper("001"), _make_paper("002")]
    mock_fetcher_cls.return_value = mock_fetcher

    mock_scorer = MagicMock()
    mock_scorer.score.return_value = [
        _make_scored_paper("001", relevance=9.0, quality=8.0, tags=("quantization",)),
        _make_scored_paper("002", relevance=5.0, quality=4.0, tags=("quantization",)),
    ]
    mock_scorer_cls.return_value = mock_scorer

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        config = AppConfig(
            fetch=FetchConfig(max_results=10, days_back=3),
            scoring=ScoringConfig(batch_size=5),
            users=[
                UserConfig(
                    user_id="picky",
                    subscriptions=SubscriptionConfig(sub_domains=["quantization"]),
                    thresholds=UserThresholdsConfig(min_relevance=7.0, min_quality=6.0, top_n=10),
                ),
            ],
            schedule=ScheduleConfig(enabled=False),
            storage=StorageConfig(db_path=db_path),
        )

        pipeline = Pipeline(config)
        results = pipeline.run(dry_run=True)

        # Only paper 001 passes the thresholds
        assert len(results["picky"]) == 1
        assert results["picky"][0].paper.arxiv_id == "001"
    finally:
        os.unlink(db_path)


@patch("paper_agent.pipeline.ArxivFetcher")
@patch("paper_agent.pipeline.ClaudeScorer")
def test_pipeline_run_specific_user(mock_scorer_cls, mock_fetcher_cls):
    """user_ids parameter restricts pipeline to specified users."""
    mock_fetcher = MagicMock()
    mock_fetcher.fetch.return_value = [_make_paper("001")]
    mock_fetcher_cls.return_value = mock_fetcher

    mock_scorer = MagicMock()
    mock_scorer.score.return_value = [
        _make_scored_paper("001", tags=("quantization",)),
    ]
    mock_scorer_cls.return_value = mock_scorer

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        config = AppConfig(
            fetch=FetchConfig(max_results=10, days_back=3),
            scoring=ScoringConfig(batch_size=5),
            users=[
                UserConfig(
                    user_id="alice",
                    subscriptions=SubscriptionConfig(sub_domains=["quantization"]),
                ),
                UserConfig(
                    user_id="bob",
                    subscriptions=SubscriptionConfig(sub_domains=["quantization"]),
                ),
            ],
            schedule=ScheduleConfig(enabled=False),
            storage=StorageConfig(db_path=db_path),
        )

        pipeline = Pipeline(config)
        results = pipeline.run(dry_run=True, user_ids=["alice"])

        # Only alice should be in results
        assert "alice" in results
        assert "bob" not in results
    finally:
        os.unlink(db_path)


def test_superset_keywords():
    """Pipeline builds superset of keywords from all users' subscriptions."""
    config = AppConfig(
        fetch=FetchConfig(keywords=["base_keyword"]),
        scoring=ScoringConfig(),
        users=[
            UserConfig(
                user_id="alice",
                subscriptions=SubscriptionConfig(sub_domains=["quantization"]),
            ),
            UserConfig(
                user_id="bob",
                subscriptions=SubscriptionConfig(sub_domains=["distillation"]),
            ),
        ],
    )

    pipeline = Pipeline.__new__(Pipeline)
    keywords = pipeline._build_superset_keywords(config)

    # Should include base keyword + sub-domain names (not all sub-domain keywords)
    assert "base_keyword" in keywords
    assert "quantization" in keywords  # sub-domain name
    assert "distillation" in keywords  # sub-domain name


@patch("paper_agent.pipeline.ArxivFetcher")
@patch("paper_agent.pipeline.ClaudeScorer")
def test_pipeline_uses_cache(mock_scorer_cls, mock_fetcher_cls):
    """Already-cached papers are not re-scored."""
    mock_fetcher = MagicMock()
    mock_fetcher.fetch.return_value = [_make_paper("001"), _make_paper("002")]
    mock_fetcher_cls.return_value = mock_fetcher

    mock_scorer = MagicMock()
    # Only returns the new paper (002)
    mock_scorer.score.return_value = [
        _make_scored_paper("002", tags=("quantization",)),
    ]
    mock_scorer_cls.return_value = mock_scorer

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        config = AppConfig(
            fetch=FetchConfig(max_results=10, days_back=3),
            scoring=ScoringConfig(batch_size=5),
            users=[
                UserConfig(
                    user_id="alice",
                    subscriptions=SubscriptionConfig(sub_domains=["all"]),
                ),
            ],
            schedule=ScheduleConfig(enabled=False),
            storage=StorageConfig(db_path=db_path),
        )

        pipeline = Pipeline(config)

        # Pre-cache paper 001
        from paper_agent.storage.database import PaperDatabase

        db = PaperDatabase(db_path)
        db.cache_papers([_make_scored_paper("001", tags=("distillation",))])

        results = pipeline.run(dry_run=True)

        # Scorer should only be called with the new paper
        mock_scorer.score.assert_called_once()
        scored_arg = mock_scorer.score.call_args[0][0]
        assert len(scored_arg) == 1
        assert scored_arg[0].arxiv_id == "002"

        # Results should include both papers (001 from cache + 002 newly scored)
        assert len(results["alice"]) == 2
    finally:
        os.unlink(db_path)


@patch("paper_agent.pipeline.ArxivFetcher")
@patch("paper_agent.pipeline.ClaudeScorer")
def test_pipeline_custom_score_weights(mock_scorer_cls, mock_fetcher_cls):
    """Pipeline sorts results using configured relevance/quality weights."""
    mock_fetcher = MagicMock()
    mock_fetcher.fetch.return_value = [_make_paper("001"), _make_paper("002")]
    mock_fetcher_cls.return_value = mock_fetcher

    mock_scorer = MagicMock()
    # Paper 001: high relevance, low quality
    # Paper 002: low relevance, high quality
    mock_scorer.score.return_value = [
        _make_scored_paper("001", relevance=10.0, quality=2.0, tags=("quantization",)),
        _make_scored_paper("002", relevance=2.0, quality=10.0, tags=("quantization",)),
    ]
    mock_scorer_cls.return_value = mock_scorer

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        # Quality-weighted: paper 002 wins (2*0.1 + 10*0.9 = 9.2 vs 10*0.1 + 2*0.9 = 2.8)
        config = AppConfig(
            fetch=FetchConfig(max_results=10, days_back=3),
            scoring=ScoringConfig(
                batch_size=5,
                relevance_weight=0.1,
                quality_weight=0.9,
            ),
            users=[
                UserConfig(
                    user_id="alice",
                    subscriptions=SubscriptionConfig(sub_domains=["quantization"]),
                    thresholds=UserThresholdsConfig(min_relevance=0.0, min_quality=0.0, top_n=10),
                ),
            ],
            schedule=ScheduleConfig(enabled=False),
            storage=StorageConfig(db_path=db_path),
        )

        pipeline = Pipeline(config)
        assert pipeline.score_weights == ScoreWeights(0.1, 0.9)

        results = pipeline.run(dry_run=True)
        # Paper 002 should come first under quality-weighted sorting
        assert results["alice"][0].paper.arxiv_id == "002"
        assert results["alice"][1].paper.arxiv_id == "001"
    finally:
        os.unlink(db_path)


@patch("paper_agent.pipeline.ClaudeScorer")
def test_pipeline_passes_scoring_config_to_scorer(mock_scorer_cls):
    """Pipeline passes the full ScoringConfig to ClaudeScorer."""
    mock_scorer_cls.return_value = MagicMock()

    scoring = ScoringConfig(
        model="claude-sonnet-4-5",
        api_key="sk-test",
        base_url="https://proxy.example.com",
        max_tokens=2048,
        prompts=PromptsConfig(system_prompt="Custom"),
    )
    config = AppConfig(
        fetch=FetchConfig(max_results=10, days_back=3),
        scoring=scoring,
        users=[
            UserConfig(
                user_id="alice",
                subscriptions=SubscriptionConfig(sub_domains=["quantization"]),
            ),
        ],
        schedule=ScheduleConfig(enabled=False),
        storage=StorageConfig(db_path=":memory:"),
    )

    Pipeline(config)
    mock_scorer_cls.assert_called_once_with(config=scoring)


@patch("paper_agent.pipeline.ArxivFetcher")
@patch("paper_agent.pipeline.ClaudeScorer")
def test_pipeline_cached_digest_uses_cache_without_fetching(mock_scorer_cls, mock_fetcher_cls):
    """Initial subscription digest uses cached papers instead of arXiv/LLM."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        config = AppConfig(
            fetch=FetchConfig(max_results=10, days_back=3),
            scoring=ScoringConfig(batch_size=5),
            users=[
                UserConfig(
                    user_id="alice",
                    subscriptions=SubscriptionConfig(sub_domains=["quantization"]),
                    thresholds=UserThresholdsConfig(
                        min_relevance=6.0,
                        min_quality=5.0,
                        top_n=10,
                    ),
                )
            ],
            schedule=ScheduleConfig(enabled=False),
            storage=StorageConfig(db_path=db_path),
        )
        pipeline = Pipeline(config)
        pipeline.db.cache_papers([
            _make_scored_paper("001", tags=("quantization",)),
            _make_scored_paper("002", tags=("moe",)),
        ])

        results = pipeline.run_cached_for_user("alice", dry_run=True)

        assert [sp.paper.arxiv_id for sp in results["alice"]] == ["001"]
        mock_fetcher_cls.return_value.fetch.assert_not_called()
        mock_scorer_cls.return_value.score.assert_not_called()
    finally:
        os.unlink(db_path)


@patch("paper_agent.pipeline.ArxivFetcher")
@patch("paper_agent.pipeline.ClaudeScorer")
def test_pipeline_ingest_caches_without_notifying(mock_scorer_cls, mock_fetcher_cls):
    """Ingest fetches/scores/caches but does not mark papers as sent."""
    mock_fetcher = MagicMock()
    mock_fetcher.fetch.return_value = [_make_paper("001")]
    mock_fetcher_cls.return_value = mock_fetcher

    mock_scorer = MagicMock()
    mock_scorer.score.return_value = [_make_scored_paper("001", tags=("quantization",))]
    mock_scorer_cls.return_value = mock_scorer

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        config = AppConfig(
            fetch=FetchConfig(max_results=10, days_back=3),
            scoring=ScoringConfig(batch_size=5),
            users=[UserConfig(user_id="alice")],
            schedule=ScheduleConfig(enabled=False),
            storage=StorageConfig(db_path=db_path),
        )
        pipeline = Pipeline(config)
        scored = pipeline.ingest()

        assert [sp.paper.arxiv_id for sp in scored] == ["001"]
        assert pipeline.db.is_cached("001")
        assert pipeline.db.get_stats(user_id="alice")["total_sent"] == 0
    finally:
        os.unlink(db_path)


@patch("paper_agent.pipeline.ArxivFetcher")
@patch("paper_agent.pipeline.ClaudeScorer")
def test_pipeline_cached_digest_uses_cache_for_all_users(mock_scorer_cls, mock_fetcher_cls):
    """Scheduled digest sends from cache without fetching arXiv."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        config = AppConfig(
            fetch=FetchConfig(max_results=10, days_back=3),
            scoring=ScoringConfig(batch_size=5),
            users=[
                UserConfig(
                    user_id="alice",
                    subscriptions=SubscriptionConfig(sub_domains=["quantization"]),
                    thresholds=UserThresholdsConfig(
                        min_relevance=6.0,
                        min_quality=5.0,
                        top_n=10,
                    ),
                )
            ],
            schedule=ScheduleConfig(enabled=False),
            storage=StorageConfig(db_path=db_path),
        )
        pipeline = Pipeline(config)
        pipeline.db.cache_papers([
            _make_scored_paper("001", tags=("quantization",)),
            _make_scored_paper("002", tags=("moe",)),
        ])

        results = pipeline.run_cached_digest(dry_run=True)

        assert [sp.paper.arxiv_id for sp in results["alice"]] == ["001"]
        mock_fetcher_cls.return_value.fetch.assert_not_called()
        mock_scorer_cls.return_value.score.assert_not_called()
    finally:
        os.unlink(db_path)
