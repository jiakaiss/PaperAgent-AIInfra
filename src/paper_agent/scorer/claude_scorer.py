"""Claude-based paper scorer using tool_use for structured output."""

from __future__ import annotations

import json
import logging

import anthropic

from paper_agent.models import Paper, ScoredPaper

logger = logging.getLogger(__name__)

SCORE_TOOL = {
    "name": "score_papers",
    "description": "Score each paper for AI Infrastructure relevance and quality",
    "input_schema": {
        "type": "object",
        "properties": {
            "scores": {
                "type": "array",
                "description": "Scores for each paper in the batch",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {
                            "type": "integer",
                            "description": "Paper index in the batch (0-based)",
                        },
                        "relevance_score": {
                            "type": "number",
                            "description": "Relevance to AI Infrastructure (0-10)",
                            "minimum": 0,
                            "maximum": 10,
                        },
                        "quality_score": {
                            "type": "number",
                            "description": "Overall quality and impact (0-10)",
                            "minimum": 0,
                            "maximum": 10,
                        },
                        "summary_zh": {
                            "type": "string",
                            "description": "One-line summary in Chinese (1-2 sentences)",
                        },
                    },
                    "required": ["index", "relevance_score", "quality_score", "summary_zh"],
                },
            }
        },
        "required": ["scores"],
    },
}

SYSTEM_PROMPT = """You are an expert reviewer specializing in AI Infrastructure. Your task is to evaluate academic papers for their relevance to AI Infra and overall quality.

**AI Infrastructure** includes (but is not limited to):
- Distributed training systems and frameworks
- Model/pipeline/tensor/data parallelism
- GPU/TPU scheduling and cluster management
- Model serving and inference optimization
- Memory optimization and checkpoint systems
- Communication optimization (all-reduce, all-gather, etc.)
- Deep learning compilers and operator fusion
- Quantization, compression, and efficient inference
- KV cache management and speculative decoding
- Mixture-of-experts systems
- LLM training infrastructure at scale

**Relevance Score (0-10):**
- 9-10: Core AI Infra paper (new training framework, parallelism strategy, etc.)
- 7-8: Directly applicable to AI Infra (optimization techniques, system design)
- 5-6: Somewhat related (ML paper with infra implications)
- 3-4: Tangentially related
- 0-2: Not related to AI Infra

**Quality Score (0-10):**
- 9-10: Groundbreaking work from top lab, likely high impact
- 7-8: Solid contribution, well-executed, good results
- 5-6: Decent work, some interesting ideas
- 3-4: Incremental or limited contribution
- 0-2: Low quality or poorly executed

Provide concise, accurate Chinese summaries (1-2 sentences)."""


class ClaudeScorer:
    """Scores papers using Anthropic Claude API with tool_use."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-haiku-4-5",
        batch_size: int = 10,
    ):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.batch_size = batch_size

    def _format_papers(self, papers: list[Paper]) -> str:
        """Format papers for the Claude prompt."""
        parts = []
        for i, p in enumerate(papers):
            parts.append(
                f"--- Paper {i} ---\n"
                f"Title: {p.title}\n"
                f"Authors: {', '.join(p.authors[:5])}{'...' if len(p.authors) > 5 else ''}\n"
                f"Categories: {', '.join(p.categories)}\n"
                f"Abstract: {p.abstract[:800]}\n"
            )
        return "\n".join(parts)

    def _score_batch(self, papers: list[Paper]) -> list[ScoredPaper]:
        """Score a single batch of papers."""
        if not papers:
            return []

        user_msg = (
            f"Please score the following {len(papers)} papers for AI Infrastructure "
            f"relevance and quality. Use the score_papers tool to provide your scores.\n\n"
            f"{self._format_papers(papers)}"
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=[SCORE_TOOL],
            tool_choice={"type": "tool", "name": "score_papers"},
            messages=[{"role": "user", "content": user_msg}],
        )

        scored = []
        for block in response.content:
            if block.type == "tool_use" and block.name == "score_papers":
                scores_data = block.input.get("scores", [])
                for item in scores_data:
                    idx = item["index"]
                    if 0 <= idx < len(papers):
                        scored.append(
                            ScoredPaper(
                                paper=papers[idx],
                                relevance_score=float(item["relevance_score"]),
                                quality_score=float(item["quality_score"]),
                                summary_zh=item["summary_zh"],
                            )
                        )

        return scored

    def score(self, papers: list[Paper]) -> list[ScoredPaper]:
        """Score all papers in batches."""
        if not papers:
            return []

        all_scored: list[ScoredPaper] = []
        total_batches = (len(papers) + self.batch_size - 1) // self.batch_size

        for i in range(0, len(papers), self.batch_size):
            batch = papers[i : i + self.batch_size]
            batch_num = i // self.batch_size + 1
            logger.info(
                f"Scoring batch {batch_num}/{total_batches} ({len(batch)} papers)..."
            )

            try:
                scored = self._score_batch(batch)
                all_scored.extend(scored)
                logger.info(f"  → Scored {len(scored)} papers")
            except Exception as e:
                logger.error(f"  → Failed to score batch {batch_num}: {e}")
                continue

        logger.info(f"Total scored: {len(all_scored)}/{len(papers)} papers")
        return all_scored
