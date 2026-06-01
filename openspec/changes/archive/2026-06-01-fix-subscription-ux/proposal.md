## Why

订阅功能存在两个影响用户体验的 bug：(1) 表单提交时浏览器弹出令人困惑的验证对话框"如果要继续，请选中..."，用户不清楚发生了什么；(2) 订阅用户无法收到推送邮件，因为创建订阅用户时未配置 SMTP 凭据（smtp_user、smtp_password、sender），导致邮件发送静默失败。这两个问题在 subscription-signup 功能刚上线后立即被发现，需要紧急修复。

## What Changes

- **修复表单验证体验**：移除 checkbox 的 `required` 属性（该属性在多个同名 checkbox 上会导致浏览器显示令人困惑的验证消息），改用 JavaScript 进行客户端验证，提供更清晰的错误提示
- **添加全局邮件配置**：在 `AppConfig` 顶层新增 `email` 配置节，集中管理 SMTP 凭据（smtp_host、smtp_port、smtp_user、smtp_password、sender），所有订阅用户共享此配置
- **订阅用户继承 SMTP 配置**：创建订阅用户时，从全局邮件配置复制 SMTP 凭据到用户的 `notify.email` 配置中
- **改进订阅成功反馈**：在订阅成功后明确提示用户"我们将使用配置好的邮箱发送推送"，增强用户信心

## Capabilities

### New Capabilities
- `global-email-config`: 全局邮件 SMTP 配置管理，集中存储 smtp_host、smtp_port、smtp_user、smtp_password、sender 等凭据

### Modified Capabilities
- `subscription-form`: 移除 checkbox 的 required 属性，改用 JavaScript 验证；改进成功反馈消息
- `subscription-storage`: 创建订阅用户时从全局配置复制 SMTP 凭据

## Impact

- **配置结构**：`config.yaml` 需要新增 `email:` 顶层配置节（可选，向后兼容）
- **数据库**：无变更
- **Web UI**：订阅表单的验证逻辑和成功提示文案
- **邮件发送**：订阅用户现在能正确收到推送邮件
- **现有用户**：不受影响，继续使用各自配置的 SMTP 凭据（如果有的话）
