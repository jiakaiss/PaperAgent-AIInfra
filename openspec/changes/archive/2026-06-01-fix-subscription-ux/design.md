## Context

当前订阅功能存在两个 bug：

1. **表单验证体验差**：`subscribe.html` 中的 checkbox 使用了 `required` 属性，当多个同名 checkbox 都设置了 `required` 时，浏览器会显示令人困惑的验证消息（如"如果要继续，请选中..."），用户不清楚发生了什么。

2. **邮件发送失败**：创建订阅用户时只设置了 `notify.email.enabled=true` 和 `notify.email.recipients=[email]`，但没有配置 SMTP 凭据（smtp_host、smtp_port、smtp_user、smtp_password、sender），导致 `EmailNotifier` 在尝试发送邮件时因缺少凭据而静默失败。

**当前架构**：
- 每个用户有自己的 `notify.email` 配置（`EmailNotifierConfig`），包含 SMTP 凭据
- 订阅用户通过 Web 表单创建，运行时添加到 `AppConfig.users`
- 没有全局邮件配置机制

## Goals / Non-Goals

**Goals:**
- 提供清晰的表单验证体验，用户能理解发生了什么
- 确保订阅用户能正确收到推送邮件
- 保持向后兼容，不影响现有配置的用户

**Non-Goals:**
- 不改变现有的 per-user 邮件配置机制（现有用户继续用自己的 SMTP 配置）
- 不支持订阅用户自定义 SMTP 配置（统一使用全局配置）
- 不实现邮件发送失败的用户反馈（仅在日志中记录）

## Decisions

### 1. 全局邮件配置设计

**决定**：在 `AppConfig` 顶层新增 `email` 配置节，类型为 `EmailNotifierConfig`（复用现有类型）。

**理由**：
- 复用现有类型，减少代码重复
- 与 `fetch`、`scoring`、`storage` 等全局配置保持一致的结构
- 可选配置，不影响现有用户

**配置结构**：
```yaml
email:
  smtp_host: smtp.gmail.com
  smtp_port: 587
  smtp_user: ${SMTP_USER}
  smtp_password: ${SMTP_PASSWORD}
  sender: ${SMTP_SENDER}
  use_tls: true
```

**替代方案**：
- 在订阅用户创建时要求输入 SMTP 凭据 → 用户体验差，且大多数用户不知道自己的 SMTP 配置
- 从第一个现有用户复制 SMTP 配置 → 不可靠，如果所有用户都用 webhook notifier 就没有 SMTP 配置

### 2. 订阅用户 SMTP 配置继承策略

**决定**：创建订阅用户时，从全局 `email` 配置复制 SMTP 凭据到用户的 `notify.email`，同时设置 `enabled=true` 和 `recipients=[email]`。

**实现逻辑**：
```python
# 创建订阅用户时
user_config = UserConfig(
    user_id=email,
    display_name=email,
    subscriptions={"sub_domains": sub_domains},
    notify={
        "email": {
            "enabled": True,
            "recipients": [email],
            # 从全局配置复制
            "smtp_host": global_email.smtp_host,
            "smtp_port": global_email.smtp_port,
            "smtp_user": global_email.smtp_user,
            "smtp_password": global_email.smtp_password,
            "sender": global_email.sender,
            "use_tls": global_email.use_tls,
        }
    },
)
```

**理由**：
- 保持与现有 `UserConfig` 结构完全一致
- 不引入新的配置继承机制，简单直接
- 每个订阅用户有独立的邮件配置，便于未来支持个性化

**替代方案**：
- 让 `EmailNotifier` 支持全局配置 fallback → 需要修改 notifier 架构，影响范围大
- 在 pipeline 运行时动态注入 SMTP 配置 → 复杂且难以调试

### 3. 表单验证改进策略

**决定**：
1. 移除 checkbox 的 `required` 属性
2. 添加 JavaScript 客户端验证，检查至少选择一个 sub-domain
3. 保留服务器端验证（Pydantic model 已有 `min_length=1` 约束）
4. 改进验证错误提示文案

**理由**：
- 浏览器对多个同名 checkbox 的 `required` 属性处理不一致且提示不友好
- JavaScript 验证可以提供更清晰的自定义错误消息
- 服务器端验证是安全底线，防止绕过客户端

**实现方式**：
```javascript
// 在表单提交前验证
document.getElementById('subscribe-form').addEventListener('submit', function(e) {
    const checked = document.querySelectorAll('input[name="sub_domain"]:checked');
    if (checked.length === 0) {
        e.preventDefault();
        showError('请至少选择一个感兴趣的领域');
        return false;
    }
});
```

**替代方案**：
- 使用 `pattern` 属性 → 不适用于 checkbox
- 使用 CSS `:invalid` 伪类 → 无法提供自定义错误消息

### 4. 改进订阅成功反馈

**决定**：在成功消息中明确提示"我们将使用配置好的邮箱发送推送"，增强用户信心。

**新的成功消息**：
```
订阅成功！
我们已将 user@example.com 添加到订阅列表。
您关注的领域：quantization, distillation
我们将使用配置好的邮箱定期为您推送相关论文。
```

**理由**：
- 用户提交后不确定是否成功，需要明确的确认
- 提示"使用配置好的邮箱"让用户理解邮件发送机制（由系统配置，而非用户自己的邮箱）

## Risks / Trade-offs

- **[风险] 全局 SMTP 配置缺失** → 当 `config.yaml` 中没有 `email:` 节时，订阅用户创建会失败。**Mitigation**：在创建订阅用户时检查全局配置是否存在，如果不存在则返回错误提示"系统未配置邮件发送功能，请联系管理员"。

- **[风险] SMTP 凭据变更** → 如果管理员修改了全局 SMTP 配置，已存在的订阅用户不会自动更新。**Mitigation**：在文档中说明，修改 SMTP 配置后需要重新加载应用或手动更新订阅用户。MVP 阶段可接受此限制。

- **[Trade-off] 订阅用户无法自定义 SMTP** → 所有订阅用户共享同一个 SMTP 配置，无法使用不同的邮件服务。**Mitigation**：这是 MVP 简化设计，未来可扩展订阅表单支持自定义 SMTP（但不推荐，增加复杂度）。

- **[Trade-off] JavaScript 验证可能被禁用** → 如果用户禁用 JavaScript，客户端验证失效。**Mitigation**：服务器端验证作为安全底线，仍然会拒绝无效提交。
