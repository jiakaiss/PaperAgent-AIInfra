"""Tests for older-works discovery and ingest cap."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from paper_agent.config import CitationsConfig, ThresholdsConfig
from paper_agent.fetcher.older_works_fetcher import (
    _s2_to_paper,
    discover_older_works,
)


def _ok_response(payload):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    resp.text = ""
    return resp


def _err_response():
    resp = MagicMock()
    resp.status_code = 500
    resp.text = "boom"
    return resp


def _s2_entry(
    arxiv_id="2202.00001",
    title="Title",
    abstract="An abstract",
    citations=200,
    year=2022,
):
    return {
        "paperId": "abc",
        "title": title,
        "abstract": abstract,
        "authors": [{"name": "Alice"}],
        "year": year,
        "externalIds": {"ArXiv": arxiv_id} if arxiv_id else {},
        "citationCount": citations,
    }


# ─── _s2_to_paper conversion ───


def test_s2_to_paper_skips_no_arxiv_id():
    """Non-arXiv papers can't be cached."""
    entry = _s2_entry(arxiv_id=None)
    assert _s2_to_paper(entry) is None


def test_s2_to_paper_skips_empty_title():
    entry = _s2_entry(title="")
    assert _s2_to_paper(entry) is None


def test_s2_to_paper_skips_empty_abstract():
    """Abstract is required for the LLM scorer to do its job."""
    entry = _s2_entry(abstract="")
    assert _s2_to_paper(entry) is None


def test_s2_to_paper_round_trip():
    entry = _s2_entry(arxiv_id="2205.14135", year=2022)
    paper = _s2_to_paper(entry)
    assert paper is not None
    assert paper.arxiv_id == "2205.14135"
    assert paper.published.year == 2022
    assert paper.abs_url == "https://arxiv.org/abs/2205.14135"


# ─── discover_older_works gating ───


def test_discover_disabled_when_citations_off():
    """citations.enabled=false → no HTTP call, empty result."""
    cfg = CitationsConfig(enabled=False)
    th = ThresholdsConfig(older_works_per_digest=5)
    with patch("paper_agent.fetcher.older_works_fetcher.requests.get") as mock_get:
        papers, source_map, citation_map = discover_older_works(cfg, th)
    assert papers == []
    assert source_map == {}
    assert citation_map == {}
    mock_get.assert_not_called()


def test_discover_disabled_when_per_digest_zero():
    """older_works_per_digest=0 → no work needed."""
    cfg = CitationsConfig(enabled=True)
    th = ThresholdsConfig(older_works_per_digest=0)
    with patch("paper_agent.fetcher.older_works_fetcher.requests.get") as mock_get:
        papers, source_map, citation_map = discover_older_works(cfg, th)
    assert papers == []
    assert source_map == {}
    assert citation_map == {}
    mock_get.assert_not_called()


# ─── filtering ───


@patch("paper_agent.fetcher.older_works_fetcher.requests.get")
def test_filters_below_min_citations(mock_get):
    """citationCount < min_citations_for_older_works is dropped."""
    mock_get.return_value = _ok_response(
        {
            "data": [
                _s2_entry(arxiv_id="2201.001", citations=200),  # passes
                _s2_entry(arxiv_id="2201.002", citations=50),  # filtered out
            ]
        }
    )
    cfg = CitationsConfig(enabled=True)
    th = ThresholdsConfig(
        older_works_per_digest=5,
        min_citations_for_older_works=100,
    )
    result, _, citation_map = discover_older_works(cfg, th, sub_domains=["quantization"])
    ids = [p.arxiv_id for p in result]
    assert "2201.001" in ids
    assert "2201.002" not in ids
    # Citation count is carried out — no second S2 round-trip needed.
    assert citation_map["2201.001"] == (200, 0)


@patch("paper_agent.fetcher.older_works_fetcher.requests.get")
def test_age_window_passed_to_s2(mock_get):
    """min/max age years define a year-range window on the S2 query."""
    mock_get.return_value = _ok_response({"data": []})
    cfg = CitationsConfig(
        enabled=True,
        older_works_min_age_years=3,
        older_works_max_age_years=12,
    )
    th = ThresholdsConfig(older_works_per_digest=5)

    discover_older_works(cfg, th, sub_domains=["serving"])

    # Inspect the call params: S2 range syntax "YYYY-YYYY"
    from datetime import datetime as _dt

    cur = _dt.now().year
    params = mock_get.call_args.kwargs["params"]
    assert params["year"] == f"{cur - 12}-{cur - 3}"


@patch("paper_agent.fetcher.older_works_fetcher.requests.get")
def test_default_max_age_excludes_old_papers(mock_get):
    """Default max_age_years=10 produces a sensible lower year bound.

    Pinned both ends in the URL param so a future regression that removes
    the upper bound (and lets 1990s/2000s papers in) will fail this test.
    """
    mock_get.return_value = _ok_response({"data": []})
    cfg = CitationsConfig(enabled=True)  # defaults: min=2, max=10
    th = ThresholdsConfig(older_works_per_digest=5)

    discover_older_works(cfg, th, sub_domains=["scheduling"])

    from datetime import datetime as _dt

    cur = _dt.now().year
    params = mock_get.call_args.kwargs["params"]
    assert params["year"] == f"{cur - 10}-{cur - 2}"


def test_max_age_must_be_at_least_min_age():
    """Validator rejects max_age < min_age — would produce an empty window."""
    import pytest

    with pytest.raises(ValueError, match="older_works_max_age_years"):
        CitationsConfig(
            enabled=True,
            older_works_min_age_years=5,
            older_works_max_age_years=3,
        )


@patch("paper_agent.fetcher.older_works_fetcher.requests.get")
def test_dedup_across_keywords(mock_get):
    """A paper matching two sub-domain keywords appears once."""
    # Same arxiv_id surfaces under two keywords
    mock_get.return_value = _ok_response({"data": [_s2_entry(arxiv_id="2201.001", citations=200)]})
    cfg = CitationsConfig(enabled=True)
    th = ThresholdsConfig(
        older_works_per_digest=5,
        min_citations_for_older_works=100,
    )
    result, source_map, _ = discover_older_works(cfg, th, sub_domains=["quantization", "kv_cache"])
    ids = [p.arxiv_id for p in result]
    assert ids.count("2201.001") == 1
    # Source map records the FIRST sub-domain that surfaced the paper.
    assert source_map["2201.001"] == "quantization"


# ─── search ergonomics: sort, page size, keyword variants ───


@patch("paper_agent.fetcher.older_works_fetcher.requests.get")
def test_search_sorts_by_citation_count_desc(mock_get):
    """Without explicit sort, S2's relevance ranking returns sparse results.

    The fetcher MUST send sort=citationCount:desc so the citation floor
    doesn't waste a page on low-citation noise.
    """
    mock_get.return_value = _ok_response({"data": []})
    cfg = CitationsConfig(enabled=True)
    th = ThresholdsConfig(older_works_per_digest=5)
    discover_older_works(cfg, th, sub_domains=["quantization"])

    params = mock_get.call_args.kwargs["params"]
    assert params["sort"] == "citationCount:desc"


@patch("paper_agent.fetcher.older_works_fetcher.requests.get")
def test_search_page_size_from_config(mock_get):
    """older_works_search_page_size controls the limit param sent to S2."""
    mock_get.return_value = _ok_response({"data": []})
    cfg = CitationsConfig(enabled=True, older_works_search_page_size=50)
    th = ThresholdsConfig(older_works_per_digest=5)
    discover_older_works(cfg, th, sub_domains=["serving"])

    params = mock_get.call_args.kwargs["params"]
    assert params["limit"] == 50


@patch("paper_agent.fetcher.older_works_fetcher.requests.get")
def test_search_uses_multiple_keyword_variants(mock_get):
    """Each sub-domain queries up to N keyword variants from SUB_DOMAINS."""
    mock_get.return_value = _ok_response({"data": []})
    cfg = CitationsConfig(enabled=True, older_works_keywords_per_sub_domain=4)
    th = ThresholdsConfig(older_works_per_digest=5)

    # quantization has many variants in SUB_DOMAINS; capped at 4 here.
    discover_older_works(cfg, th, sub_domains=["quantization"])

    # 4 separate search calls, each with a different query string.
    assert mock_get.call_count == 4
    queries = [c.kwargs["params"]["query"] for c in mock_get.call_args_list]
    assert "quantization" in queries
    assert len(set(queries)) == 4  # all distinct


@patch("paper_agent.fetcher.older_works_fetcher.requests.get")
def test_unknown_sub_domain_falls_back_to_bare_name(mock_get):
    """A sub-domain not in SUB_DOMAINS dict still queries with its name."""
    mock_get.return_value = _ok_response({"data": []})
    cfg = CitationsConfig(enabled=True, older_works_keywords_per_sub_domain=3)
    th = ThresholdsConfig(older_works_per_digest=5)

    discover_older_works(cfg, th, sub_domains=["totally_made_up_domain"])

    assert mock_get.call_count == 1
    assert mock_get.call_args.kwargs["params"]["query"] == "totally made up domain"


# ─── failure modes ───


@patch("paper_agent.fetcher.older_works_fetcher.requests.get")
def test_http_error_returns_empty_no_raise(mock_get):
    mock_get.return_value = _err_response()
    cfg = CitationsConfig(enabled=True)
    th = ThresholdsConfig(
        older_works_per_digest=5,
        min_citations_for_older_works=100,
    )
    result, source_map, citation_map = discover_older_works(cfg, th, sub_domains=["quantization"])
    assert result == []
    assert source_map == {}
    assert citation_map == {}


@patch("paper_agent.fetcher.older_works_fetcher.requests.get")
def test_request_exception_returns_empty(mock_get):
    import requests as _r

    mock_get.side_effect = _r.Timeout()
    cfg = CitationsConfig(enabled=True)
    th = ThresholdsConfig(
        older_works_per_digest=5,
        min_citations_for_older_works=100,
    )
    result, source_map, citation_map = discover_older_works(cfg, th, sub_domains=["quantization"])
    assert result == []
    assert source_map == {}
    assert citation_map == {}
