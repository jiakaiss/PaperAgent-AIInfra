## Why

两个用户体验问题需要修复：

1. **推送数量过少**：当前 `pipeline.py:206` 对每个用户只取 `top_n=20` 篇（按总分排序），不区分领域。订阅多个领域的用户实际可能某些领域一篇都看不到 —— 因为另一个论文密集的领域把全部名额占了。用户期望"每个订阅的领域都能各看到 top 20 篇"。

2. **邮件字体可读性**：当前邮件模板（`formatter/templates.py:104`）用 `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`。对英文论文标题来说 sans-serif 在密集排版下不够清晰，用户希望英文用 Times New Roman（衬线字体更适合长篇英文阅读），中文用微软雅黑（屏幕显示清晰）。

## What Changes

- **按订阅领域分别取 top-N，再合集去重**：
  - 新增 `UserThresholdsConfig.per_sub_domain_top_n: int = 20`
  - 修改 `Pipeline._filter_and_notify_for_user`：对每个订阅的 sub-domain，独立筛选 + 排序，取 top N；再合并去重；保留原 `top_n` 作为合集后的全局上限兜底
  - 订阅 `["all"]` 的用户行为不变（无领域可拆，沿用全局 `top_n`）

- **邮件字体改为 Times New Roman + 微软雅黑**：
  - 修改 `formatter/templates.py` 中邮件 HTML `<body>` 的 `font-family`
  - 优先级：`'Times New Roman', 'Microsoft YaHei', '微软雅黑', serif`
  - 浏览器/邮件客户端按字符匹配字体：英文走 Times，中文走微软雅黑（Linux/Mac 上没装微软雅黑会回退到下一个 serif）
  - 不动 web 浏览页字体（`web/static/style.css` 不变）

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `delivery-volume-control`: 新增「按订阅领域分别限额」要求；不替换现有「Configurable subscription delivery count」（用户级总上限仍存在，新限额是叠加在它前面的"领域内"限额）

## Impact

- 受影响代码：
  - `src/paper_agent/config.py`（`UserThresholdsConfig` 加字段）
  - `src/paper_agent/pipeline.py`（`_filter_and_notify_for_user` 重写过滤逻辑）
  - `src/paper_agent/formatter/templates.py`（邮件 HTML font-family）
  - `config.example.yaml`、`config.yaml`（示例 `per_sub_domain_top_n`，可选）
- 不受影响：web 页面、API、数据库、其它 notifier (wecom/feishu/dingtalk) —— 仅邮件 HTML 字体改动
- 测试：`tests/test_pipeline.py` 现有 `top_n` 行为测试需要复核；新增 per-domain 拆分测试
- 无 BREAKING：新字段有默认值；`top_n` 默认仍 20，作为合集上限继续生效；订阅 `["all"]` 用户行为不变
