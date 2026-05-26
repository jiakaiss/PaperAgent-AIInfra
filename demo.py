"""Demo script to test pipeline with mock data (bypass arXiv rate limiting)."""

import logging
from datetime import datetime, timezone

from paper_agent.config import load_config
from paper_agent.models import Paper, ScoredPaper
from paper_agent.scorer.claude_scorer import ClaudeScorer
from paper_agent.storage.database import PaperDatabase
from paper_agent.notifier import create_notifiers_for_user
from paper_agent.formatter.templates import format_markdown

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_mock_papers() -> list[Paper]:
    """Create sample papers for testing."""
    return [
        Paper(
            arxiv_id="2401.12345v1",
            title="Efficient INT4 Quantization for Large Language Models with Outlier-Aware Dynamic Calibration",
            authors=["Wei Zhang", "Li Chen", "Hao Wang"],
            abstract="We propose a novel INT4 quantization method that dynamically calibrates weight ranges "
                     "while handling outliers, achieving less than 1% perplexity degradation on LLaMA-70B "
                     "compared to FP16 baseline. Our method reduces memory footprint by 75% and enables "
                     "deployment on consumer GPUs without fine-tuning.",
            published=datetime(2024, 1, 20, tzinfo=timezone.utc),
            categories=["cs.LG", "cs.DC"],
            pdf_url="https://arxiv.org/pdf/2401.12345v1",
            abs_url="https://arxiv.org/abs/2401.12345v1",
        ),
        Paper(
            arxiv_id="2401.12346v1",
            title="SparseMoE: Accelerating Mixture-of-Experts with 2:4 Structured Sparsity",
            authors=["Sarah Johnson", "Michael Brown"],
            abstract="We introduce SparseMoE, a framework that applies 2:4 structured sparsity to MoE models, "
                     "achieving 2.3x speedup on A100 GPUs while maintaining 99.2% accuracy. Our approach "
                     "leverages NVIDIA sparse tensor cores and expert routing optimization.",
            published=datetime(2024, 1, 19, tzinfo=timezone.utc),
            categories=["cs.DC", "cs.LG"],
            pdf_url="https://arxiv.org/pdf/2401.12346v1",
            abs_url="https://arxiv.org/abs/2401.12346v1",
        ),
        Paper(
            arxiv_id="2401.12347v1",
            title="Knowledge Distillation for Code Generation Models: A Comprehensive Study",
            authors=["Alice Chen", "Bob Smith", "Charlie Wang"],
            abstract="We present a systematic study of knowledge distillation techniques for code generation "
                     "models. Our distilled CodeT5-770M model achieves 95% of CodeGen-16B performance with "
                     "20x fewer parameters, enabling efficient deployment on edge devices.",
            published=datetime(2024, 1, 18, tzinfo=timezone.utc),
            categories=["cs.LG", "cs.SE"],
            pdf_url="https://arxiv.org/pdf/2401.12347v1",
            abs_url="https://arxiv.org/abs/2401.12347v1",
        ),
        Paper(
            arxiv_id="2401.12348v1",
            title="PagedAttention Meets Speculative Decoding: 3x Faster LLM Inference",
            authors=["David Lee", "Emma Wilson"],
            abstract="We combine PagedAttention with speculative decoding to achieve 3.1x throughput improvement "
                     "for LLaMA-2-70B serving. Our system reduces KV cache memory fragmentation while "
                     "leveraging draft models for parallel token verification.",
            published=datetime(2024, 1, 17, tzinfo=timezone.utc),
            categories=["cs.DC", "cs.CL"],
            pdf_url="https://arxiv.org/pdf/2401.12348v1",
            abs_url="https://arxiv.org/abs/2401.12348v1",
        ),
        Paper(
            arxiv_id="2401.12349v1",
            title="FlashAttention-3: 5x Faster Attention with Asynchronous Low-Precision Arithmetic",
            authors=["Tri Dao", "James Park"],
            abstract="FlashAttention-3 exploits asynchronous low-precision arithmetic on H100 GPUs to achieve "
                     "5x speedup over FlashAttention-2. We introduce novel techniques for handling numerical "
                     "instability while maintaining model accuracy.",
            published=datetime(2024, 1, 16, tzinfo=timezone.utc),
            categories=["cs.DC", "cs.LG"],
            pdf_url="https://arxiv.org/pdf/2401.12349v1",
            abs_url="https://arxiv.org/abs/2401.12349v1",
        ),
    ]


def main():
    logger.info("🚀 Starting demo with mock data...")

    # Load config
    config = load_config()

    # Create mock papers
    mock_papers = create_mock_papers()
    logger.info(f"Created {len(mock_papers)} mock papers")

    # Score with Claude
    logger.info("Scoring papers with Claude...")
    scorer = ClaudeScorer(
        model=config.scoring.model,
        batch_size=config.scoring.batch_size,
    )
    scored_papers = scorer.score(mock_papers)
    logger.info(f"Scored {len(scored_papers)} papers")

    # Cache results
    db = PaperDatabase(config.storage.db_path)
    db.cache_papers(scored_papers)
    logger.info(f"Cached {len(scored_papers)} scored papers")

    # Print results
    for sp in scored_papers:
        print(f"\n{'='*80}")
        print(f"📄 {sp.paper.title}")
        print(f"   Relevance: {sp.relevance_score:.1f}/10  Quality: {sp.quality_score:.1f}/10")
        print(f"   Tags: {', '.join(sp.sub_domain_tags)}")
        print(f"   {sp.summary_zh}")

    # Send to users
    for user in config.users:
        logger.info(f"\n{'='*80}")
        logger.info(f"Processing user: {user.user_id}")

        # Filter by sub-domain
        sub_domains = user.subscriptions.sub_domains
        if "all" not in sub_domains:
            wanted = set(sub_domains)
            filtered = [sp for sp in scored_papers if set(sp.sub_domain_tags) & wanted]
        else:
            filtered = list(scored_papers)

        # Filter by thresholds
        filtered = [
            sp for sp in filtered
            if sp.relevance_score >= user.thresholds.min_relevance
            and sp.quality_score >= user.thresholds.min_quality
        ]

        logger.info(f"  → {len(filtered)} papers after filtering (sub_domains={sub_domains})")

        if not filtered:
            logger.info(f"  → No papers to send")
            continue

        # Create notifiers
        notifiers = create_notifiers_for_user(user.notify)
        if not notifiers:
            logger.warning(f"  → No notifiers configured")
            continue

        # Send
        for notifier in notifiers:
            logger.info(f"  → Sending via {notifier.name}...")
            success = notifier.notify(filtered)
            if success:
                logger.info(f"    ✓ {notifier.name} sent successfully")
            else:
                logger.error(f"    ✗ {notifier.name} failed")

        # Mark as sent
        db.mark_sent(user.user_id, filtered)

    logger.info(f"\n{'='*80}")
    logger.info("✅ Demo complete!")


if __name__ == "__main__":
    main()
