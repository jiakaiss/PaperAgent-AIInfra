## Context

订阅页 `/subscribe` 的容器与 checkbox 网格当前样式（`src/paper_agent/web/static/style.css`）：

```css
.subscribe-container { max-width: 600px; padding: var(--spacing-xl); … }

.sub-domain-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: var(--spacing-sm);
}

@media (min-width: 1024px) {
  .sub-domain-grid { grid-template-columns: repeat(3, 1fr); }
}

.checkbox-card { display: flex; align-items: center; gap: var(--spacing-sm); padding: …; }
```

14 个 sub-domain 长度跨度 3–20 字符。容器 600px、3 列等宽时每列 ~180px，其中 padding 与 checkbox 占去约 50px，留给文字只剩 ~130px。`distributed_training`、`speculative_decoding`、`memory_optimization` 在默认字号下渲染宽度 ≥130px，触发文字换行到 checkbox 下方。

## Goals / Non-Goals

**Goals:**
- 14 个 sub-domain chip 在桌面端布局完全一致：每个 chip 都是「checkbox 在左、文字在右、同一行」
- 拓宽订阅页容器，仅作用于 `/subscribe`，不影响浏览页
- 改动尽量小、可逆，纯 CSS

**Non-Goals:**
- 不引入新设计语言、不重构组件、不改 base color/spacing 变量
- 不动 `subscribe.html` 模板结构（避免影响已上线的两条订阅规则文案区块）
- 不做 sub-domain 中文别名映射
- 不动浏览页 `/` 的布局

## Decisions

### 决策 1：容器宽度 `max-width: 600px` → `820px`

- 600px 是当前问题根因，必须放宽
- 选 820px 而不是 1000px+ 的理由：订阅是「读两句规则、填邮箱、勾几个领域、按按钮」的轻型表单，宽度太大反而让表单字段在大屏上拉得很长，输入框看着空旷，影响成行可读性
- 820px 下 3 列 grid 每列约 245px（减去 container padding 与 grid gap 后），最长 tag `distributed_training` ≈ 160-170px，留有富余

### 决策 2：grid 用 `repeat(auto-fit, minmax(220px, 1fr))` 替换硬编码 `repeat(3, 1fr)`

- 取消 `@media (min-width: 1024px) { repeat(3, 1fr); }` 这条硬列数规则
- 改用 `auto-fit + minmax(220px, 1fr)`，效果：
  - 820px 容器下自动算出 3 列
  - 中等屏 (`768–1023px`) 自动 2-3 列
  - 移动 (<768px) 自动 1-2 列（仍由 `.sub-domain-grid { grid-template-columns: 1fr; }` 媒体规则兜底）
- 优点：未来加 sub-domain 不用调列数；任何宽度下「每列至少 220px」保证长 tag 不换行

备选：保留 `repeat(3, 1fr)` 但只在 ≥820px 启用。否决理由：硬编码与容器宽度耦合，未来调容器宽度容易忘记同步。

### 决策 3：`.checkbox-card` 文本不换行兜底

加 `flex-wrap: nowrap`（防 checkbox 和文字分行）和 `white-space: nowrap`（防文字内部断词），保证哪怕某个新加的 tag 名意外很长也不会破坏排版（最差情况是文字被 `overflow` 隐藏，仍然每行只有 checkbox + 文字一行）。

不加 `overflow: hidden + text-overflow: ellipsis`：当前 14 个 tag 在 220px 列宽下都装得下，省略号反而会让用户看不清完整名字；如果将来真的有更长 tag，再补也来得及。

### 决策 4：移动端保持现有规则不动

`@media (max-width: 768px) { .sub-domain-grid { grid-template-columns: 1fr; } .subscribe-container { padding: var(--spacing-lg); } }` 已经能在窄屏单列堆叠。`max-width: 820px` 比窗口宽就自动靠 `width: auto` + padding 退化，没有副作用。

## Risks / Trade-offs

- [820px 比 600px 视觉感受变化大] → 实际看起来是「表单变宽松」而不是「页面变拥挤」，因为 max-width 仍远小于浏览页正文区。如果上线后觉得过宽，把 820 调到 720 即一行 CSS 改动。
- [`auto-fit + minmax(220px)` 在 820px 下取整为 3 列没问题，但 880-1000px 之间会变成 4 列] → 由于订阅页 max-width 锁在 820px，`.sub-domain-grid` 实际可用宽度不会超过 ~750px，触发不到 4 列。安全。
- [删除 `@media (min-width: 1024px) { repeat(3, 1fr); }` 是否影响别的页面] → 这条规则只匹配 `.sub-domain-grid` 类，且该类只在订阅模板里使用。grep 确认无副作用。
