## Context

Paper Agent 当前支持 4 种通知器（email、feishu、wecom、dingtalk）和一个 `users` 列表配置，用于定义多用户的订阅偏好和通知渠道。随着 Web 订阅系统的成熟（全局 SMTP 配置 + Web 表单订阅），飞书/企微/钉钉 webhook 通知器已不再是核心功能，而 `users` 列表与订阅系统功能高度重合。

当前状态：
- `notifier/` 目录下有 4 个通知器实现（`email_notifier.py` + 3 个 webhook 通知器），共约 438 行代码
- `config.py` 有 4 个通知器配置类（`EmailNotifierConfig` + 3 个 webhook 配置类），`UserNotifyConfig` 包含 4 个字段
- `config.example.yaml` 的 `users` 部分展示了 3 个示例用户（分别用飞书、邮件、企微），配置冗长
- `pipeline.py` 为每个 `config.users` 创建通知器并运行 per-user digest
- `cli.py` 的 `test` 命令支持 4 种通知器选择，`stats` 命令遍历 4 种通知器

## Goals / Non-Goals

**Goals:**
- 删除飞书、企微、钉钉通知器及其配置，仅保留邮件通知
- 精简 `UserNotifyConfig` 为仅含 email 字段，移除冗余配置类
- 移除 `config.yaml` 中的 `users` 列表，将全局阈值和订阅偏好提升到顶层配置
- 订阅系统成为唯一用户来源，简化 pipeline 的用户处理逻辑
- 同步更新 README、CLAUDE.md、config.example.yaml、测试文件

**Non-Goals:**
- 不改变数据库 schema（`sent_papers` 的 `user_id` 仍为订阅邮箱）
- 不改变 Web UI 的浏览/过滤功能
- 不改变管理员看板功能
- 不改变 arXiv 抓取和 Claude 评分逻辑

## Decisions

### D1: 移除 `users` 列表，改用全局阈值 + 订阅系统

**决定**：删除 `AppConfig.users: list[UserConfig]`，将 `UserThresholdsConfig` 的字段提升为 `AppConfig` 的全局字段。订阅系统（`subscriptions` 表）成为唯一用户来源。

**理由**：
- `users` 列表与订阅系统功能完全重合，维护两套用户配置增加复杂度
- 所有通知均走邮件，不存在 per-user 不同通知渠道的需求
- 全局阈值适用于所有订阅用户，简化配置
- `pipeline.py` 不再需要 `_build_superset_keywords` 遍历 users，改用全局 `fetch.keywords` + `subscriptions.sub_domains`

**替代方案**：保留 `users` 但仅支持 email 通知器 → 仍需维护 UserConfig/UserNotifyConfig，收益有限

### D2: 通知器模块精简为仅邮件

**决定**：删除 `dingtalk_notifier.py`、`feishu_notifier.py`、`wecom_notifier.py`，简化 `notifier/__init__.py` 为仅注册 `EmailNotifier`。

**理由**：
- 3 个 webhook 通知器总计约 309 行代码，使用率低
- 邮件通知器已有完整实现（HTML 模板、SMTP、取消订阅链接）
- 删除后减少维护负担和依赖（如钉钉的 HMAC-SHA256 签名逻辑）

### D3: 保留 `UserConfig` 作为内部数据模型（但不在配置文件中暴露）

**决定**：`UserConfig` 类保留在代码中作为 pipeline 的内部数据结构（由订阅系统构造），但从 `AppConfig` 中移除 `users` 字段。配置文件不再需要定义 `users`。

**理由**：
- pipeline 仍需 per-user 过滤和通知，`UserConfig` 作为内部数据模型有用
- 订阅 → UserConfig 的转换逻辑已存在于 `subscriptions.py`
- 从配置文件移除 `users` 让用户配置大幅简化

### D4: 全局阈值配置

**决定**：将 `UserThresholdsConfig` 的关键字段提升为 `AppConfig` 下的 `thresholds` 配置节，所有订阅用户共享同一套阈值。

```yaml
thresholds:
  min_relevance: 6.0
  min_quality: 5.0
  top_n: 10
  min_tier: solid
```

**理由**：只有一种通知渠道后，per-user 阈值差异化的需求大大降低。全局阈值 + 订阅时自选子领域已足够。

## Risks / Trade-offs

- **[Breaking change]** 删除 `users` 配置后，现有用户需要迁移配置文件 → 提供 `config.example.yaml` 作为参考，在 README 中说明迁移步骤
- **[Breaking change]** 删除 webhook 通知器后，依赖这些渠道的用户无法继续使用 → 邮件订阅已覆盖核心场景，webhook 用户可自行 fork 添加
- **[Per-user 阈值灵活性降低]** 全局阈值不满足个性化需求 → 可后续通过订阅表单扩展 per-user 阈值覆盖，但当前阶段全局阈值足够
- **[Pipeline 需适配]** `Pipeline.__init__` 和 `_run_digest` 需改为从订阅系统获取用户列表 → 改动量可控，逻辑更清晰
