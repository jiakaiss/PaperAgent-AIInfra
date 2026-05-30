## Why

偏好设置面板中有 14 个子领域 checkbox，用户想全部选中时需要逐个点击 14 次。添加「全选/取消全选」按钮可以一键操作，提升配置效率。

## What Changes

- **前端**: 在偏好设置面板的子领域 checkbox 区域添加「全选」和「取消全选」按钮
- **前端**: 点击「全选」时选中所有 14 个子领域 checkbox，更新 `paper_agent_prefs.subDomains`，同步 chip 状态并刷新论文列表
- **前端**: 点击「取消全选」时取消所有 checkbox 选中状态，清空 `subDomains`，同步 UI 并刷新论文列表

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `user-preferences`: 偏好设置面板新增「全选」和「取消全选」按钮，Preferences JS module 新增 `selectAllSubDomains()` 和 `clearAllSubDomains()` 方法

## Impact

- **前端模板**: `src/paper_agent/web/templates/index.html` — 偏好设置面板中添加按钮
- **前端 JS**: `src/paper_agent/web/static/preferences.js` — 新增全选/清空方法
- **前端 JS**: `src/paper_agent/web/static/app.js` — 绑定按钮事件
- **测试**: `tests/js/preferences.test.mjs` — 新增全选/清空的 JS 单元测试
- **无后端改动** — 纯前端功能
