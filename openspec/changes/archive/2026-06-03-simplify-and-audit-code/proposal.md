## Why

近期连续加入了 Web 订阅、邮件配置、筛选偏好、UI 改造等功能，代码路径变多且跨越 config、storage、routes、templates、static JS/CSS 和测试。需要做一次聚焦的简化与审计，降低维护成本，同时捕获明显 bug（如参数格式不一致、配置继承不一致、前端状态与请求不同步）。

## What Changes

- 审计并简化 Web 订阅链路：`config.email` → subscription API → database → `UserConfig` → notifier，消除重复的 SMTP 配置复制/校验逻辑
- 审计并简化前端筛选链路：localStorage preferences → chip/checkbox/radio state → HTMX URL → `/_paper_list` 结果，抽取单一 URL 构建/状态同步入口
- 清理近期引入的重复测试辅助代码，统一测试 fixture 和 helper，减少脆弱测试
- 修复审计中发现的高置信 bug；若发现需要需求变更的行为，先在 spec 中明确再实现
- 保持外部行为不变（除非修复明确 bug）：订阅、邮件、筛选、浏览 API 不做破坏性修改

## Capabilities

### New Capabilities
- `code-audit-cleanup`: 定义代码简化与 bug 审计的可验证流程，覆盖重复逻辑清理、状态链路一致性、配置继承一致性和测试覆盖要求

### Modified Capabilities
- `global-email-config`: 明确全局邮件配置校验和订阅用户 SMTP 继承应使用单一 helper，避免 app.py/routes.py/cli.py 重复实现
- `user-preferences`: 明确前端偏好状态变更和 HTMX URL 构建应通过单一模块入口完成，避免 chip/checkbox/search/time range 分叉逻辑不一致
- `subscription-storage`: 明确订阅到 UserConfig 的转换应集中实现，避免启动加载和运行时新增使用不同逻辑

## Impact

- **Config / subscriptions**: `config.py`, `web/app.py`, `web/routes.py`, `cli.py` 可能抽取共享 helper
- **Frontend filtering**: `web/static/preferences.js`, `web/static/app.js` 可能简化状态同步与 URL 构建
- **Tests**: `tests/test_subscription_api.py`, `tests/test_subscription_storage.py`, `tests/js/preferences.test.mjs` 可能抽取 fixtures/helper
- **Specs**: 新增 `code-audit-cleanup`，并对相关能力进行小范围需求澄清
