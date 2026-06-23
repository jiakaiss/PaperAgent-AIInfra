# Paper Agent - AI Infra 论文智能推送系统

自动从 arXiv 抓取高质量 AI Infrastructure 相关论文，通过 Claude 智能评分与分类，按邮件订阅推送给用户，并提供 Web UI 浏览与筛选。

## 功能特点

- 自动抓取 arXiv 上最新的 AI Infra 相关论文
- 使用 Claude 对论文进行相关度、质量打分，自动分类到 14 个子领域
- **影响力分级** — 每篇论文自动分到「重磅突破 / 稳健工作 / 渐进改进」三档，前端按 tier 排序与视觉区分
- **结构化洞察** — 评分时额外抽取「关键贡献 / 问题陈述 / 方法概述」，前端与邮件用彩色卡片高亮展示
- **引用感知评分**（可选）— 接入 Semantic Scholar 周期采集每篇论文的引用数；引用涨幅超过阈值时自动让 Claude 用最新引用作 context 重新评估 `relevance/quality/tier`，让评分随真实世界影响力动态变化。每次刷新最多重判 N 篇，单篇间隔最少 M 天，成本可控
- **重要老作分区**（可选）— 反向从 Semantic Scholar 发现高引用老论文（≥ 配置年限），打分入库后在邮件/网页中以独立分区呈现（不占用 top_n 名额）
- **双轨抓取**（可选）— 每个关键词独立配额避免噪声词独占 + cs.LG/cs.DC 跨列表兜底，捞回用了不同术语的高质量工作
- **邮件订阅推送** — 唯一的推送渠道；用户通过 Web 表单订阅，系统统一使用全局 SMTP 凭据发送
- **Web 浏览界面** — FastAPI + HTMX 论文浏览页，支持子领域筛选、影响力 tier 筛选、标题搜索、时间范围过滤、分页
- **偏好设置** — 基于 localStorage 的浏览模式切换、子领域选择、最低影响力档位，筛选条件会同步到 URL
- **Web 自助订阅** — 访问 `/subscribe` 输入邮箱和关注领域，自动加入定时邮件推送
- **全局阈值与邮件配置** — 所有订阅用户共享全局 `thresholds` 和 `email` 配置，支持 `${ENV_VAR}` 注入敏感信息
- **数据库自动迁移** — 升级后老数据无缝兼容，可选 `paper-agent rescore --missing-fields` 回填新字段
- **部署前自检** — `paper-agent doctor` 检查配置、数据库、Web 资源和邮件配置
- **Docker / VPS 部署** — 提供 Dockerfile、docker-compose、`.env.example`、部署/备份/恢复脚本
- 可配置的 daemon 定时任务：后台按间隔查询/评分/入库，每日定时从缓存推送
- SQLite 去重，避免重复推送

## 快速开始

### 安装

```bash
# 克隆项目
git clone <repo-url>
cd paper_agent

# 安装依赖（含 Web UI）
pip install -e ".[dev]"
```

### 配置

```bash
# 生成配置文件模板
paper-agent init

# 编辑 config.yaml，填入 Claude API key 和全局 SMTP 凭据
```

配置文件采用单一全局配置 + Web 订阅模式：所有推送用户均来自 Web 表单订阅（写入 SQLite `subscriptions` 表），共享全局阈值与 SMTP 配置。详见 `config.example.yaml`。

重要配置点：

- `scoring.api_key` / `scoring.base_url`：LLM API 配置，支持 `${ENV_VAR}` 环境变量注入
- `email`：全局 SMTP 配置，供所有订阅用户接收邮件推送
- `thresholds`：全局推送阈值（`min_relevance` / `min_quality` / `top_n` / `min_tier` / `per_sub_domain_top_n`），适用于所有订阅用户
- `thresholds.min_tier`：影响力阈值（`breakthrough` / `solid` / `incremental`），默认 `solid`（排除渐进改进）
- `fetch.quality_floor_strategy`：双轨抓取开关（`none` / `per_keyword_cap`），默认关闭保持向后兼容
- `fetch.cross_list_categories`：双轨抓取中轨道 2 的 arXiv 分类（如 `[cs.LG, cs.DC]`），仅在 `per_keyword_cap` 下生效
- `storage.db_path`：SQLite 数据库路径，Docker 部署时建议使用 `/app/data/paper_agent.db`
- `schedule`：daemon 后台查询频率和每日推送时间配置

> **注意：** 已不再支持飞书 / 企业微信 / 钉钉 webhook 推送以及在 `config.yaml` 中静态定义的 `users:` 列表。所有用户通过 Web 订阅。

### 运行

```bash
# 部署前自检
paper-agent doctor -c config.yaml

# 单次运行（dry-run 模式，不发通知）
paper-agent run --dry-run -c config.yaml

# 单次运行（指定订阅邮箱）
paper-agent run --user alice@example.com --dry-run -c config.yaml

# 测试邮件配置（仅支持 email）
paper-agent test --notifier email --user alice@example.com -c config.yaml

# 启动 daemon（后台按间隔查询入库，每天 9:00 从缓存推送）
paper-agent daemon -c config.yaml

# 启动 Web UI（http://127.0.0.1:8000）
paper-agent web -c config.yaml

# 给老论文（升级前未打 tier / 关键贡献的）批量补全结构化字段
# 会调 Claude API 花钱；每批一个事务，可随时 Ctrl+C 中断后重跑续上
paper-agent rescore --missing-fields -c config.yaml
```

Linux 本地/服务器可使用启动脚本：

```bash
# 同时启动 Web 和 daemon（前台运行，Ctrl+C 同时停止）
scripts/start-local.sh all

# 只启动 Web
scripts/start-local.sh web

# 只启动 daemon（后台查询 + 每日推送，前台运行）
scripts/start-local.sh daemon

# 后台持久化运行 daemon 和 web（推荐生产环境，非 Docker）
# 日志各自写入 logs/daemon.log 和 logs/web.log（由 Python FileHandler 维护，不依赖 shell session）
scripts/daemon.sh start          # 调度器（拉取 + 评分 + 每日推送）
scripts/web.sh start             # Web UI
scripts/daemon.sh status         # 各自支持 start | stop | restart | status
scripts/web.sh status
# 指定 Python 环境 / 监听地址
PYTHON_BIN=/opt/conda/envs/paper_agent/bin/python scripts/daemon.sh start
HOST=0.0.0.0 PORT=8000 scripts/web.sh start

# 本地检查（ruff + pytest + 可选 JS tests）
scripts/check.sh
```

常用 Linux/Docker 运维脚本：

```bash
# 部署/更新 Docker 服务
scripts/deploy.sh

# 查看服务状态和 Web 健康检查
scripts/status.sh

# 查看全部日志，或指定 web/daemon（直接使用 docker compose）
docker compose logs -f
docker compose logs -f daemon

# 停止 Docker 服务
docker compose down

# 备份/恢复数据库
scripts/backup.sh
scripts/restore.sh deploy/backups/paper_agent-YYYYMMDD-HHMMSS.db
```

> Windows 不是当前优先部署环境；如需手动运行 CLI，请自行设置 `PYTHONIOENCODING=utf-8` 避免编码错误。

## 命令说明

| 命令 | 说明 |
|---|---|
| `paper-agent run` | 单次运行抓取、评分和推送 |
| `paper-agent daemon` | 启动定时任务守护进程 |
| `paper-agent web` | 启动 Web 浏览界面 |
| `paper-agent rescore --missing-fields` | 给老论文补全 tier / 关键贡献等结构化字段 |
| `paper-agent doctor` | 检查部署前配置、数据库、Web 资源和邮件配置 |
| `paper-agent test --notifier email --user <email>` | 测试邮件渠道配置（仅支持 email） |
| `paper-agent stats` | 查看数据库统计信息 |
| `paper-agent init` | 生成配置文件模板 |

## Web UI

启动后访问 `http://127.0.0.1:8000`，支持以下功能：

- **影响力分级筛选** — 按「仅重磅突破 / 稳健及以上（默认）/ 全部含渐进改进」三档筛选，首页默认隐藏「渐进改进」论文
- **子领域筛选** — 点击标签 chip 按子领域过滤论文
- **时间范围** — 按发布时间过滤（近一周/月/3月/半年/1年/3年）
- **标题搜索** — 按关键词搜索论文标题
- **偏好设置** — 切换「全量论文」/「自定义领域」浏览模式，选择最低影响力档位
- **结构化论文卡片** — 每篇论文展示影响力徽章（重磅突破带橙色边框 + 琥珀色标记）、关键贡献（绿色块）、问题陈述（蓝色块）、方法概述（紫色块）、子领域标签和评分
- **分页** — 每页 25 篇，按影响力优先排序（breakthrough → solid → incremental），同 tier 内按综合得分排序
- **URL 可分享** — 筛选条件编码在 URL 中，可收藏或分享
- **自助订阅** — 访问 `/subscribe` 填写邮箱和关注领域，订阅信息写入 SQLite，daemon 后续按订阅推送
- **管理员看板** — `/admin` 路径（默认关闭）。开启后用 HTTP Basic Auth 鉴权，提供订阅用户列表、推送统计、论文库概览、系统状态四个面板，以及订阅 CSV 导出。详见 [CLAUDE.md](CLAUDE.md#admin-dashboard-webadminpy) 的 Admin Dashboard 章节。

### Web 订阅说明

所有用户都通过 Web 表单订阅，记录保存在数据库 `subscriptions` 表中。应用启动时会把 active subscriptions 转换成运行时 `UserConfig`，并从全局 `email` 配置继承 SMTP 凭据、从全局 `thresholds` 继承推送阈值。

> 💡 设置 `web.public_base_url` 后，每封日报邮件顶部都会出现「🔗 在网页中浏览全部论文」链接，方便订阅用户一键跳转到 Web UI 浏览更多论文。修改该字段后需要重启应用，已有订阅用户的邮件链接才会更新。

```yaml
email:
  enabled: true
  smtp_host: ${SMTP_HOST}
  smtp_port: 587
  smtp_user: ${SMTP_USER}
  smtp_password: ${SMTP_PASSWORD}
  sender: ${SMTP_SENDER}
  use_tls: true

thresholds:
  min_relevance: 6.0
  min_quality: 5.0
  top_n: 10
  min_tier: solid
```

如果修改了 SMTP 配置或全局阈值，需要重启 Web/daemon 服务让已有订阅用户加载新配置。

## Docker / VPS 部署

项目提供 Docker Compose 部署方式，可在任意 Linux VPS 上同时运行 Web UI 和 daemon 定时任务：

```bash
cp .env.example .env
cp config.example.yaml deploy/config/config.yaml
# 编辑 .env 和 deploy/config/config.yaml
# Docker 部署注意：将 storage.db_path 改为 /app/data/paper_agent.db，
#                   将 logging.file 改为 /app/logs/paper-agent.log
./scripts/deploy.sh
```

部署后包含两个服务：

- `web`：对外提供 Web UI，容器内绑定 `0.0.0.0:8000`，并提供 `/health` 健康检查
- `daemon`：按 `schedule` 配置执行后台查询/评分/入库，并每日定时从缓存推送

运行数据默认持久化在：

```text
deploy/data/      # SQLite 数据库
deploy/logs/      # 日志
deploy/backups/   # 备份
```

常用运维命令：

```bash
# 查看状态和日志
docker compose ps
docker compose logs -f web
docker compose logs -f daemon

# 备份/恢复数据库
./scripts/backup.sh
./scripts/restore.sh deploy/backups/paper_agent-YYYYMMDD-HHMMSS.db

# 部署前自检
paper-agent doctor -c deploy/config/config.yaml
```

部署文档见 [`docs/docker-deployment.md`](docs/docker-deployment.md)。

## 子领域分类

系统自动将论文分类到 14 个 AI Infra 子领域：

`quantization` · `distillation` · `pruning` · `sparsity` · `distributed_training` · `parallelism` · `serving` · `speculative_decoding` · `kv_cache` · `moe` · `compiler` · `memory_optimization` · `communication` · `scheduling`

## 影响力分级

每篇论文由 LLM 评估后归入三级 impact tier，用于前端视觉区分和用户级过滤：

| 分级 | 含义 | 前端样式 | 默认显示 |
|---|---|---|---|
| **重磅突破** (`breakthrough`) | 可能改变实践的新技术/成果 | 橙色左边框 + 琥珀色徽章 | ✅ |
| **稳健工作** (`solid`) | 工作扎实的有用改进 | 灰色徽章，标准样式 | ✅ |
| **渐进改进** (`incremental`) | 小幅变化，范围狭窄，评估有限 | 半透明 + 浅灰徽章 | ❌ 隐藏 |

排序规则：**先按 tier 优先级排**（breakthrough → solid → incremental），同 tier 内按综合得分降序。

用户可通过以下方式控制：
- **全局配置**：`thresholds.min_tier`（`breakthrough` / `solid` / `incremental`）
- **Web 偏好面板**：最低影响力三档单选开关
- **URL 参数**：`?tier=breakthrough&tier=solid&tier=incremental`

## 从旧版本迁移

旧版本（含 `users:` 列表和飞书/企微/钉钉 webhook 推送）升级到当前版本需要：

1. 从 `config.yaml` 中删除 `users:` 列表
2. 把原 `users[].thresholds` 的阈值合并到新的全局 `thresholds:` 段（参考 `config.example.yaml`）
3. 删除任何 `feishu` / `wecom` / `dingtalk` 相关配置和环境变量
4. 已订阅但通过非邮件渠道接收推送的用户，需通过 `/subscribe` 重新订阅获取邮件推送

## 技术栈

- Python 3.11+
- arxiv — arXiv API 客户端
- anthropic — Claude API SDK（兼容接口）
- FastAPI + Jinja2 + HTMX — Web 前端
- APScheduler — 定时任务调度
- Click — CLI 框架
- Pydantic — 配置验证
- SQLite — 数据存储（WAL 模式，支持并发读写）

## License

MIT
