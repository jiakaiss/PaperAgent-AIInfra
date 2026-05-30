# Paper Agent - AI Infra 论文智能推送系统

自动从 arXiv 抓取高质量 AI Infrastructure 相关论文，通过 Claude 智能评分与分类，推送到邮件和企业微信/飞书/钉钉，并提供 Web UI 浏览与筛选。

## 功能特点

- 自动抓取 arXiv 上最新的 AI Infra 相关论文
- 使用 Claude 对论文进行相关度、质量打分，自动分类到 14 个子领域
- 支持邮件、企业微信、飞书、钉钉多渠道推送
- **多用户支持** — 不同用户可订阅不同子领域，独立推送
- **Web 浏览界面** — FastAPI + HTMX 论文浏览页，支持子领域筛选、标题搜索、时间范围过滤、分页
- **偏好设置** — 基于 localStorage 的浏览模式切换和子领域选择
- 可配置的定时任务（daemon 模式），每天自动抓取
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

### 运行

```bash
# 单次运行（dry-run 模式，不发通知）
paper-agent run --dry-run -c config.yaml

# 单次运行（指定用户）
paper-agent run --user alice --dry-run -c config.yaml

# 测试通知配置
paper-agent test --notifier feishu --user alice -c config.yaml

# 启动定时任务（每天 9:00 自动抓取）
paper-agent daemon -c config.yaml

# 启动 Web UI（http://127.0.0.1:8000）
paper-agent web -c config.yaml
```

> Windows 用户运行 CLI 前请设置 `set PYTHONIOENCODING=utf-8` 避免编码错误。

## 命令说明

| 命令 | 说明 |
|---|---|
| `paper-agent run` | 单次运行抓取、评分和推送 |
| `paper-agent daemon` | 启动定时任务守护进程 |
| `paper-agent web` | 启动 Web 浏览界面 |
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
