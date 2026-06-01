## Why

代码审查发现多处重复逻辑、过度复杂的初始化模式、以及未使用的死代码。这些问题降低了可读性，增加了维护成本，也容易在修改时引入不一致。趁现在代码规模还小，做一次系统性精简，为后续功能迭代打好基础。

## What Changes

- **消除 database.py 中的行转换重复**：`load_cached_papers` 和 `_row_to_scored_paper` 各自实现了几乎相同的 row → ScoredPaper 转换逻辑，统一为一个方法
- **简化 ClaudeScorer 构造函数**：当前 `__init__` 有 9 个参数，每个都用 `x if x is not None else config.x` 模式，可以用 dataclass 或合并策略精简
- **移除 SafeFormatter 内联定义**：`_build_user_message` 内部定义了 `_SafeFormatter` 类，应提升为模块级或用更简洁的方案替代
- **统一 notifier 工厂模式**：`create_notifiers_for_user` 和 `get_notifier_by_name` 都用 if-chain，改为注册表映射
- **清理死代码**：`KEYWORD_TO_SUB_DOMAIN` 反向映射和 `get_all_sub_domain_keywords()` 函数未被使用，移除
- **明确 ScoredPaper.total_score 的定位**：当前 property 硬编码 0.6/0.4，与 `ScoreWeights` 并存造成混淆，标记为向后兼容并推荐使用 `compute_total_score`

## Capabilities

### New Capabilities
- `code-dedup`: 消除模块内重复代码（database row 转换、notifier 工厂）
- `init-simplify`: 简化 ClaudeScorer 构造函数的参数处理逻辑
- `dead-code-cleanup`: 移除未使用的代码和过时的兼容层

### Modified Capabilities
- `llm-api-config`: ClaudeScorer 构造方式变更（外部行为不变，内部简化）

## Impact

- **src/paper_agent/storage/database.py**: 合并两处 row 转换逻辑，减少约 20 行重复代码
- **src/paper_agent/scorer/claude_scorer.py**: 构造函数从 ~40 行减至 ~15 行；移除内联类定义
- **src/paper_agent/notifier/__init__.py**: if-chain 替换为 dict 映射
- **src/paper_agent/models.py**: 移除未使用的 `KEYWORD_TO_SUB_DOMAIN` 和 `get_all_sub_domain_keywords`
- **tests/**: 需要更新/移除测试死代码的用例；新增测试验证简化后的行为不变
