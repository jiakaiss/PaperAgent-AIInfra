## Context

当前代码库整体结构清晰，但在以下几个地方出现了"演化痕迹"——重复逻辑、过度防御性的参数处理、以及功能迭代后遗留的死代码。这些问题不影响功能，但会在后续开发中增加认知负担和引入不一致的风险。

主要受影响模块：
- `storage/database.py`：两处 row → ScoredPaper 转换
- `scorer/claude_scorer.py`：构造函数参数处理、内联类
- `notifier/__init__.py`：工厂 if-chain
- `models.py`：未使用的反向映射和辅助函数

## Goals / Non-Goals

**Goals:**
- 消除重复代码，让每段逻辑只存在一份
- 简化构造函数，降低阅读门槛
- 移除死代码，减少维护时的困惑
- 保持所有外部行为不变（API、CLI、web 均无感知）

**Non-Goals:**
- 不引入新的架构模式（如依赖注入框架）
- 不改变配置格式或数据库 schema
- 不重构 pipeline 的整体流程
- 不添加新功能

## Decisions

### 1. database.py：统一 row 转换

**决定**：让 `load_cached_papers` 调用已有的 `_row_to_scored_paper`，而非重复实现转换逻辑。

**理由**：两处代码几乎完全相同（字段解析、datetime 转换、json.loads），唯一差别是 `load_cached_papers` 在循环内完成转换。统一后只需维护一份逻辑。

**替代方案**：
- 引入 `@dataclass` 的 `from_row` 类方法——但 Paper/ScoredPaper 是 `frozen=True` dataclass，加方法会让 models.py 依赖 sqlite3，破坏分层。

### 2. ClaudeScorer 构造函数简化

**决定**：保留 `config` + kwargs 的接口签名，但用 dict-merge 模式替代逐字段的三元表达式。

```python
# Before (9 行重复模式)
api_key = api_key if api_key is not None else config.api_key
...

# After
overrides = {k: v for k, v in kwargs.items() if v is not None}
resolved = {**config.__dict__, **overrides}
```

**理由**：行为完全等价，但代码量减少约 60%。保留 kwargs 接口以兼容测试代码的直接调用。

**替代方案**：
- 改用 `pydantic.BaseModel` 做参数合并——过度工程，构造函数不是热路径，不值得引入额外依赖。
- 移除 kwargs 只保留 config——破坏现有测试和 CLI 的直接调用方式。

### 3. SafeFormatter 提升为模块级

**决定**：将 `_SafeFormatter` 从 `_build_user_message` 内部提升到模块级，重命名为 `_SafeFormatter`。

**理由**：内联类定义让 `_build_user_message` 方法体变长且难以快速理解。模块级定义更符合 Python 惯例，也便于测试。

### 4. Notifier 工厂改为注册表

**决定**：用 dict 映射替代 if-chain。

```python
# Before
if config.email.enabled: notifiers.append(EmailNotifier(config.email))
if config.wecom.enabled: notifiers.append(WeComNotifier(config.wecom))
...

# After
_REGISTRY: dict[str, tuple[type[Notifier], str]] = {
    "email": (EmailNotifier, "email"),
    "wecom": (WeComNotifier, "wecom"),
    ...
}
for name, (cls, attr) in _REGISTRY.items():
    sub_config = getattr(config, attr)
    if sub_config.enabled:
        notifiers.append(cls(sub_config))
```

**理由**：新增 notifier 时只需在 `_REGISTRY` 加一行，不用在两个函数里各加一个 if 分支。`create_notifiers_for_user` 和 `get_notifier_by_name` 共享同一个注册表。

### 5. 移除死代码

**决定**：删除 `KEYWORD_TO_SUB_DOMAIN` 和 `get_all_sub_domain_keywords()`。

**理由**：通过全仓库搜索确认两者均未被调用（测试除外）。保留死代码会让新贡献者误以为它们有用途。

**迁移**：测试中引用这两个符号的用例直接删除。

### 6. ScoredPaper.total_score 标记为向后兼容

**决定**：保留 property，但在 docstring 中明确标注"使用 `compute_total_score(paper, weights)` 代替"。

**理由**：`total_score` 被 `sort_by_score` 在无 weights 参数时使用，删除会破坏向后兼容。添加 deprecation 提示即可。

## Risks / Trade-offs

- **[风险] Notifier 注册表重构引入 bug** → 现有测试覆盖四种 notifier 的启用/禁用逻辑，重构后运行 `pytest tests/test_pipeline.py` 验证。
- **[风险] ClaudeScorer 构造简化改变参数优先级** → 用 dict-merge 时 kwargs 覆盖 config 值，与现有行为一致。增加单元测试覆盖 `config=X, api_key=Y` 的场景。
- **[Trade-off] 不引入 DI 框架** → 代码简化程度有限，但避免了新依赖和学习成本，符合项目"轻量工具"定位。
- **[Trade-off] total_score 不删除只标注** → 保留了一点技术债，但避免了破坏性变更。后续大版本可考虑移除。
