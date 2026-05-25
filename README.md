# Paper Agent - AI Infra 论文智能推送系统

自动从 arXiv 抓取高质量 AI Infrastructure 相关论文，通过 Claude 智能筛选，推送到邮件和企业微信/飞书/钉钉。

## 功能特点

- 自动抓取 arXiv 上最新的 AI Infra 相关论文
- 使用 Claude 对论文进行相关度和质量打分
- 支持邮件、企业微信、飞书、钉钉多渠道推送
- 可配置的定时任务，支持每天/每周推送
- SQLite 去重，避免重复推送

## 快速开始

### 安装

```bash
# 克隆项目
git clone <repo-url>
cd paper_agent

# 安装依赖
pip install -e .
```

### 配置

```bash
# 生成配置文件模板
paper-agent init

# 编辑 config.yaml，填入你的 API 密钥和 Webhook URL
```

### 运行

```bash
# 单次运行（dry-run 模式，不发通知）
paper-agent run --dry-run

# 测试通知配置
paper-agent test --notifier email

# 启动定时任务
paper-agent daemon
```

## 命令说明

- `paper-agent run` - 单次运行抓取和推送
- `paper-agent daemon` - 启动定时任务守护进程
- `paper-agent test` - 测试通知配置
- `paper-agent stats` - 查看数据库统计
- `paper-agent init` - 生成配置文件模板

## 技术栈

- Python 3.11+
- arxiv - arXiv API 客户端
- anthropic - Claude API SDK
- APScheduler - 定时任务调度
- Click - CLI 框架
- Pydantic - 配置验证
- SQLite - 数据存储

## License

MIT
