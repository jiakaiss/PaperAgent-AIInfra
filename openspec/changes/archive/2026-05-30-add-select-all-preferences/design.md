## Context

偏好设置面板（`index.html` 中的 `<aside id="preferences-panel">`）目前包含：
- 浏览模式切换（全量论文 / 自定义领域）
- 14 个子领域 checkbox，由 `all_sub_domains` 模板变量渲染

用户想全部选中时需要手动点击 14 次。`preferences.js` 已有 `setSubDomains(tags)` 方法可以一次性设置所有选中的子领域。

## Goals / Non-Goals

**Goals:**
- 一键全选所有 14 个子领域
- 一键取消全选（清空所有子领域）
- 全选/取消后自动同步 chip 状态、checkbox 状态、localStorage、论文列表
- 按钮样式与现有 UI 一致

**Non-Goals:**
- 不做「反选」（toggle 每个 checkbox 的状态）— 用户需求是全部选中或全部取消
- 不做「记住上次选择」— 当前 localStorage 已经持久化了 subDomains，刷新后状态不丢失

## Decisions

### 1. 两个独立按钮 vs 一个 toggle 按钮

**Decision:** 使用两个独立按钮「全选」和「取消全选」。

**Alternatives considered:**
- *一个 toggle 按钮*（文字在全选/取消之间切换）：逻辑更复杂，需要判断当前是全选还是部分选中状态来决定显示哪个文字。
- *一个 checkbox*（「全选」checkbox）：和下面的 checkbox 列表视觉上混淆。

**Rationale:** 两个按钮语义清晰，操作简单，实现成本低。

### 2. 按钮位置

**Decision:** 放在子领域 checkbox 区域上方，「浏览模式」和「关注领域」之间。

**Rationale:** 用户看到「关注领域」标题后，第一反应是操作这些 checkbox，全选/取消按钮在列表上方最容易发现。

### 3. 复用 setSubDomains()

**Decision:** 全选调用 `setSubDomains(allTags)`，取消调用 `setSubDomains([])`。不新增独立方法。

**Rationale:** `setSubDomains()` 已经处理了校验、持久化、UI 同步和列表刷新，直接复用即可。只需要暴露 `getValidSubDomains()` 来获取全部有效 tag 列表（已在 `window.PaperAgentPrefs` 中暴露）。

### 4. 事件绑定方式

**Decision:** 在模板中使用 `onclick` 内联调用，和现有 chip 按钮保持一致。

```html
<button onclick="PaperAgentPrefs.setSubDomains(PaperAgentPrefs.getValidSubDomains())">全选</button>
<button onclick="PaperAgentPrefs.setSubDomains([])">取消全选</button>
```

**Rationale:** 无需修改 `app.js` 添加事件监听，保持简单。

## Risks / Trade-offs

- **[全选后论文列表为空]** 在 custom 模式下全选 14 个子领域等价于全量模式。 → Mitigation: 可接受，用户可以切换回「全量论文」模式。
- **[按钮样式]** 需要确保按钮在偏好设置面板中不显得突兀。 → Mitigation: 使用现有的 `.btn .btn-sm` 样式。
