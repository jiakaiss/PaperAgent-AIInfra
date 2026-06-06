## 1. 模板改造

- [x] 1.1 在 `src/paper_agent/web/templates/subscribe.html` 中，在 `<p class="subscribe-description">…</p>` 与 `<form id="subscribe-form" …>` 之间新增 `<section class="subscribe-rules" aria-label="订阅规则">` 区块
- [x] 1.2 区块内用 `<h2>` 或加粗段落作为「订阅规则」标题，配 `<ul>` 列出两条规则
- [x] 1.3 规则一文案：「每天 09:00（北京时间）从最新论文中筛选一份个性化摘要发送到您的邮箱」
- [x] 1.4 规则二文案：「目前仅支持下方列出的 14 个标准研究方向；如需新增类别，请联系管理员添加」（不嵌入任何具体邮箱/链接）
- [x] 1.5 在模板靠近推送时间文案处加 HTML 注释 `<!-- 修改推送时间前请同步 config.schedule.digest_hour/digest_minute -->`

## 2. 样式调整（按需）

- [x] 2.1 在浏览器中查看 `/subscribe`，确认 `.subscribe-rules` 与上下文留白、字号、对齐看起来一致
- [x] 2.2 如果留白或视觉分隔不够，在 `src/paper_agent/web/static/style.css` 中新增最小化 `.subscribe-rules` 样式（如 `margin`、淡色背景块、左边框），与现有 `.subscribe-description` / `.form-hint` 视觉语言一致
- [x] 2.3 检查移动端（窄屏）下区块布局没有溢出/挤压

## 3. 验证

- [x] 3.1 启动 `paper-agent web -c config.yaml`，打开 `/subscribe`，肉眼确认两条规则可见且位于介绍段落之后、表单之前
- [x] 3.2 确认页面 HTML 中没有出现明文管理员邮箱（`grep -i "@" subscribe.html` 仅命中 placeholder `your.email@example.com`）
- [x] 3.3 确认 access-code 开启与关闭两种配置下规则区块都正常渲染
- [x] 3.4 运行 `pytest tests/ -v` 确认无现有测试因模板结构变更而失败
- [x] 3.5 运行 `ruff check src/ tests/` 确认无 lint 回归（虽然只改模板，作为例行步骤）

## 4. 归档

- [x] 4.1 在 `proposal.md` / `design.md` / `specs/` 全部落实后，运行 `openspec validate add-subscription-rules-notice --strict`
- [ ] 4.2 准备好后由用户执行 `/opsx:archive` 完成归档
