## 1. 配置字段

- [x] 1.1 在 `src/paper_agent/config.py` 的 `UserThresholdsConfig` 中新增 `per_sub_domain_top_n: int = 20`
- [x] 1.2 在 `UserThresholdsConfig` 加 Pydantic validator：`per_sub_domain_top_n` 必须 > 0
- [x] 1.3 把 `UserThresholdsConfig.top_n` 默认值从 `20` 改为 `200`（作为合集后兜底上限）
- [x] 1.4 在 `config.example.yaml` 的 user 示例 `thresholds:` 块下加注释行 `# per_sub_domain_top_n: 20` 并说明语义

## 2. Pipeline 算法

- [x] 2.1 修改 `src/paper_agent/pipeline.py` 的 `_filter_and_notify_for_user`：把"领域过滤 → 阈值过滤 → 排序 → 截 top_n"重写为：
  - 若 `"all" not in sub_domains`：对每个 sub-domain 独立筛选（领域命中 + 阈值通过）+ 排序，取 `per_sub_domain_top_n`，合并所有桶，按 `arxiv_id` 去重，再排序后截 `top_n` 兜底
  - 若 `"all" in sub_domains`：保持原行为（阈值过滤 → 排序 → 截 top_n）
- [x] 2.2 保留现有 dedup 逻辑（`db.filter_unsent_for_user` 那部分不动）
- [x] 2.3 日志输出加一行 `per-domain bucket sizes`，便于排查（如 `quant=15, distil=8`）

## 3. 邮件字体

- [x] 3.1 修改 `src/paper_agent/formatter/templates.py:104` 的 `<body style="font-family: ...">`，把现有 sans-serif 字体栈替换为 `'Times New Roman', 'Microsoft YaHei', '微软雅黑', serif`
- [x] 3.2 检查 `format_markdown` 函数确认无 font-family 出现（不该有，仅复核）

## 4. 测试

- [x] 4.1 在 `tests/test_pipeline.py` 新增 `test_per_sub_domain_top_n_split_and_dedup`：构造 quantization 30 篇 + distillation 25 篇 + 5 篇双 tag，`per_sub_domain_top_n=10`，断言用户拿到 ≤20 篇且去重正确
- [x] 4.2 新增 `test_per_sub_domain_respects_overall_cap`：`per_sub_domain_top_n=20, top_n=15`，10 个 sub-domain，断言总数 ≤15
- [x] 4.3 新增 `test_all_subscription_ignores_per_domain_limit`：订阅 `["all"]`，验证拿到 `top_n` 篇（而非按领域分桶）
- [x] 4.4 复核现有 `test_pipeline_multi_user_filter` 与 `top_n` 相关断言是否需要调整（现有测试显式传 `top_n=10`，不受默认值变化影响）
- [x] 4.5 在 `tests/test_formatter.py` 新增 `test_email_html_uses_times_and_yahei`（断言 font-family 包含 Times/雅黑，不再包含 BlinkMacSystemFont）+ `test_format_markdown_has_no_html_font_family`（断言 markdown 未泄漏 font-family）

## 5. 自动化验证

- [x] 5.1 运行 `pytest tests/ -v` — 190 passed
- [x] 5.2 运行 `ruff check src/ tests/` — All checks passed
- [x] 5.3 用 `paper-agent test --notifier email --user <subscription_email>` 手动发一封测试邮件，肉眼确认字体（用户负责，需自行执行）

## 6. 归档

- [x] 6.1 运行 `openspec validate per-domain-top-and-email-font --strict`
- [x] 6.2 由用户执行 `/opsx:archive` 完成归档
