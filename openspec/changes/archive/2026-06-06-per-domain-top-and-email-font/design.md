## Context

### 当前推送筛选逻辑（`pipeline.py:185-211`）

```python
# Filter by sub-domain tags
if "all" not in sub_domains:
    wanted = set(sub_domains)
    filtered = [sp for sp in all_scored if set(sp.sub_domain_tags) & wanted]
else:
    filtered = list(all_scored)

# Filter by thresholds
filtered = [
    sp for sp in filtered
    if sp.relevance_score >= user.thresholds.min_relevance
    and sp.quality_score >= user.thresholds.min_quality
]

# Sort and limit
filtered = sort_by_score(filtered, weights=self.score_weights)[: user.thresholds.top_n]
```

整个匹配集合按总分排序后截前 20。**问题**：如果 quantization 这周出 40 篇高分、distillation 只出 5 篇高分，订阅这两个方向的用户拿到的 20 篇可能全是 quantization，distillation 一篇都看不到。

### 当前邮件字体（`formatter/templates.py:104`）

```html
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
             sans-serif; max-width: 800px; margin: 0 auto; padding: 20px;">
```

中英文都用 sans-serif，对英文论文标题密集排版下，用户反馈"不好看"。

## Goals / Non-Goals

**Goals:**
- 每个订阅的 sub-domain 在每日推送中至少有机会被看到 top N 篇（默认 20）
- 同一篇踩多个 tag 的论文只算一次（合集去重）
- 英文用 Times New Roman、中文用微软雅黑，邮件客户端能正确按字符切换字体
- 改动可向后兼容：现有 `top_n` 字段语义保留，作为合集后的上限兜底

**Non-Goals:**
- 不重写整个 notifier 模块，仅改 email HTML 字体
- 不改 wecom/feishu/dingtalk notifier（它们走 markdown/纯文本，没有字体概念）
- 不改 web 浏览页字体（用户明确说只改邮件）
- 不引入 jinja2 模板文件（保留现有 f-string 风格，避免新依赖）
- 不动 `UserThresholdsConfig.top_n` 默认值（仍 20），仅新增 `per_sub_domain_top_n`

## Decisions

### 决策 1：per-domain 过滤算法 —— 分领域取 top，再合集去重

```python
if "all" not in sub_domains:
    # For each subscribed sub-domain, take its top-N
    per_domain_buckets = []
    for sd in sub_domains:
        bucket = [
            sp for sp in all_scored
            if sd in sp.sub_domain_tags
            and sp.relevance_score >= user.thresholds.min_relevance
            and sp.quality_score >= user.thresholds.min_quality
        ]
        bucket = sort_by_score(bucket, weights=self.score_weights)
        per_domain_buckets.extend(bucket[: user.thresholds.per_sub_domain_top_n])

    # Dedup (same paper may appear in multiple buckets)
    seen = set()
    filtered = []
    for sp in per_domain_buckets:
        if sp.paper.arxiv_id not in seen:
            seen.add(sp.paper.arxiv_id)
            filtered.append(sp)

    # Resort dedup'd list and apply user-level cap
    filtered = sort_by_score(filtered, weights=self.score_weights)[: user.thresholds.top_n]
else:
    # "all" subscribers: keep current behavior (no per-domain split possible)
    filtered = [
        sp for sp in all_scored
        if sp.relevance_score >= user.thresholds.min_relevance
        and sp.quality_score >= user.thresholds.min_quality
    ]
    filtered = sort_by_score(filtered, weights=self.score_weights)[: user.thresholds.top_n]
```

为何保留 `top_n` 全局上限：
- 防御性：订阅 14 个 sub-domain × 每域 20 篇 = 280 篇邮件，谁也不会看完
- 让操作员有手动封顶能力（如果某天论文炸出，仍能压住单封邮件长度）
- `top_n` 默认 20 太小，需要默认值改为更大（见决策 2）

### 决策 2：`top_n` 默认值改 20 → 200

`per_sub_domain_top_n=20` 默认下，14 个领域全订理论上限 280，全局兜底 200 比较合理（不会让"按领域取 top"的语义被 20 卡死）。常规 2-3 个领域订阅的用户取到 35-60 篇，远小于 200，兜底实际不触发。

**风险**：`top_n=20` 是现有用户的"预期数量"，改成 200 可能让某些用户突然收到更多邮件。
**处理**：
- `UserThresholdsConfig.top_n` 默认值改 200
- `SubscriptionDefaultsConfig.default_top_n` 保留 10（新订阅用户的默认值）—— 这两个字段语义本来就分开，subscription 新用户期望"少而精"，已配置用户期望"按 sub-domain 拿全"
- 在 proposal 里明确这条不算 BREAKING（因为按领域分桶后实际数量受 per_sub_domain_top_n 限制，而非 200）

备选：保持 `top_n=20` 不动，把 `per_sub_domain_top_n` 默认设小（如 8）。否决：用户明确说"每个领域 20 篇"，不能在桶内偷偷砍到 8。

### 决策 3：字体声明顺序 `'Times New Roman', 'Microsoft YaHei', '微软雅黑', serif`

CSS `font-family` 是按字符按优先级匹配（不是按整段文本）：
- 英文字符：浏览器/邮件客户端检查 Times New Roman 是否能渲染 → 能 → 用 Times
- 中文字符：Times 不含中文字形 → 回退到 'Microsoft YaHei' → Windows/部分 Mac 上能渲染 → 用雅黑
- Mac/Linux 上没装 Microsoft YaHei → 再回退到 '微软雅黑'（部分系统接受中文别名）→ 再不行就 `serif` 系统衬线（Mac 会回退到 PingFang / Songti，Linux 到 Noto Serif CJK）

写两遍雅黑（英文名 + 中文名）是因为部分中文 Windows 系统的 SMTP 邮件客户端只识别其中一种。

最后兜底 `serif`（不是 `sans-serif`），让英文部分即使 Times 不在也走衬线风格保持一致感。

### 决策 4：仅改 `<body>` 一处 `font-family`

`format_email_html` 中后续所有 `<table>`、`<td>`、`<a>`、`<div>`、`<span>` 都没显式 font-family，会继承 `<body>`。改一处足够。

`format_markdown`（用于 wecom/feishu/dingtalk）保持不动 —— webhook 平台不解析 CSS 字体。

## Risks / Trade-offs

- [per-domain 分桶后用户实际收到的论文数可能从 ~20 跳到 ~50+] → 是预期行为，用户明确要求"每个领域 20 篇"。`top_n=200` 兜底防止极端值。如有用户嫌多，可在 config.yaml 里单独把该用户的 `per_sub_domain_top_n` 调小。
- [部分老邮件客户端不支持 `font-family` 多重 fallback] → 这套写法是 1996 年 CSS1 标准，所有现代邮件客户端（Gmail Web/App、Outlook、QQ 邮箱、网易邮箱、Apple Mail）都支持。极老的客户端会忽略整条规则回退到默认，仍可读，不会出错。
- [测试覆盖] → `tests/test_pipeline.py` 已有 `test_pipeline_multi_user_filter` 类测试，需新增一个 `test_per_domain_top_n` 验证分桶+去重逻辑；email 字体改动靠目测验证 + 模板渲染包含字符串检测
- [BREAKING 风险] → 增字段 `per_sub_domain_top_n` 默认 20，`top_n` 默认 20→200。订阅 1 个领域的用户行为不变（20 篇）；订阅 N 个领域的用户邮件变长。这是用户要的效果，记为"行为变化"而非 BREAKING（无 API/配置不兼容）
