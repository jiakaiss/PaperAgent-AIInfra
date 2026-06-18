"""Tests for the citation provider abstraction."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from paper_agent.config import CitationsConfig
from paper_agent.scorer.citation_provider import (
    CitationInfo,
    SemanticScholarCitationProvider,
    create_citation_provider,
)


def _ok_response(payload):
    """Build a fake ``requests.Response``-like object."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    resp.text = "<json body>"
    return resp


def _err_response(status_code=503, text="upstream busy"):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


def _make_config(**overrides):
    return CitationsConfig(enabled=True, **overrides)


# ─── factory ───


def test_factory_returns_none_when_disabled():
    cfg = CitationsConfig(enabled=False)
    assert create_citation_provider(cfg) is None


def test_factory_builds_semantic_scholar_when_enabled():
    cfg = CitationsConfig(enabled=True)
    provider = create_citation_provider(cfg)
    assert isinstance(provider, SemanticScholarCitationProvider)


def test_factory_unknown_provider_warns_and_returns_none(caplog):
    cfg = CitationsConfig(enabled=True, provider="not_a_real_one")
    with caplog.at_level("WARNING"):
        result = create_citation_provider(cfg)
    assert result is None
    assert "Unknown citations.provider" in caplog.text


# ─── happy path ───


@patch("paper_agent.scorer.citation_provider.requests.post")
def test_get_citations_parses_batch_response(mock_post):
    mock_post.return_value = _ok_response(
        [
            {
                "externalIds": {"ArXiv": "2401.00001"},
                "citationCount": 320,
                "influentialCitationCount": 12,
            },
            {
                "externalIds": {"ArXiv": "2402.00002"},
                "citationCount": 5,
                "influentialCitationCount": 0,
            },
        ]
    )
    provider = SemanticScholarCitationProvider(_make_config())
    result = provider.get_citations(["2401.00001", "2402.00002"])

    assert result == {
        "2401.00001": CitationInfo(citation_count=320, influential_citation_count=12),
        "2402.00002": CitationInfo(citation_count=5, influential_citation_count=0),
    }


@patch("paper_agent.scorer.citation_provider.requests.post")
def test_version_suffix_stripped_before_sending(mock_post):
    """arXiv IDs in the cache carry ``vN`` suffixes; S2 rejects them (HTTP 400).

    The provider must strip the suffix when building the request body, but
    still key the result by the ORIGINAL versioned ID so DB updates match
    the versioned PK.
    """
    mock_post.return_value = _ok_response(
        [
            {
                "externalIds": {"ArXiv": "2605.24461"},
                "citationCount": 42,
                "influentialCitationCount": 3,
            }
        ]
    )
    provider = SemanticScholarCitationProvider(_make_config())
    # Pass a versioned ID (as stored in the cache).
    result = provider.get_citations(["2605.24461v1"])

    # Request body must use the BARE id (no v1) — S2 rejects versioned ids.
    body = mock_post.call_args.kwargs["json"]
    assert body == {"ids": ["ArXiv:2605.24461"]}
    # Result is keyed by the original versioned id (the DB PK).
    assert result == {"2605.24461v1": CitationInfo(citation_count=42, influential_citation_count=3)}


@patch("paper_agent.scorer.citation_provider.requests.post")
def test_unknown_paper_skipped(mock_post):
    """S2 returns ``null`` for unindexed papers — they're absent from the result."""
    mock_post.return_value = _ok_response(
        [
            {
                "externalIds": {"ArXiv": "2401.00001"},
                "citationCount": 100,
                "influentialCitationCount": 5,
            },
            None,  # unknown to S2
        ]
    )
    provider = SemanticScholarCitationProvider(_make_config())
    result = provider.get_citations(["2401.00001", "2401.zzzzz"])

    assert "2401.00001" in result
    assert "2401.zzzzz" not in result  # silent skip


@patch("paper_agent.scorer.citation_provider.requests.post")
def test_api_key_header_injected_when_set(mock_post):
    mock_post.return_value = _ok_response([])
    provider = SemanticScholarCitationProvider(_make_config(api_key="secret-key-123"))
    provider.get_citations(["2401.00001"])

    headers = mock_post.call_args.kwargs["headers"]
    assert headers["x-api-key"] == "secret-key-123"


@patch("paper_agent.scorer.citation_provider.requests.post")
def test_api_key_header_absent_when_unset(mock_post):
    mock_post.return_value = _ok_response([])
    provider = SemanticScholarCitationProvider(_make_config(api_key=None))
    provider.get_citations(["2401.00001"])

    headers = mock_post.call_args.kwargs["headers"]
    assert "x-api-key" not in headers


# ─── failure modes never crash the caller ───


@patch("paper_agent.scorer.citation_provider.requests.post")
def test_http_error_returns_empty_no_raise(mock_post, caplog):
    mock_post.return_value = _err_response(503, "busy")
    provider = SemanticScholarCitationProvider(_make_config())
    with caplog.at_level("WARNING"):
        result = provider.get_citations(["2401.00001"])
    assert result == {}
    assert "HTTP 503" in caplog.text


@patch("paper_agent.scorer.citation_provider.requests.post")
def test_request_exception_returns_empty(mock_post, caplog):
    import requests

    mock_post.side_effect = requests.Timeout("timed out")
    provider = SemanticScholarCitationProvider(_make_config())
    with caplog.at_level("WARNING"):
        result = provider.get_citations(["2401.00001"])
    assert result == {}
    assert "S2 batch request failed" in caplog.text


@patch("paper_agent.scorer.citation_provider.requests.post")
def test_invalid_json_returns_empty(mock_post, caplog):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.side_effect = ValueError("bad json")
    mock_post.return_value = resp
    provider = SemanticScholarCitationProvider(_make_config())
    with caplog.at_level("WARNING"):
        result = provider.get_citations(["2401.00001"])
    assert result == {}


# ─── batching & rate limiting ───


@patch("paper_agent.scorer.citation_provider.time.sleep")
@patch("paper_agent.scorer.citation_provider.requests.post")
def test_batches_at_configured_size(mock_post, mock_sleep):
    mock_post.return_value = _ok_response([])
    cfg = _make_config(batch_size=2, requests_per_second=10.0)
    provider = SemanticScholarCitationProvider(cfg)

    # 5 ids, batch_size=2 → 3 batches (2+2+1)
    provider.get_citations(["a", "b", "c", "d", "e"])

    assert mock_post.call_count == 3
    # Sleep between batches: 2 sleeps for 3 batches
    assert mock_sleep.call_count == 2
    # Sleep duration = 1 / requests_per_second
    assert mock_sleep.call_args_list[0].args[0] == pytest.approx(0.1)


@patch("paper_agent.scorer.citation_provider.time.sleep")
@patch("paper_agent.scorer.citation_provider.requests.post")
def test_no_sleep_for_single_batch(mock_post, mock_sleep):
    mock_post.return_value = _ok_response([])
    cfg = _make_config(batch_size=10, requests_per_second=1.0)
    provider = SemanticScholarCitationProvider(cfg)

    provider.get_citations(["a", "b"])

    assert mock_post.call_count == 1
    assert mock_sleep.call_count == 0


@patch("paper_agent.scorer.citation_provider.requests.post")
def test_empty_input_no_request(mock_post):
    provider = SemanticScholarCitationProvider(_make_config())
    result = provider.get_citations([])
    assert result == {}
    assert mock_post.call_count == 0
