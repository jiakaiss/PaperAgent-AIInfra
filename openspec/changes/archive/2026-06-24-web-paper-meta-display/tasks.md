## 1. Template changes (`src/paper_agent/web/templates/_paper_list.html`)

- [x] 1.1 Wrap the tier badge, older-works badge, and citation badge in a single `<div class="paper-card-header-badges">…</div>` inside `.paper-card-header`.
- [x] 1.2 Remove the `{% if sp.citation_count and sp.citation_count > 0 %}` guard around the citation badge so it ALWAYS renders. Badge text becomes `📈 {{ sp.citation_count or 0 }} citations` (handles `None` from very-legacy rows safely).
- [x] 1.3 In the authors paragraph, append a `<span class="paper-published">· {{ sp.paper.published.strftime('%Y-%m-%d') }}</span>` after the authors text. Confirm `Paper.published` is always populated (it is `datetime` and non-optional per `src/paper_agent/models.py:181`).

## 2. CSS changes (`src/paper_agent/web/static/style.css`)

- [x] 2.1 Add `.paper-card-header-badges { display: inline-flex; gap: 0.25rem; align-items: center; flex-shrink: 0; }`.
- [x] 2.2 Remove the `margin-left: 4px` from `.citation-badge` and `.paper-kind-badge` (the cluster `gap` now governs inter-badge spacing — keeping the margins would make spacing inconsistent depending on which badges are present).
- [x] 2.3 Add `.paper-published { color: var(--color-text-muted); font-size: 0.82rem; margin-left: 0.25rem; }` (or co-locate with `.paper-authors` styling). Verify it renders as inline next to the authors.
- [x] 2.4 Sanity-check the responsive `@media (max-width: 768px)` block — the new badge cluster should still wrap cleanly when the title is long on narrow screens (no change expected, just visual verification).

## 3. Tests

- [x] 3.1 In `tests/test_web_browsing.py` (or `test_web_app.py`, whichever already covers card rendering), add a test asserting that a paper with `citation_count=0` renders the `📈 0 citations` badge in the HTML response of `/_paper_list`.
- [x] 3.2 Add a test asserting the formatted `YYYY-MM-DD` published date appears in the paper card HTML for a paper with a known `published` datetime.
- [x] 3.3 Update any existing test that previously asserted the absence of a citation badge for `citation_count=0` papers (search the test files for `citation_count` and `citations` in assertions).
- [x] 3.4 Add a test asserting the header badge cluster wrapper (`paper-card-header-badges`) exists in the rendered card for both the "older + citation + tier" case and the "citation + tier only" case.

## 4. Validation

- [x] 4.1 Run `pytest tests/test_web_browsing.py tests/test_web_app.py -v` and ensure all tests pass.
- [x] 4.2 Run `ruff check src/ tests/` and `ruff format --check src/ tests/`.
- [x] 4.3 Manually launch `paper-agent web -c config.yaml`, load `/`, and visually verify: (a) every card shows a published date, (b) every card shows a citation badge including `0`, (c) badges are tightly clustered and right-aligned uniformly across cards with varying title length and varying badge sets.
- [x] 4.4 Run `openspec validate web-paper-meta-display --strict` and confirm the change validates cleanly.
