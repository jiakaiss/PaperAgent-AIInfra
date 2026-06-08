"""Claude-based paper scorer using tool_use for structured output."""

from __future__ import annotations

import logging
from string import Formatter
from typing import TYPE_CHECKING

import anthropic

from paper_agent.models import IMPACT_TIERS, SUB_DOMAINS, Paper, ScoredPaper

if TYPE_CHECKING:
    from paper_agent.config import PromptsConfig, ScoringConfig


class _SafeFormatter(Formatter):
    """str.format() that leaves unknown placeholders as-is instead of raising."""

    def get_value(self, key, args, kwargs):
        try:
            return super().get_value(key, args, kwargs)
        except (KeyError, IndexError):
            return "{" + str(key) + "}"


logger = logging.getLogger(__name__)

# Build the sub-domain enum list for the tool schema
SUB_DOMAIN_KEYS = list(SUB_DOMAINS.keys())

# Bounds for the new structured fields. Centralised so validation in
# _score_batch and the tool schema description stay in sync.
MAX_KEY_CONTRIBUTIONS = 3
MAX_CONTRIBUTION_CHARS = 120
DEFAULT_IMPACT_TIER = "solid"

SCORE_TOOL = {
    "name": "score_papers",
    "description": (
        "Score each paper for AI Infrastructure relevance and quality, "
        "assign sub-domain tags, and extract structured insights "
        "(key contributions, problem framing, methods, impact tier)."
    ),
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
                        "sub_domain_tags": {
                            "type": "array",
                            "description": (
                                "1-3 sub-domain tags this paper belongs to "
                                "(choose from the defined sub-domains)"
                            ),
                            "items": {
                                "type": "string",
                                "enum": SUB_DOMAIN_KEYS,
                            },
                            "minItems": 1,
                            "maxItems": 3,
                        },
                        "key_contributions": {
                            "type": "array",
                            "description": (
                                f"1-{MAX_KEY_CONTRIBUTIONS} short bullet phrases "
                                f"capturing this paper's distinguishing contributions. "
                                f"Each bullet must be ≤ {MAX_CONTRIBUTION_CHARS} "
                                "characters. Prefer concrete claims "
                                '("reduces KV cache by 4x") over generic ones '
                                '("novel method"). Write in the same language as '
                                "the abstract."
                            ),
                            "items": {"type": "string"},
                            "minItems": 1,
                            "maxItems": MAX_KEY_CONTRIBUTIONS,
                        },
                        "problem_statement_zh": {
                            "type": "string",
                            "description": (
                                "1-2 sentences in Chinese describing the problem "
                                "the paper addresses."
                            ),
                        },
                        "methods_zh": {
                            "type": "string",
                            "description": (
                                "1-2 sentences in Chinese describing the methods or approach used."
                            ),
                        },
                        "impact_tier": {
                            "type": "string",
                            "description": (
                                "Coarse impact tier. "
                                "'breakthrough' = novel technique or result likely "
                                "to be widely cited or change practice; "
                                "'solid' = well-executed, useful, incremental on a "
                                "clear baseline (most papers); "
                                "'incremental' = minor variation, narrow scope, or "
                                "limited evaluation. Be conservative: when in doubt "
                                "choose 'solid'."
                            ),
                            "enum": list(IMPACT_TIERS),
                        },
                    },
                    "required": [
                        "index",
                        "relevance_score",
                        "quality_score",
                        "summary_zh",
                        "sub_domain_tags",
                        "key_contributions",
                        "problem_statement_zh",
                        "methods_zh",
                        "impact_tier",
                    ],
                },
            }
        },
        "required": ["scores"],
    },
}

# Build sub-domain descriptions for the system prompt
SUB_DOMAIN_DESCRIPTIONS = """
**Sub-Domain Taxonomy** (assign 1-3 tags per paper):
- `quantization`: Post-training quantization (PTQ), quantization-aware training (QAT),
  mixed-precision, INT4/INT8, GPTQ, AWQ, GGUF
- `distillation`: Knowledge distillation, teacher-student frameworks, self-distillation,
  model compression via distillation
- `pruning`: Network pruning (structured/unstructured), lottery ticket hypothesis,
  weight/neuron pruning
- `sparsity`: Sparse computation, sparse attention, 2:4 / N:M sparsity, sparse kernels
- `distributed_training`: Distributed training systems, data parallelism, FSDP, DeepSpeed, ZeRO
- `parallelism`: Tensor/pipeline/model/sequence parallelism, Megatron, 3D parallelism
- `serving`: Model serving engines, vLLM, continuous batching, PagedAttention,
  inference optimization
- `speculative_decoding`: Speculative decoding, draft models, speculative inference/sampling
- `kv_cache`: KV cache management, prefix caching, attention memory optimization
- `moe`: Mixture-of-experts systems, sparse MoE, expert routing, load balancing
- `compiler`: Deep learning compilers, operator fusion, TVM, XLA, MLIR, FlashAttention
- `memory_optimization`: Memory optimization, activation/gradient checkpointing, offloading
- `communication`: All-reduce, all-gather, NCCL, communication-efficient training
- `scheduling`: GPU scheduling, cluster management, job scheduling, resource allocation
"""

SYSTEM_PROMPT = f"""You are an expert reviewer specializing in AI Infrastructure. Your task
is to evaluate academic papers for their relevance to AI Infra and overall quality.

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

{SUB_DOMAIN_DESCRIPTIONS}

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

**Impact Tier** (categorical, for triage UI — be conservative, lean toward `solid`):
- `breakthrough`: Novel technique or result likely to be widely cited or change
  practice; introduces a primitive others will build on.
- `solid`: Well-executed, useful work that incrementally advances a clear
  baseline. This is the right answer for most papers.
- `incremental`: Minor variation, narrow scope, or limited evaluation;
  reproduces a known idea with small tweaks.

**Structured Insights** (extract per paper):
- `key_contributions`: 1-3 short bullet phrases. Prefer concrete claims
  ("reduces KV cache memory by 4x with <1% accuracy drop") over generic ones
  ("novel attention method"). Each bullet ≤ 120 characters.
- `problem_statement_zh`: 1-2 Chinese sentences naming the concrete problem.
- `methods_zh`: 1-2 Chinese sentences naming the approach.

Provide concise, accurate Chinese summaries (1-2 sentences)."""


_DEFAULT_USER_MESSAGE_TEMPLATE = (
    "Please score the following {paper_count} papers for AI Infrastructure "
    "relevance and quality. Use the score_papers tool to provide your scores, "
    "including sub_domain_tags for each paper.\n\n"
    "{papers}"
)


def _build_tool_choice(value: str) -> dict:
    """Convert a ``tool_choice`` config string to the Anthropic API dict form."""
    if value == "tool":
        return {"type": "tool", "name": SCORE_TOOL["name"]}
    # Default: "auto" or any other value → auto
    return {"type": "auto"}


# Sentinel to distinguish "kwarg not passed" from "kwarg explicitly None".
_UNSET = object()


def _resolve(explicit, config, attr, default=_UNSET):
    """Resolve a parameter: explicit kwarg > config value > default.

    Returns the first non-None value in the chain. When *default* is
    ``_UNSET`` and no value is found, returns ``None``.
    """
    if explicit is not None:
        return explicit
    if config is not None:
        val = getattr(config, attr, None)
        if val is not None:
            return val
    return None if default is _UNSET else default


class ClaudeScorer:
    """Scores papers using Anthropic Claude API with tool_use.

    All scoring behavior (API connection, generation parameters, prompts) can
    be configured via a ``ScoringConfig`` object. Individual kwargs are also
    accepted for backward compatibility and testing.
    """

    def __init__(
        self,
        config: ScoringConfig | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        batch_size: int | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        tool_choice: str | None = None,
        abstract_max_length: int | None = None,
        prompts: PromptsConfig | None = None,
    ):
        # Resolve: explicit kwarg > config > hardcoded default
        resolved_model = _resolve(model, config, "model", "claude-haiku-4-5")
        resolved_batch = _resolve(batch_size, config, "batch_size", 10)
        resolved_max_tokens = _resolve(max_tokens, config, "max_tokens", 4096)
        resolved_abs_len = _resolve(abstract_max_length, config, "abstract_max_length", 800)
        resolved_tool = _resolve(tool_choice, config, "tool_choice", "auto")
        resolved_prompts = _resolve(prompts, config, "prompts")

        self.client = anthropic.Anthropic(
            api_key=_resolve(api_key, config, "api_key"),
            base_url=_resolve(base_url, config, "base_url"),
        )
        self.model = resolved_model
        self.batch_size = resolved_batch
        self.max_tokens = resolved_max_tokens
        # temperature: None means "omit from API call" — resolve only when
        # explicitly passed or present in config
        self.temperature = _resolve(temperature, config, "temperature")
        self.tool_choice = _build_tool_choice(resolved_tool)
        self.abstract_max_length = resolved_abs_len
        self.prompts = resolved_prompts

    def _resolve_system_prompt(self) -> str:
        """Return the system prompt to use, falling back to the default."""
        if self.prompts and self.prompts.system_prompt:
            return self.prompts.system_prompt
        return SYSTEM_PROMPT

    def _build_user_message(self, papers: list[Paper]) -> str:
        """Build the user message for a batch, using custom template if set."""
        formatted = self._format_papers(papers)
        if self.prompts and self.prompts.user_message_template:
            return _SafeFormatter().format(
                self.prompts.user_message_template,
                paper_count=len(papers),
                papers=formatted,
            )
        return _DEFAULT_USER_MESSAGE_TEMPLATE.format(
            paper_count=len(papers),
            papers=formatted,
        )

    def _format_papers(self, papers: list[Paper]) -> str:
        """Format papers for the Claude prompt."""
        parts = []
        for i, p in enumerate(papers):
            parts.append(
                f"--- Paper {i} ---\n"
                f"Title: {p.title}\n"
                f"Authors: {', '.join(p.authors[:5])}{'...' if len(p.authors) > 5 else ''}\n"
                f"Categories: {', '.join(p.categories)}\n"
                f"Abstract: {p.abstract[: self.abstract_max_length]}\n"
            )
        return "\n".join(parts)

    def _score_batch(self, papers: list[Paper]) -> list[ScoredPaper]:
        """Score a single batch of papers."""
        if not papers:
            return []

        user_msg = self._build_user_message(papers)

        kwargs: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": self._resolve_system_prompt(),
            "tools": [SCORE_TOOL],
            "tool_choice": self.tool_choice,
            "messages": [{"role": "user", "content": user_msg}],
        }
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature

        response = self.client.messages.create(**kwargs)

        scored = []
        for block in response.content:
            if block.type == "tool_use" and block.name == "score_papers":
                scores_data = block.input.get("scores", [])
                for item in scores_data:
                    idx = item["index"]
                    if 0 <= idx < len(papers):
                        # Validate sub_domain_tags
                        tags = item.get("sub_domain_tags", [])
                        valid_tags = tuple(t for t in tags if t in SUB_DOMAIN_KEYS)

                        # Validate key_contributions: truncate to max, log excess
                        raw_contribs = item.get("key_contributions", [])
                        contribs = tuple(c[:MAX_CONTRIBUTION_CHARS] for c in raw_contribs)
                        if len(contribs) > MAX_KEY_CONTRIBUTIONS:
                            logger.warning(
                                "Paper %s returned %d key_contributions; truncated to first %d.",
                                papers[idx].arxiv_id,
                                len(raw_contribs),
                                MAX_KEY_CONTRIBUTIONS,
                            )
                            contribs = contribs[:MAX_KEY_CONTRIBUTIONS]

                        # Validate impact_tier: unknown values fall back to solid
                        raw_tier = item.get("impact_tier", DEFAULT_IMPACT_TIER)
                        if raw_tier not in IMPACT_TIERS:
                            logger.warning(
                                "Paper %s returned unknown impact_tier=%r; falling back to '%s'.",
                                papers[idx].arxiv_id,
                                raw_tier,
                                DEFAULT_IMPACT_TIER,
                            )
                            raw_tier = DEFAULT_IMPACT_TIER

                        # Allow empty prose fields but log once (aggregate below)
                        problem_zh = item.get("problem_statement_zh", "") or ""
                        methods_zh = item.get("methods_zh", "") or ""

                        scored.append(
                            ScoredPaper(
                                paper=papers[idx],
                                relevance_score=float(item["relevance_score"]),
                                quality_score=float(item["quality_score"]),
                                summary_zh=item["summary_zh"],
                                sub_domain_tags=valid_tags,
                                key_contributions=contribs,
                                problem_statement_zh=problem_zh,
                                methods_zh=methods_zh,
                                impact_tier=raw_tier,
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
            logger.info(f"Scoring batch {batch_num}/{total_batches} ({len(batch)} papers)...")

            try:
                scored = self._score_batch(batch)
                all_scored.extend(scored)
                logger.info(f"  → Scored {len(scored)} papers")
            except Exception as e:
                logger.error(f"  → Failed to score batch {batch_num}: {e}")
                continue

        logger.info(f"Total scored: {len(all_scored)}/{len(papers)} papers")
        _log_tier_distribution(all_scored)
        return all_scored


def _log_tier_distribution(scored: list[ScoredPaper]) -> None:
    """Log how scored papers break down by impact tier."""
    if not scored:
        return
    counts = {tier: 0 for tier in IMPACT_TIERS}
    for sp in scored:
        # tier_rank() coerces unknown values; mirror that here so totals add up.
        bucket = sp.impact_tier if sp.impact_tier in counts else DEFAULT_IMPACT_TIER
        counts[bucket] += 1
    parts = " ".join(f"{tier}={counts[tier]}" for tier in IMPACT_TIERS)
    logger.info("tier distribution: %s", parts)
