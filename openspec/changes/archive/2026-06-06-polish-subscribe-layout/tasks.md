## 1. 调整订阅页 CSS

- [x] 1.1 在 `src/paper_agent/web/static/style.css` 中，把 `.subscribe-container` 的 `max-width` 从 `600px` 改为 `820px`
- [x] 1.2 修改 `.sub-domain-grid` 默认规则：`grid-template-columns: repeat(auto-fit, minmax(220px, 1fr))`（原为 `minmax(180px, 1fr)`）
- [x] 1.3 删除 `@media (min-width: 1024px) { .sub-domain-grid { grid-template-columns: repeat(3, 1fr); } }` 这条硬列数规则（让 auto-fit 接管所有 ≥768px 断点）
- [x] 1.4 删除 `@media (min-width: 768px) and (max-width: 1023px) { .sub-domain-grid { grid-template-columns: repeat(2, 1fr); } }` 同理（auto-fit 会按 220px 算）
- [x] 1.5 在 `.checkbox-card` 加 `flex-wrap: nowrap`；在 `.checkbox-card-label` 加 `white-space: nowrap`，作为兜底防止文字换行
- [x] 1.6 移动端规则 `@media (max-width: 768px) { .sub-domain-grid { grid-template-columns: 1fr; } }` 保留不动（窄屏强制单列）

## 2. 验证

- [x] 2.1 用 Jinja 静态渲染 `subscribe.html`，确认 CSS 文件能被加载、类名匹配，无 lint 错误
- [x] 2.2 启动 `paper-agent web -c config.yaml`，桌面浏览器打开 `/subscribe`，肉眼确认 3 列等宽、长 tag 不换行（用户负责）
- [x] 2.3 浏览器 DevTools 切换到 375px 宽度（iPhone SE），确认 sub-domain 网格仍单列、容器不溢出（用户负责）
- [x] 2.4 打开 `/` 浏览页，确认页面宽度、卡片布局没有任何变化
- [x] 2.5 运行 `pytest tests/ -v` 全量回归
- [x] 2.6 运行 `ruff check src/ tests/`

## 3. 归档

- [x] 3.1 运行 `openspec validate polish-subscribe-layout --strict`
- [ ] 3.2 由用户执行 `/opsx:archive` 完成归档

## 4. 附带修复：静态资源缓存破坏（实施中追加）

实施验证时发现：浏览器对 `/static/style.css` 永久缓存，导致 CSS 改动不刷新看不到。属于本次 polish 的必要配套修复，一并纳入。

- [x] 4.1 在 `src/paper_agent/web/templates/base.html` 把 `<link rel="stylesheet" href="/static/style.css">` 改为 `<link rel="stylesheet" href="/static/style.css?v={{ style_version }}">`
- [x] 4.2 在 `src/paper_agent/web/app.py` 启动时计算 `style.css` 的 mtime 作为版本号，注入 `templates.env.globals["style_version"]`
- [x] 4.3 重启 web 验证：HTML 渲染出 `style.css?v=<timestamp>`，外网刷新即可看到新样式（无需强刷）
