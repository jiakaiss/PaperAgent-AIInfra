## Context

`/subscribe` 页面（`src/paper_agent/web/templates/subscribe.html`）当前只有一句 `subscribe-description` 介绍订阅用途，没有说明推送频率（每天 09:00 Asia/Shanghai，由 `config.schedule.digest_hour/minute` 决定）和子领域可扩展性（14 个标准子领域在 `paper_agent.models.SUB_DOMAINS` 写死）。

变更纯前端文案，无后端逻辑。

## Goals / Non-Goals

**Goals:**
- 用户在提交订阅前就能看到「每天 09:00 推送」与「有新类别请联系管理员添加」两条规则
- 文案位置自然，不破坏现有表单视觉与交互
- 不引入新的模板上下文字段、配置项或翻译文件

**Non-Goals:**
- 不把 `digest_hour` 从配置动态注入到模板（当前 9 点是项目长期默认且不会随用户而变；硬编码可读且易维护）
- 不实现「在 UI 上申请新子领域」的功能
- 不调整管理员联系方式的展示形式（不放邮箱/链接，保持「联系管理员」即可，避免把管理员邮箱暴露在公开页面）

## Decisions

### 决策 1：把规则说明放在 description 段落之后、表单之前

把新增的「订阅规则」放在 `<h1>订阅 / 更新论文推送</h1>` 与 `<form>` 之间，作为独立的 `.subscribe-rules` 区块。理由：

- 用户视线自然从标题 → 介绍 → 规则 → 表单，规则在提交前被读到
- 与现有 `subscribe-description` 处在同一层级，不需要把它塞进任何 `form-group`，避免被误以为是表单字段
- 备选：放在按钮下方 / 放在 sub_domain checkbox 下方 → 都在用户填表后才看到，时机太晚

### 决策 2：推送时间硬编码为「每天 09:00（北京时间）」

理由：

- 当前 `config.example.yaml` 与 `config.yaml` 都是 `digest_hour: 9, digest_minute: 0, timezone: Asia/Shanghai`，且这是项目对外承诺
- 把模板做成读 `config.schedule` 反而引入跨层耦合（subscribe 路由要把 schedule 注入上下文），收益有限
- 若未来该时间真的要改，直接改这一句模板字符串即可，且应当伴随用户公告，不是默默跟配置走

### 决策 3：用「联系管理员」纯文案，不放具体联系方式

理由：

- 联系渠道（邮箱 / 飞书 / 钉钉群）因部署而异，不在 `AppConfig` 中
- 公开页面暴露管理员邮箱有被爬取的风险
- 用户从「联系管理员」自然回到自己的部署渠道（公司内网通常有既定 IT 工单/管理员沟通方式）

### 决策 4：复用现有 `.subscribe-description` / `.form-hint` 视觉语言

新增一个 `.subscribe-rules` 容器，其内部用 `<ul>` 列出 2 条规则。如果现有 CSS 已经能撑住样式（`subscribe-description` 段落 + 列表），就不新增 CSS；如果留白/分隔不够清晰，再在 `style.css` 里加最小化的 `.subscribe-rules { ... }` 规则（border / padding / 背景淡色块）。

## Risks / Trade-offs

- [推送时间硬编码与 `config.schedule` 漂移] → 在 `subscribe.html` 旁注一行 HTML 注释提示「修改前请核对 config.schedule.digest_hour」；并在 tasks.md 里要求改时间的同时检查这处文案
- [不同部署的管理员联系方式不同，文案过于笼统] → 接受。后续若有需求可加一个可选 `config.subscriptions.admin_contact` 字段并注入模板，本次不做
- [新增文案影响小屏移动端布局] → 用现有响应式样式承载；如出现明显问题在 verify 阶段补一条 CSS 调整
