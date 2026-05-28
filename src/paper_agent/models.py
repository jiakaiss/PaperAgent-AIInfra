"""Data models for papers and sub-domain taxonomy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from paper_agent.config import ScoringConfig


# Sub-domain taxonomy: each sub-domain maps to a list of arXiv keywords
SUB_DOMAINS: dict[str, list[str]] = {
    "quantization": [
        "quantization",
        "PTQ",
        "QAT",
        "INT8",
        "INT4",
        "GPTQ",
        "AWQ",
        "GGUF",
        "mixed precision",
        "low-bit",
        "weight quantization",
        "activation quantization",
    ],
    "distillation": [
        "knowledge distillation",
        "model distillation",
        "teacher-student",
        "self-distillation",
        "distillation",
        "model compression via distillation",
    ],
    "pruning": [
        "pruning",
        "structured pruning",
        "unstructured pruning",
        "lottery ticket",
        "weight pruning",
        "neuron pruning",
        "sparse training",
    ],
    "sparsity": [
        "sparsity",
        "sparse inference",
        "sparse attention",
        "2:4 sparsity",
        "N:M sparsity",
        "structured sparsity",
        "sparse computation",
    ],
    "distributed_training": [
        "distributed training",
        "data parallelism",
        "FSDP",
        "DeepSpeed",
        "ZeRO",
        "distributed optimization",
        "synchronous training",
    ],
    "parallelism": [
        "tensor parallelism",
        "pipeline parallelism",
        "model parallelism",
        "Megatron",
        "3D parallelism",
        "sequence parallelism",
        "expert parallelism",
    ],
    "serving": [
        "model serving",
        "vLLM",
        "continuous batching",
        "PagedAttention",
        "inference engine",
        "TGI",
        "TensorRT-LLM",
        "request scheduling",
    ],
    "speculative_decoding": [
        "speculative decoding",
        "draft model",
        "speculative inference",
        "speculative sampling",
        "assisted generation",
    ],
    "kv_cache": [
        "KV cache",
        "prefix caching",
        "PagedAttention",
        "attention optimization",
        "key-value cache",
        "memory efficient attention",
    ],
    "moe": [
        "mixture of experts",
        "MoE",
        "sparse MoE",
        "expert parallelism",
        "expert routing",
        "load balancing",
    ],
    "compiler": [
        "deep learning compiler",
        "operator fusion",
        "TVM",
        "XLA",
        "MLIR",
        "FlashAttention",
        "code generation",
        "graph optimization",
    ],
    "memory_optimization": [
        "memory optimization",
        "activation checkpointing",
        "offloading",
        "gradient compression",
        "memory efficient",
        "gradient checkpointing",
    ],
    "communication": [
        "all-reduce",
        "all-gather",
        "communication optimization",
        "Ring",
        "Tree",
        "NCCL",
        "gradient compression",
        "communication efficient",
    ],
    "scheduling": [
        "GPU scheduling",
        "cluster management",
        "job scheduling",
        "GPU cluster",
        "resource allocation",
        "workload balancing",
    ],
}

# Reverse mapping: keyword -> sub-domain (for quick lookup)
KEYWORD_TO_SUB_DOMAIN: dict[str, str] = {}
for _sd, _keywords in SUB_DOMAINS.items():
    for _kw in _keywords:
        KEYWORD_TO_SUB_DOMAIN[_kw.lower()] = _sd


@dataclass(frozen=True)
class Paper:
    """A paper fetched from arXiv."""

    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    published: datetime
    categories: list[str]
    pdf_url: str
    abs_url: str

    @property
    def primary_category(self) -> str:
        return self.categories[0] if self.categories else "unknown"


@dataclass(frozen=True)
class ScoredPaper:
    """A paper with LLM-generated scores and summary."""

    paper: Paper
    relevance_score: float  # 0-10, relevance to AI Infra
    quality_score: float  # 0-10, overall quality/impact
    summary_zh: str  # One-line Chinese summary
    sub_domain_tags: tuple[str, ...] = ()  # 1-3 sub-domain tags

    @property
    def total_score(self) -> float:
        """Weighted total score (relevance matters more)."""
        return self.relevance_score * 0.6 + self.quality_score * 0.4

    @property
    def sub_domain_display(self) -> str:
        """Format sub-domain tags for display."""
        return ", ".join(self.sub_domain_tags) if self.sub_domain_tags else "general"


@dataclass(frozen=True)
class ScoreWeights:
    """Weights for combining relevance and quality scores into a total score.

    Default values (0.6, 0.4) match the historical hardcoded behavior in
    ``ScoredPaper.total_score``.
    """

    relevance: float = 0.6
    quality: float = 0.4

    @classmethod
    def from_scoring_config(cls, config: ScoringConfig) -> ScoreWeights:
        """Construct weights from a ``ScoringConfig`` instance."""
        return cls(
            relevance=config.relevance_weight,
            quality=config.quality_weight,
        )


def compute_total_score(paper: ScoredPaper, weights: ScoreWeights) -> float:
    """Compute weighted total score using the given weights."""
    return paper.relevance_score * weights.relevance + paper.quality_score * weights.quality


def sort_by_score(
    papers: list[ScoredPaper],
    weights: ScoreWeights | None = None,
) -> list[ScoredPaper]:
    """Sort papers by total score, highest first.

    When ``weights`` is provided, uses ``compute_total_score`` with those
    weights. Otherwise falls back to ``ScoredPaper.total_score`` (default
    0.6/0.4 weighting) for backward compatibility.
    """
    if weights is None:
        return sorted(papers, key=lambda p: p.total_score, reverse=True)
    return sorted(
        papers,
        key=lambda p: compute_total_score(p, weights),
        reverse=True,
    )


def get_all_sub_domain_keywords() -> list[str]:
    """Get a flat list of all keywords across all sub-domains."""
    keywords = []
    for kw_list in SUB_DOMAINS.values():
        keywords.extend(kw_list)
    return keywords
