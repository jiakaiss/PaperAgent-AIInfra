## 1. 配置层精简 (config.py)

- [x] 1.1 删除 `WeComNotifierConfig`、`FeishuNotifierConfig`、`DingTalkNotifierConfig` 三个配置类
- [x] 1.2 简化 `UserNotifyConfig`：仅保留 `email: EmailNotifierConfig` 字段
- [x] 1.3 添加全局 `ThresholdsConfig`（含 `min_relevance`、`min_quality`、`top_n`、`min_tier`、`per_sub_domain_top_n`）
- [x] 1.4 在 `AppConfig` 中添加 `thresholds: ThresholdsConfig` 字段，移除 `users: list[UserConfig]` 字段
- [x] 1.5 删除 `AppConfig.validate_unique_user_ids` 校验器（已无 users 列表）
- [x] 1.6 保留 `UserConfig`、`UserThresholdsConfig`、`SubscriptionConfig` 作为订阅系统使用的内部模型

## 2. 通知器模块精简 (notifier/)

- [x] 2.1 删除 `notifier/dingtalk_notifier.py`
- [x] 2.2 删除 `notifier/feishu_notifier.py`
- [x] 2.3 删除 `notifier/wecom_notifier.py`
- [x] 2.4 更新 `notifier/__init__.py`：仅注册 `EmailNotifier`，移除其他 3 个通知器的 import 和注册
- [x] 2.5 简化 `create_notifiers_for_user` 工厂函数：仅检查 email 是否启用

## 3. 订阅系统适配 (subscriptions.py)

- [x] 3.1 修改 `_load_subscriptions_into_config`（或等效函数）：从全局 `config.thresholds` 读取阈值赋给生成的 `UserConfig`
- [x] 3.2 确保订阅 → UserConfig 转换不再触碰 wecom/feishu/dingtalk 字段
- [x] 3.3 启动时若 `config.email.enabled=false`，订阅用户 UserConfig 仍生成但 email 禁用（保持原警告）

## 4. Pipeline 适配 (pipeline.py)

- [x] 4.1 修改 `Pipeline._build_superset_keywords`：从全局 `config.fetch.keywords` 加全部 `SUB_DOMAINS` 名构造关键词（不再遍历 users）
- [x] 4.2 修改 `Pipeline.__init__`：从 `config.users`（由订阅系统填充）创建 per-user notifiers
- [x] 4.3 确认 `_run_digest` 和 `_run_for_user` 仍正常工作（用户来自订阅系统）

## 5. CLI 精简 (cli.py)

- [x] 5.1 `test` 命令的 `--notifier` 选项简化为仅支持 `email`（或保留 click.Choice(["email"])）
- [x] 5.2 `stats` 命令的用户遍历仅显示 email notifier 状态，删除 wecom/feishu/dingtalk 检查分支
- [x] 5.3 `daemon`、`run` 命令保持不变（依然从 subscriptions 加载用户）

## 6. 配置模板精简 (config.example.yaml)

- [x] 6.1 删除 `users:` 列表整个段落（包括 alice/bob/team_channel 三个示例）
- [x] 6.2 添加新的 `thresholds:` 顶层段落
- [x] 6.3 删除 `keywords` 列表中冗余的"重复表达"项（如 `mixture of experts` 在 sub-domain 已涵盖），适度精简
- [x] 6.4 删除/简化指向 `FEISHU_WEBHOOK_*`、`WECOM_WEBHOOK`、`DINGTALK_WEBHOOK` 的环境变量注释

## 7. Web 层影响检查 (web/)

- [x] 7.1 检查 `web/app.py` 是否在用户初始化时假设了 `cfg.users` 存在，调整为兼容空 users
- [x] 7.2 检查 `web/routes.py` 是否引用了 webhook notifier 类型，移除
- [x] 7.3 检查 `web/admin.py` 的活动用户面板是否仅显示 email，移除多通知器展示

## 8. 数据库层检查 (storage/database.py)

- [x] 8.1 确认数据库 schema 无变化（`sent_papers.user_id` 仍为订阅邮箱）
- [x] 8.2 检查 admin 聚合查询（`get_user_stats` 等）是否需要调整

## 9. 测试同步更新 (tests/)

- [x] 9.1 删除 `tests/test_dingtalk_notifier.py`、`tests/test_feishu_notifier.py`、`tests/test_wecom_notifier.py`（若存在）
- [x] 9.2 更新 `tests/test_config.py`：删除 users 列表测试，添加 thresholds 测试
- [x] 9.3 更新 `tests/test_pipeline.py`：使用订阅系统构造测试用户，不再用 config.users
- [x] 9.4 更新 `tests/test_subscriptions.py`：验证全局 thresholds 应用到生成的 UserConfig
- [x] 9.5 检查 `tests/test_admin.py`：保证 secret 不泄漏的测试用例覆盖新结构
- [x] 9.6 运行 `pytest tests/ -v` 全部通过

## 10. 文档更新

- [x] 10.1 更新 `README.md`：移除飞书/企微/钉钉相关说明；说明邮件订阅为唯一通知渠道；展示新的配置结构（无 users 列表 + thresholds）
- [x] 10.2 更新 `CLAUDE.md`：同步 Pipeline、Config、Notifier 章节，反映精简后的架构
- [x] 10.3 更新 `docs/user-guide.md` 和 `docs/docker-deployment.md`（如有相关说明）
- [x] 10.4 更新 `.env.example`：移除 FEISHU_WEBHOOK_*、WECOM_WEBHOOK、DINGTALK_WEBHOOK 等无用变量

## 11. 验证与清理

- [x] 11.1 `ruff check src/ tests/` 通过
- [x] 11.2 `ruff format src/ tests/`
- [x] 11.3 手动启动 `paper-agent web` 验证 Web UI 工作正常
- [x] 11.4 手动执行 `paper-agent run --dry-run` 验证 pipeline 工作正常
- [x] 11.5 删除任何引用已删除模块的死代码（grep 检查 `dingtalk|feishu|wecom`）