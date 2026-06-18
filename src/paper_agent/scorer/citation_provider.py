"""Citation-count provider abstraction with a Semantic Scholar implementation.

The citation-aware-scoring change introduced this layer so the rest of the
pipeline never knows about HTTP, rate limits, or response formats — it just
asks ``provider.get_citations(arxiv_ids)`` and gets back a dict.

Two design decisions to remember:

1. **Never crash the caller.** S2 is best-effort: 5xx responses, timeouts,
   even truncated JSON should log + return whatever partial data we have.
   Citation refresh is opportunistic — a failed batch just means the rows
   stay stale until the next tick.

2. **Skip unknown papers silently.** S2's batch endpoint returns ``null`` for
   IDs it doesn't know. The dict returned by :meth:`get_citations` simply
   has no entry for those IDs; callers must treat "missing" as "no data
   this run" rather than an error.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import requests

if TYPE_CHECKING:
    from paper_agent.config import CitationsConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CitationInfo:
    """Citation metrics for a single paper."""

    citation_count: int
    influential_citation_count: int


class CitationProvider(Protocol):
    """Anything that maps arXiv IDs to citation metrics."""

    def get_citations(self, arxiv_ids: list[str]) -> dict[str, CitationInfo]:
        """Look up citation data for a batch of arXiv IDs.

        Returns a dict keyed by ``arxiv_id``. IDs the provider has no data
        for are simply absent from the dict — never an exception. The
        caller treats absence as "skip this paper this run".
        """
        ...


# ─── Semantic Scholar ───


_S2_BATCH_PATH = "/paper/batch"
_S2_FIELDS = "externalIds,citationCount,influentialCitationCount"

# arXiv IDs in our cache carry a version suffix (e.g. "2401.12345v1") because
# that's what the arXiv fetcher stores as the PK. S2's batch endpoint REJECTS
# versioned IDs with HTTP 400 "No valid paper ids given" — it only accepts the
# bare ID ("2401.12345"). We strip the suffix before sending and map the
# response back to the original versioned key by index alignment.
_VERSION_SUFFIX = re.compile(r"v\d+$")


def _bare_arxiv_id(arxiv_id: str) -> str:
    """Strip a trailing arXiv version suffix (``v1``, ``v2``, …)."""
    return _VERSION_SUFFIX.sub("", arxiv_id)


class SemanticScholarCitationProvider:
    """Citation provider backed by the Semantic Scholar Graph API.

    Uses the batch endpoint::

        POST /graph/v1/paper/batch?fields=...
        body: {"ids": ["ArXiv:2401.12345", ...]}

    which returns a list aligned with the input IDs, with ``null`` entries
    for unknown papers. We tolerate any HTTP error and return only the IDs
    we successfully parsed — citation refresh is opportunistic.
    """

    def __init__(self, config: CitationsConfig):
        self._base_url = config.base_url.rstrip("/")
        self._api_key = config.api_key
        self._timeout = config.request_timeout
        self._batch_size = config.batch_size
        self._rps = config.requests_per_second

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self._api_key:
            h["x-api-key"] = self._api_key
        return h

    def _fetch_batch(self, arxiv_ids: list[str]) -> dict[str, CitationInfo]:
        """One HTTP round-trip for ``arxiv_ids``; returns parsed dict.

        The returned dict is keyed by the ORIGINAL ``arxiv_ids`` (which may
        carry version suffixes) so callers can match DB rows by PK. Internally
        we send bare IDs to S2 (it rejects versioned IDs) and rely on the
        response's index alignment to map results back.
        """
        if not arxiv_ids:
            return {}
        url = f"{self._base_url}{_S2_BATCH_PATH}"
        # S2 rejects versioned IDs (HTTP 400) — strip the vN suffix.
        bare_ids = [_bare_arxiv_id(aid) for aid in arxiv_ids]
        body = {"ids": [f"ArXiv:{bid}" for bid in bare_ids]}
        try:
            resp = requests.post(
                url,
                params={"fields": _S2_FIELDS},
                json=body,
                headers=self._headers(),
                timeout=self._timeout,
            )
        except requests.RequestException as e:
            logger.warning("S2 batch request failed: %s — skipping %d ids", e, len(arxiv_ids))
            return {}

        if resp.status_code != 200:
            logger.warning(
                "S2 batch returned HTTP %s — skipping %d ids (body: %s)",
                resp.status_code,
                len(arxiv_ids),
                resp.text[:200],
            )
            return {}

        try:
            data = resp.json()
        except ValueError as e:
            logger.warning("S2 batch returned invalid JSON: %s", e)
            return {}

        if not isinstance(data, list):
            logger.warning("S2 batch unexpected response shape: %r", type(data))
            return {}

        out: dict[str, CitationInfo] = {}
        # The response list aligns positionally with our request body, so map
        # each entry back to the original (versioned) arxiv_id by index. This
        # is what lets update_citations match the versioned DB PK.
        for i, entry in enumerate(data):
            if entry is None:
                continue  # paper not indexed by S2
            if i >= len(arxiv_ids):
                break  # defensive: malformed response longer than request
            cc = entry.get("citationCount") or 0
            ic = entry.get("influentialCitationCount") or 0
            out[arxiv_ids[i]] = CitationInfo(
                citation_count=int(cc),
                influential_citation_count=int(ic),
            )
        return out

    def get_citations(self, arxiv_ids: list[str]) -> dict[str, CitationInfo]:
        """Batch-fetch citations, honoring ``requests_per_second`` rate limit."""
        if not arxiv_ids:
            return {}
        out: dict[str, CitationInfo] = {}
        sleep_between = 1.0 / max(self._rps, 0.001)
        for i in range(0, len(arxiv_ids), self._batch_size):
            chunk = arxiv_ids[i : i + self._batch_size]
            out.update(self._fetch_batch(chunk))
            # Sleep between chunks (not after the last) to spread load.
            if i + self._batch_size < len(arxiv_ids):
                time.sleep(sleep_between)
        return out


def create_citation_provider(config: CitationsConfig) -> CitationProvider | None:
    """Construct the configured citation provider, or ``None`` when disabled.

    Returning ``None`` lets callers short-circuit cheaply::

        provider = create_citation_provider(config.citations)
        if provider is None:
            return  # citations disabled or unsupported provider
    """
    if not config.enabled:
        return None
    if config.provider == "semantic_scholar":
        return SemanticScholarCitationProvider(config)
    logger.warning(
        "Unknown citations.provider=%r — citations disabled for this session",
        config.provider,
    )
    return None
