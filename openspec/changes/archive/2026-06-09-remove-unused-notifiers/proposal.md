## Why

Paper Agent 已支持通过 Web 表单订阅 + 全局 SMTP 邮件推送作为主要通知方式，飞书、企业微信、钉钉等 webhook 通知器的使用价值已大幅降低。同时，多用户（`users` 列表）配置模式与订阅系统功能重合，增加了配置复杂度。本次重构旨在大幅精简代码，移除非核心通知渠道和多用户静态配置，降低维护成本。

## What Changes

- **BREAKING**: 移除 `WeComNotifier`、`FeishuNotifier`、`DingTalkNotifier` 及其对应配置类
- **BREAKING**: 移除 `config.yaml` 中的 `users` 列表，改为单用户模式+邮件订阅用户的组合
  - 原有 `users` 中的 `thresholds`（评分阈值）合并到全局配置
  - 原有 `users` 中的 `subscriptions.sub_domains` 改为全局配置（供 arXiv 搜索关键词使用，配合 Web UI 按子领域过滤）
- **BREAKING**: 精简 `UserNotifyConfig`，仅保留 `email` 字段（移除 `wecom`/`feishu`/`dingtalk`）
- **BREAKING**: 移除 `cli.py` 中 `test` 命令的 `wecom`/`feishu`/`dingtalk` 选项，简化为仅支持 email
- 移除 `notifier/__init__.py` 中的 3 个通知器注册和工厂逻辑
- 清理 `config.example.yaml`，移除废弃的 notifier 示例用户和多用户示例
- 删除 `notifier/dingtalk_notifier.py`、`notifier/feishu_notifier.py`、`notifier/wecom_notifier.py`
- 同步更新 `README.md`、`CLAUDE.md` 及相关测试文件
- 确保 Web UI 和管理员看板不受影响

## Capabilities

### New Capabilities
（无新增能力）

### Modified Capabilities
- `global-email-config`: 移除对多用户和 wecom/feishu/dingtalk 通知器的依赖
- `subscription-storage`: 明确订阅系统与配置系统中用户信息的关系

## Impact

- **删除文件**: `dingtalk_notifier.py`、`feishu_notifier.py`、`wecom_notifier.py`
- **修改文件**: `config.py`、`notifier/__init__.py`、`cli.py`、`pipeline.py`、`subscriptions.py`、`web/app.py`、`web/routes.py`、`web/admin.py`、`web/deps.py`、`storage/database.py`、`config.example.yaml`、`README.md`、`CLAUDE.md`
- **测试文件**: 相关测试文件需要同步调整
- **依赖变化**: 无需新增依赖；可移除 unused imports