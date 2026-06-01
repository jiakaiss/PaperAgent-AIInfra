## Requirements

### Requirement: Unused reverse keyword mapping removed
The module-level dict `KEYWORD_TO_SUB_DOMAIN` (keyword → sub-domain reverse lookup) SHALL NOT exist in `models.py`, as it is not referenced by any production or test code.

#### Scenario: KEYWORD_TO_SUB_DOMAIN not importable
- **WHEN** code attempts `from paper_agent.models import KEYWORD_TO_SUB_DOMAIN`
- **THEN** an `ImportError` is raised

#### Scenario: models.py does not build reverse mapping at import time
- **WHEN** `paper_agent.models` is imported
- **THEN** no iteration over `SUB_DOMAINS` to build a reverse mapping occurs during module initialization

### Requirement: Unused get_all_sub_domain_keywords function removed
The function `get_all_sub_domain_keywords()` SHALL NOT exist in `models.py`, as it is not called by any production or test code.

#### Scenario: Function not importable
- **WHEN** code attempts `from paper_agent.models import get_all_sub_domain_keywords`
- **THEN** an `ImportError` is raised

#### Scenario: Equivalent one-liner available
- **WHEN** a flat list of all sub-domain keywords is needed
- **THEN** callers can use `[kw for kw_list in SUB_DOMAINS.values() for kw in kw_list]` directly

### Requirement: ScoredPaper.total_score marked as legacy
`ScoredPaper.total_score` property SHALL remain for backward compatibility but its docstring SHALL direct users to `compute_total_score(paper, weights)` for configurable weight support.

#### Scenario: total_score still works with default weights
- **WHEN** `paper.total_score` is accessed on a `ScoredPaper` instance
- **THEN** it returns `relevance_score * 0.6 + quality_score * 0.4` (unchanged behavior)

#### Scenario: Docstring recommends compute_total_score
- **WHEN** a developer reads the docstring of `ScoredPaper.total_score`
- **THEN** the docstring mentions that `compute_total_score(paper, weights)` should be used when configurable weights are needed
