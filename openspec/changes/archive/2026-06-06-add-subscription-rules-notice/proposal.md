## Why

订阅页面目前没有告诉用户「什么时候会收到推送」以及「14 个标准子领域之外能不能添加新方向」。结果是：用户提交后不知道下一封邮件何时到达，遇到自己关心但列表里没有的方向时也不知道该联系谁，体验上像「黑盒」，也增加了管理员收到「为什么还没收到推送」「能不能加 X 方向」类咨询的概率。

## What Changes

- 在 `/subscribe` 页面表单上方新增一块「订阅规则说明」区域，告知用户：
  - 推送时间：每天 09:00（Asia/Shanghai）从最新缓存中筛选一份个性化论文摘要并发送
  - 子领域范围：当前仅提供下方 14 个标准子领域，若有新的类别需求，请联系管理员添加
- 文案与现有表单视觉保持一致（沿用 `subscribe-description` / `form-hint` 的样式语言，避免引入新组件）
- 内容为纯静态展示，不引入新的后端字段、API 或配置项

## Capabilities

### New Capabilities
<!-- 无新增 capability -->

### Modified Capabilities
- `subscription-form`: 在订阅表单页新增「推送时间」与「联系管理员添加新类别」两条说明性要求

## Impact

- 受影响代码：`src/paper_agent/web/templates/subscribe.html`
- 可能受影响样式：`src/paper_agent/web/static/style.css`（如需为说明区块新增轻量样式）
- 无 API 变更、无数据库变更、无配置变更
- 无 BREAKING 变更
