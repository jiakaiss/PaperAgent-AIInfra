# Paper Agent - AI Infra 论文智能推送系统

自动从 arXiv 抓取高质量 AI Infrastructure 相关论文，通过 Claude 智能评分与分类，推送到邮件和企业微信/飞书/钉钉，并提供 Web UI 浏览与筛选。

## 功能特点

- 自动抓取 arXiv 上最新的 AI Infra 相关论文
- 使用 Claude 对论文进行相关度、质量打分，自动分类到 14 个子领域
- 支持邮件、企业微信、飞书、钉钉多渠道推送
- **多用户支持** — 不同用户可订阅不同子领域，独立推送
- **Web 浏览界面** — FastAPI + HTMX 论文浏览页，支持子领域筛选、标题搜索、时间范围过滤、分页
- **偏好设置** — 基于 localStorage 的浏览模式切换和子领域选择，筛选条件会同步到 URL
- **Web 自助订阅** — 访问 `/subscribe` 输入邮箱和关注领域，自动加入定时邮件推送
- **全局邮件配置** — 订阅用户统一继承 `config.email` SMTP 配置，支持 `${ENV_VAR}` 注入敏感信息
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

# 编辑 config.yaml，填入你的 API 密钥、Webhook URL 和用户订阅
```

配置文件支持多用户，每个用户可独立配置订阅子领域、推送渠道和分数阈值。详见 `config.example.yaml`。

重要配置点：

- `scoring.api_key` / `scoring.base_url`：LLM API 配置，支持 `${ENV_VAR}` 环境变量注入
- `email`：全局 SMTP 配置，供 Web 自助订阅用户接收邮件推送
- `users`：手动配置的用户，可继续使用飞书/企业微信/钉钉/邮件等通知渠道
- `storage.db_path`：SQLite 数据库路径，Docker 部署时建议使用 `/app/data/paper_agent.db`
- `schedule`：daemon 后台查询频率和每日推送时间配置

### 运行

```bash
# 部署前自检
paper-agent doctor -c config.yaml

# 单次运行（dry-run 模式，不发通知）
paper-agent run --dry-run -c config.yaml

# 单次运行（指定用户）
paper-agent run --user alice --dry-run -c config.yaml

# 测试通知配置
paper-agent test --notifier feishu --user alice -c config.yaml

# 启动 daemon（后台按间隔查询入库，每天 9:00 从缓存推送）
paper-agent daemon -c config.yaml

# 启动 Web UI（http://127.0.0.1:8000）
paper-agent web -c config.yaml
```

Linux 本地/服务器可使用启动脚本：

```bash
# 同时启动 Web 和 daemon（前台运行，Ctrl+C 同时停止）
scripts/start-local.sh all

# 只启动 Web
scripts/start-local.sh web

# 只启动 daemon（后台查询 + 每日推送）
scripts/start-local.sh daemon

# 指定 Python 环境
PYTHON_BIN=/opt/conda/envs/paper_agent/bin/python scripts/start-local.sh all

# 本地检查（ruff + pytest + 可选 JS tests）
scripts/check.sh
```

常用 Linux/Docker 运维脚本：

```bash
# 部署/更新 Docker 服务
scripts/deploy.sh

# 查看服务状态和 Web 健康检查
scripts/status.sh

# 查看全部日志，或指定 web/daemon
scripts/logs.sh
scripts/logs.sh daemon

# 停止 Docker 服务
scripts/stop.sh

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
| `paper-agent doctor` | 检查部署前配置、数据库、Web 资源和邮件配置 |
| `paper-agent test` | 测试通知渠道配置 |
| `paper-agent stats` | 查看数据库统计信息 |
| `paper-agent init` | 生成配置文件模板 |

## Web UI

启动后访问 `http://127.0.0.1:8000`，支持以下功能：

- **子领域筛选** — 点击标签 chip 按子领域过滤论文
- **时间范围** — 按发布时间过滤（近一周/月/3月/半年/1年/3年）
- **标题搜索** — 按关键词搜索论文标题
- **偏好设置** — 切换「全量论文」/「自定义领域」浏览模式
- **分页** — 每页 25 篇，按综合得分（相关度 × 0.6 + 质量 × 0.4）排序
- **URL 可分享** — 筛选条件编码在 URL 中，可收藏或分享
- **自助订阅** — 访问 `/subscribe` 填写邮箱和关注领域，订阅信息写入 SQLite，daemon 后续按订阅推送

### Web 订阅说明

Web 订阅用户不会写入 `config.yaml`，而是保存在数据库 `subscriptions` 表中。应用启动时会把 active subscriptions 转换成运行时 `UserConfig`，并从全局 `email` 配置继承 SMTP 凭据。

```yaml
email:
  enabled: true
  smtp_host: ${SMTP_HOST}
  smtp_port: 587
  smtp_user: ${SMTP_USER}
  smtp_password: ${SMTP_PASSWORD}
  sender: ${SMTP_SENDER}
  use_tls: true
```

如果修改了 SMTP 配置，需要重启 Web/daemon 服务让已有订阅用户加载新配置。

## Docker / VPS 部署

项目提供 Docker Compose 部署方式，可在任意 Linux VPS 上同时运行 Web UI 和 daemon 定时任务：

```bash
cp .env.example .env
cp deploy/config/config.yaml.example deploy/config/config.yaml
# 编辑 .env 和 deploy/config/config.yaml
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
