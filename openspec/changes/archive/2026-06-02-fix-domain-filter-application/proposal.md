## Why

用户在页面上选择感兴趣领域后，论文列表仍展示全量数据，导致筛选功能失效。这个问题直接影响论文浏览体验，也会让用户误以为订阅/偏好设置没有生效，需要修复前端偏好状态到 HTMX 请求参数、服务端过滤结果、以及 UI 状态展示之间的一致性。

## What Changes

- 修复领域筛选请求链路：确保用户选择 sub-domain 后，`/_paper_list` 请求包含正确的 `sub_domain` query 参数
- 修复自定义模式逻辑：当用户选择具体领域时，应自动进入或保持 `custom` 模式，避免 `all` 模式覆盖筛选
- 修复服务端过滤保障：`routes.py` 必须将 query 参数转为 `set[str]` 并传给 `PaperDatabase.list_papers()` / `count_papers()`
- 增加可观察测试：覆盖 chip 点击、checkbox 切换、localStorage 偏好、URL query、HTMX fragment 返回数量之间的一致性
- 改进空选择行为：custom 模式下无领域选择时，应显示空状态提示，而不是退回全量数据

## Capabilities

### New Capabilities
None

### Modified Capabilities
- `paper-browsing`: 确保 `sub_domain` 查询参数在页面和片段端点中真正限制返回结果
- `user-preferences`: 确保 localStorage 中的 custom mode/subDomains 状态会稳定转换为请求参数，并且 UI 与结果同步

## Impact

- **Frontend JS**: `preferences.js` / `app.js` 中构建 HTMX URL、chip/checkbox 状态同步、mode 切换逻辑
- **Web routes**: `/` 和 `/_paper_list` 对 `sub_domain` 参数的解析和传递
- **Templates**: 空状态或筛选提示可能需要调整
- **Tests**: 增加/修复 Web browsing 和 JS 测试，防止筛选回归
