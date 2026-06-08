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
        pipeline.db.cache_papers(
            [
                _make_scored_paper("001", tags=("quantization",)),
                _make_scored_paper("002", tags=("moe",)),
            ]
        )

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
        pipeline.db.cache_papers(
            [
                _make_scored_paper("001", tags=("quantization",)),
                _make_scored_paper("002", tags=("moe",)),
            ]
        )

        results = pipeline.run_cached_digest(dry_run=True)

        assert [sp.paper.arxiv_id for sp in results["alice"]] == ["001"]
        mock_fetcher_cls.return_value.fetch.assert_not_called()
        mock_scorer_cls.return_value.score.assert_not_called()
    finally:
        os.unlink(db_path)


@patch("paper_agent.pipeline.ArxivFetcher")
@patch("paper_agent.pipeline.ClaudeScorer")
def test_per_sub_domain_top_n_split_and_dedup(mock_scorer_cls, mock_fetcher_cls):
    """Per-domain top-N: 30 quant + 25 distil + 5 dual-tag, per_sub_domain_top_n=10 → ≤20 unique."""
    mock_fetcher_cls.return_value.fetch.return_value = []

    scored = []
    # 30 quant-only papers, scores 9.0 → 6.1 (descending)
    for i in range(30):
        scored.append(
            _make_scored_paper(
                f"q{i:03d}", relevance=9.0 - i * 0.1, quality=7.0, tags=("quantization",)
            )
        )
    # 25 distil-only papers
    for i in range(25):
        scored.append(
            _make_scored_paper(
                f"d{i:03d}", relevance=9.0 - i * 0.1, quality=7.0, tags=("distillation",)
            )
        )
    # 5 dual-tag papers (both quant and distil)
    for i in range(5):
        scored.append(
            _make_scored_paper(
                f"dual{i}",
                relevance=8.5,
                quality=7.5,
                tags=("quantization", "distillation"),
            )
        )
    mock_scorer_cls.return_value.score.return_value = scored
    mock_fetcher_cls.return_value.fetch.return_value = [sp.paper for sp in scored]

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        config = AppConfig(
            fetch=FetchConfig(max_results=100, days_back=3),
            scoring=ScoringConfig(batch_size=5),
            users=[
                UserConfig(
                    user_id="alice",
                    subscriptions=SubscriptionConfig(sub_domains=["quantization", "distillation"]),
                    thresholds=UserThresholdsConfig(
                        min_relevance=6.0,
                        min_quality=5.0,
                        top_n=200,
                        per_sub_domain_top_n=10,
                    ),
                )
            ],
            schedule=ScheduleConfig(enabled=False),
            storage=StorageConfig(db_path=db_path),
        )
        results = Pipeline(config).run(dry_run=True)
        alice_ids = [sp.paper.arxiv_id for sp in results["alice"]]
        # Each bucket takes top 10 (10 quant + 10 distil = 20 entries before dedup).
        # Dual-tag papers (score 8.5) rank inside top 10 of both buckets → counted twice
        # in raw merge but deduped to one. Final count ≤ 20.
        assert len(alice_ids) <= 20
        # No duplicates after dedup
        assert len(alice_ids) == len(set(alice_ids))
    finally:
        os.unlink(db_path)


@patch("paper_agent.pipeline.ArxivFetcher")
@patch("paper_agent.pipeline.ClaudeScorer")
def test_per_sub_domain_respects_overall_cap(mock_scorer_cls, mock_fetcher_cls):
    """top_n caps the dedup'd union even when per-domain buckets sum higher."""
    sub_domains = [
        "quantization",
        "distillation",
        "pruning",
        "sparsity",
        "serving",
        "kv_cache",
        "moe",
        "compiler",
        "scheduling",
        "parallelism",
    ]
    scored = []
    for tag in sub_domains:
        for i in range(5):
            scored.append(_make_scored_paper(f"{tag}{i}", relevance=8.0, quality=7.0, tags=(tag,)))
    mock_scorer_cls.return_value.score.return_value = scored
    mock_fetcher_cls.return_value.fetch.return_value = [sp.paper for sp in scored]

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        config = AppConfig(
            fetch=FetchConfig(max_results=100, days_back=3),
            scoring=ScoringConfig(batch_size=5),
            users=[
                UserConfig(
                    user_id="alice",
                    subscriptions=SubscriptionConfig(sub_domains=sub_domains),
                    thresholds=UserThresholdsConfig(
                        min_relevance=6.0,
                        min_quality=5.0,
                        top_n=15,
                        per_sub_domain_top_n=20,
                    ),
                )
            ],
            schedule=ScheduleConfig(enabled=False),
            storage=StorageConfig(db_path=db_path),
        )
        results = Pipeline(config).run(dry_run=True)
        # 10 domains × 5 papers each = 50 candidates after per-domain take 20.
        # top_n=15 caps the merged result to 15.
        assert len(results["alice"]) == 15
    finally:
        os.unlink(db_path)


@patch("paper_agent.pipeline.ArxivFetcher")
@patch("paper_agent.pipeline.ClaudeScorer")
def test_all_subscription_ignores_per_domain_limit(mock_scorer_cls, mock_fetcher_cls):
    """Users subscribed to 'all' skip per-domain bucketing, get top_n directly."""
    scored = [
        _make_scored_paper(
            f"p{i:03d}", relevance=9.0 - i * 0.05, quality=7.0, tags=("quantization",)
        )
        for i in range(30)
    ]
    mock_scorer_cls.return_value.score.return_value = scored
    mock_fetcher_cls.return_value.fetch.return_value = [sp.paper for sp in scored]

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        config = AppConfig(
            fetch=FetchConfig(max_results=100, days_back=3),
            scoring=ScoringConfig(batch_size=5),
            users=[
                UserConfig(
                    user_id="team",
                    subscriptions=SubscriptionConfig(sub_domains=["all"]),
                    thresholds=UserThresholdsConfig(
                        min_relevance=6.0,
                        min_quality=5.0,
                        top_n=12,
                        per_sub_domain_top_n=3,  # would only give 3 if buckets applied
                    ),
                )
            ],
            schedule=ScheduleConfig(enabled=False),
            storage=StorageConfig(db_path=db_path),
        )
        results = Pipeline(config).run(dry_run=True)
        # "all" bypasses per-domain; should get top_n=12 (not 3 from per_sub_domain_top_n)
        assert len(results["team"]) == 12
    finally:
        os.unlink(db_path)


# ─── min_tier filtering ───


def _make_tiered_paper(
    arxiv_id: str,
    impact_tier: str = "solid",
    tags: tuple = ("quantization",),
    relevance: float = 8.0,
    quality: float = 7.0,
) -> ScoredPaper:
    return ScoredPaper(
        paper=_make_paper(arxiv_id),
        relevance_score=relevance,
        quality_score=quality,
        summary_zh="测试",
        sub_domain_tags=tags,
        impact_tier=impact_tier,
    )


@patch("paper_agent.pipeline.ArxivFetcher")
@patch("paper_agent.pipeline.ClaudeScorer")
def test_pipeline_min_tier_breakthrough_only(mock_scorer_cls, mock_fetcher_cls):
    """User with min_tier='breakthrough' receives only breakthrough papers."""
    mock_fetcher = MagicMock()
    mock_fetcher.fetch.return_value = [_make_paper(f"{i:03d}") for i in range(3)]
    mock_fetcher_cls.return_value = mock_fetcher

    mock_scorer = MagicMock()
    mock_scorer.score.return_value = [
        _make_tiered_paper("000", impact_tier="breakthrough"),
        _make_tiered_paper("001", impact_tier="solid"),
        _make_tiered_paper("002", impact_tier="incremental"),
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
                    thresholds=UserThresholdsConfig(
                        min_relevance=6.0,
                        min_quality=5.0,
                        top_n=10,
                        min_tier="breakthrough",
                    ),
                ),
            ],
            schedule=ScheduleConfig(enabled=False),
            storage=StorageConfig(db_path=db_path),
        )
        results = Pipeline(config).run(dry_run=True)
        assert {sp.paper.arxiv_id for sp in results["picky"]} == {"000"}
    finally:
        os.unlink(db_path)


@patch("paper_agent.pipeline.ArxivFetcher")
@patch("paper_agent.pipeline.ClaudeScorer")
def test_pipeline_default_min_tier_excludes_incremental(mock_scorer_cls, mock_fetcher_cls):
    """Default min_tier='solid' excludes incremental papers."""
    mock_fetcher = MagicMock()
    mock_fetcher.fetch.return_value = [_make_paper(f"{i:03d}") for i in range(3)]
    mock_fetcher_cls.return_value = mock_fetcher

    mock_scorer = MagicMock()
    mock_scorer.score.return_value = [
        _make_tiered_paper("000", impact_tier="breakthrough"),
        _make_tiered_paper("001", impact_tier="solid"),
        _make_tiered_paper("002", impact_tier="incremental"),
    ]
    mock_scorer_cls.return_value = mock_scorer

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        # No min_tier set → defaults to "solid"
        config = AppConfig(
            fetch=FetchConfig(max_results=10, days_back=3),
            scoring=ScoringConfig(batch_size=5),
            users=[
                UserConfig(
                    user_id="default-user",
                    subscriptions=SubscriptionConfig(sub_domains=["quantization"]),
                    thresholds=UserThresholdsConfig(top_n=10),
                ),
            ],
            schedule=ScheduleConfig(enabled=False),
            storage=StorageConfig(db_path=db_path),
        )
        results = Pipeline(config).run(dry_run=True)
        ids = {sp.paper.arxiv_id for sp in results["default-user"]}
        assert ids == {"000", "001"}
        assert "002" not in ids  # incremental excluded
    finally:
        os.unlink(db_path)


@patch("paper_agent.pipeline.ArxivFetcher")
@patch("paper_agent.pipeline.ClaudeScorer")
def test_pipeline_min_tier_incremental_includes_all(mock_scorer_cls, mock_fetcher_cls):
    """User with min_tier='incremental' gets every tier."""
    mock_fetcher = MagicMock()
    mock_fetcher.fetch.return_value = [_make_paper(f"{i:03d}") for i in range(3)]
    mock_fetcher_cls.return_value = mock_fetcher

    mock_scorer = MagicMock()
    mock_scorer.score.return_value = [
        _make_tiered_paper("000", impact_tier="breakthrough"),
        _make_tiered_paper("001", impact_tier="solid"),
        _make_tiered_paper("002", impact_tier="incremental"),
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
                    user_id="completionist",
                    subscriptions=SubscriptionConfig(sub_domains=["quantization"]),
                    thresholds=UserThresholdsConfig(top_n=10, min_tier="incremental"),
                ),
            ],
            schedule=ScheduleConfig(enabled=False),
            storage=StorageConfig(db_path=db_path),
        )
        results = Pipeline(config).run(dry_run=True)
        assert {sp.paper.arxiv_id for sp in results["completionist"]} == {"000", "001", "002"}
    finally:
        os.unlink(db_path)


@patch("paper_agent.pipeline.ArxivFetcher")
@patch("paper_agent.pipeline.ClaudeScorer")
def test_pipeline_min_tier_sort_order_is_tier_first(mock_scorer_cls, mock_fetcher_cls):
    """Within a user's digest, breakthrough sorts before higher-scoring solid."""
    mock_fetcher = MagicMock()
    mock_fetcher.fetch.return_value = [_make_paper(f"{i:03d}") for i in range(2)]
    mock_fetcher_cls.return_value = mock_fetcher

    mock_scorer = MagicMock()
    mock_scorer.score.return_value = [
        # solid paper with a higher score
        _make_tiered_paper("001", impact_tier="solid", relevance=9.5, quality=9.5),
        # breakthrough paper with a lower score
        _make_tiered_paper("000", impact_tier="breakthrough", relevance=6.0, quality=6.0),
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
                    user_id="reader",
                    subscriptions=SubscriptionConfig(sub_domains=["quantization"]),
                    thresholds=UserThresholdsConfig(top_n=10, min_tier="solid"),
                ),
            ],
            schedule=ScheduleConfig(enabled=False),
            storage=StorageConfig(db_path=db_path),
        )
        results = Pipeline(config).run(dry_run=True)
        ordered_ids = [sp.paper.arxiv_id for sp in results["reader"]]
        # breakthrough first, despite lower raw score
        assert ordered_ids[0] == "000"
        assert ordered_ids[1] == "001"
    finally:
        os.unlink(db_path)
