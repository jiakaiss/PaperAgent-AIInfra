## 1. Dead code cleanup (models.py)

- [x] 1.1 Remove `KEYWORD_TO_SUB_DOMAIN` reverse mapping and its build loop from `models.py`
- [x] 1.2 Remove `get_all_sub_domain_keywords()` function from `models.py`
- [x] 1.3 Update `ScoredPaper.total_score` docstring to mark as legacy and recommend `compute_total_score`
- [x] 1.4 Remove any test cases that reference removed symbols

## 2. Database row conversion dedup (storage/database.py)

- [x] 2.1 Refactor `load_cached_papers` to call `_row_to_scored_paper` instead of inline conversion
- [x] 2.2 Verify `list_papers` already uses `_row_to_scored_paper` (no change needed if so)
- [x] 2.3 Run `pytest tests/test_storage.py` to verify no regressions

## 3. Notifier factory registry (notifier/__init__.py)

- [x] 3.1 Define `_REGISTRY` dict mapping notifier names to (class, config_attr) tuples
- [x] 3.2 Rewrite `create_notifiers_for_user` to iterate over `_REGISTRY`
- [x] 3.3 Rewrite `get_notifier_by_name` to look up in `_REGISTRY`
- [x] 3.4 Run `pytest tests/test_pipeline.py` to verify notifier creation still works

## 4. ClaudeScorer constructor simplification (scorer/claude_scorer.py)

- [x] 4.1 Move `_SafeFormatter` class from inside `_build_user_message` to module level
- [x] 4.2 Replace per-field ternary chain in `__init__` with dict-merge pattern
- [x] 4.3 Verify `__init__` resolution body is under 20 lines
- [x] 4.4 Run `pytest tests/test_scorer.py` to verify behavior equivalence

## 5. Verification and cleanup

- [x] 5.1 Run full test suite: `pytest tests/ -v`
- [x] 5.2 Run linter: `ruff check src/ tests/`
- [x] 5.3 Run formatter: `ruff format src/ tests/`
- [x] 5.4 Manual smoke test: `paper-agent stats -c config.yaml`
