## Why

订阅页 `/subscribe` 的「感兴趣的领域」checkbox 网格目前排版不整齐：长 tag（`distributed_training`、`speculative_decoding`、`memory_optimization`）在 180px 列宽里塞不下，导致 checkbox 和文字换行，文字被挤到 checkbox 下方；短 tag（`moe`、`pruning`）则横向排开。结果是同一个列表里有些 chip 文字在 checkbox 右边、有些在下边，视觉上参差不齐，给用户「页面没做完」的印象。

根因是订阅页 `.subscribe-container` 被限制在 `max-width: 600px`，留给 3 列 grid 的每列只有 ~180px，撑不下 20 字符的长 tag。

## What Changes

- 把 `.subscribe-container` 的 `max-width` 从 `600px` 放宽到 `820px`（其它页面浏览页 `.container` 不动）
- 让 `.sub-domain-grid` 在订阅页放宽后的宽度下，每列至少 220px，确保 `distributed_training` / `speculative_decoding` 这种最长 tag 也能横排不换行
- 单 chip 内部 `.checkbox-card` 增加 `flex-wrap: nowrap` + `white-space: nowrap`，保证不会因为文本意外溢出而再次换行（即使将来加新 tag）
- 同步检查移动端窄屏下的退化（≤768px 仍单列），保证不影响小屏可用性

不变更内容：
- 不改 sub-domain 集合本身（仍是 `paper_agent.models.SUB_DOMAINS` 的 14 项）
- 不加中文别名，tag 仍英文原样展示
- 不动浏览页 `/`、不动 base 容器宽度

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `subscription-form`: 「checkbox 排版必须整齐一致」作为新增可验证要求，加入到表单的呈现层规约

## Impact

- 受影响代码：`src/paper_agent/web/static/style.css`（仅订阅页相关选择器）
- 不受影响：模板 `subscribe.html`、其它页面、路由、API、数据库、配置
- 无 BREAKING 变更
