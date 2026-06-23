# Windows → Linux 服务器迁移指南

本文档记录把 `paper_agent` 从当前 Windows 部署迁到 Linux 服务器的完整步骤。

## 当前部署形态（迁出端）

- **运行方式**：原生 Python（非 Docker），通过 `scripts/daemon.sh` + `scripts/web.sh` 启动
- **数据库**：项目根目录 `paper_agent.db`（SQLite，含 WAL 模式）
- **配置文件**：项目根目录 `config.yaml`
- **日志**：项目根目录 `logs/`
- **公网入口**：Cloudflare Tunnel（Token 模式），域名 `paper.aiinfraagent.com`
- **cloudflared**：Windows 服务自启，token 存在服务的 `PathName` 参数里

## 迁移后目标形态（迁入端）

- **OS**：Ubuntu 22.04 / 24.04 LTS
- **运行方式**：Docker Compose（用项目里现有的 `docker-compose.yml`），路径切换到 `deploy/data/`、`deploy/logs/`
- **公网入口**：Cloudflare Tunnel（**同一个 token**，DNS / 域名零修改）
- **进程管理**：cloudflared 用 systemd，paper-agent 用 docker compose
- **备份**：cron 每日 sqlite `.backup` + 可选 rclone 同步到对象存储

---

## 一、必须拷贝的文件（**核心 3 个**）

按重要性排序：

### 1. 数据库 `paper_agent.db`（**最重要，丢了不可恢复**）

- **路径**：`<project_root>/paper_agent.db`
- **包含**：所有已评分论文缓存（约几 MB ~ 几十 MB）、订阅用户列表、邮件发送记录
- **拷贝前必须停服务**（否则 WAL 未 checkpoint，文件不一致）
- **建议方式**：用 `sqlite3 .backup` 做一致性快照（自动 checkpoint），不要直接拷裸文件

```bash
# Windows 端，项目根目录
sqlite3 paper_agent.db ".backup paper_agent-migrate.db"
```

> ⚠️ 不要拷 `paper_agent.db-wal` 和 `paper_agent.db-shm`——`.backup` 命令已经把它们合并进新文件了。

### 2. 配置文件 `config.yaml`（**必须**）

- **路径**：`<project_root>/config.yaml`
- **包含**：fetch / scoring / email / thresholds / admin / citations 等全部业务配置
- **注意**：Docker 部署时需要改两个路径（见下文「阶段二」第 3 步）

### 3. Cloudflare Tunnel Token（**必须**，用于公网入口零中断切换）

- **位置**：Windows 服务的命令行参数里（不在文件里）
- **获取方式**：
  ```powershell
  # PowerShell（管理员）
  Get-WmiObject Win32_Service -Filter "Name='cloudflared'" | Select-Object -ExpandProperty PathName
  ```
- **token 是 `--token` 后面的一长串字符串**，形如 `eyJhIjoi...`
- ⚠️ **安全**：token = 这条 tunnel 的密码，**不要贴到任何公开地方**（聊天群、git、截图）

---

## 二、不需要拷贝的文件（**有就别拷**）

| 类别 | 文件 | 不拷的原因 |
|------|------|-----------|
| Python 缓存 | `__pycache__/`、`*.pyc`、`.venv/`、`uv.lock` 编译产物 | Linux 上重新装，平台不兼容 |
| 日志 | `logs/daemon.log`、`logs/web.log`、`logs/*.stdout.log` | 老日志没价值，新机器从头记 |
| 守护态文件 | `logs/daemon.pid`、`paper_agent.db.daemon.json` | 旧 PID/心跳，新机器会重写 |
| 备份 | `deploy/backups/*.db`、`deploy/data/` | 备份留 Windows 上做兜底，**不要带过去**（新备份从新机器开始） |
| `.env` | 你目前根目录就没有，跳过 | Docker 部署时再现场创建（见阶段二） |
| WAL 文件 | `paper_agent.db-wal`、`paper_agent.db-shm` | 用 `.backup` 命令已合并 |
| OpenSpec / docs | `openspec/`、`docs/` | 跟代码一起从 git 拉，不用单独拷 |

代码本身**也不用拷**——直接在 Linux 上 `git clone` 最干净。

---

## 三、完整迁移流程

### 阶段一：Linux 服务器初始化（一次性，约 15 分钟）

```bash
# 以 root 登录新服务器
apt update && apt upgrade -y
apt install -y curl git ufw sqlite3 ca-certificates

# 时区（保证 daemon 调度时间和现在一致）
timedatectl set-timezone Asia/Shanghai

# 创建非 root 部署账号
adduser --disabled-password --gecos "" deploy
usermod -aG sudo deploy

# Swap（2GB 内存机器强烈建议，4GB 也建议开 1GB）
fallocate -l 2G /swapfile
chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
sysctl vm.swappiness=10

# 防火墙：用 Cloudflare Tunnel 的话，22 都可以不开放（用 SSH 跳板/Tailscale）
# 这里保守起见开 22，公网 80/443 不需要（流量走 tunnel）
ufw allow 22/tcp
ufw --force enable

# 装 Docker
curl -fsSL https://get.docker.com | sh
usermod -aG docker deploy

# 切到 deploy 账号
su - deploy
```

### 阶段二：把项目跑起来（**不切公网流量**，约 10 分钟）

```bash
# 1. clone 仓库
cd ~
git clone <你的 git 仓库地址> paper_agent
cd paper_agent

# 2. 准备 deploy 配置目录
cp config.example.yaml deploy/config/config.yaml
```

#### 3. 改 `deploy/config/config.yaml` 关键路径

对照你当前 `config.yaml` 的内容，**把 Windows 路径改成 Docker 内路径**：

```yaml
# 原（Windows 上）              # 改成（Docker 内路径）
storage:
  db_path: paper_agent.db   →   db_path: /app/data/paper_agent.db

logging:
  file: logs/daemon.log     →   file: /app/logs/paper-agent.log
```

其他字段（fetch / scoring / email / admin / citations / public_base_url）**保持不变**。

> 提示：可以直接把你 Windows 上的 `config.yaml` 整个拷成 `deploy/config/config.yaml`，再用 `sed`/编辑器改这两个路径。

#### 4. 创建 `.env`

```bash
cat > .env <<'EOF'
ANTHROPIC_API_KEY=sk-ant-...你的Claude key...
SMTP_PASSWORD=你的QQ邮箱16位授权码
ADMIN_PASSWORD=你的admin密码至少16位
TZ=Asia/Shanghai
WEB_PORT=8000
EOF
chmod 600 .env
```

> Windows 上你目前没有 `.env`，原生模式下这些 key 估计是在 `config.yaml` 写死或用环境变量传的——迁过来 Docker 模式统一放 `.env` 更干净。

#### 5. 从 Windows 拷数据库过来

**Windows 端**（先停服务保证 db 一致）：

```bash
# 停 daemon 和 web
cd C:/Users/Administrator/Desktop/code/paper_agent
./scripts/daemon.sh stop 2>/dev/null || true
./scripts/web.sh stop 2>/dev/null || true
# 或者按你实际启动方式停掉对应进程

# 做一致性快照
sqlite3 paper_agent.db ".backup paper_agent-migrate.db"
```

**Linux 端**接收（在 Windows PowerShell 里跑 scp）：

```powershell
# Windows
scp C:\Users\Administrator\Desktop\code\paper_agent\paper_agent-migrate.db deploy@<linux-ip>:/home/deploy/paper_agent/deploy/data/paper_agent.db
```

或者用 `rsync`：

```bash
# Linux 端（如果装了 rsync 且 Windows 有 ssh）
rsync -avz administrator@<windows-ip>:/c/Users/Administrator/Desktop/code/paper_agent/paper_agent-migrate.db deploy/data/paper_agent.db
```

#### 6. 起服务 + 健康检查

```bash
cd ~/paper_agent
./scripts/deploy.sh                              # 自动 build + doctor + up -d
./scripts/status.sh                              # 健康检查

# 看实时日志
docker compose logs -f --tail=50

# 验证内部可访问
curl http://127.0.0.1:8000/health                # 应返回 ok

# 验证数据库内容
docker compose exec web paper-agent stats -c /app/config.yaml
```

**到这一步，Linux 服务器已经能在本地访问，Windows 上的公网入口还在正常服务。**

### 阶段三：切换公网流量（窗口期 ~10 秒）

#### 1. Linux 端装 cloudflared（先装但不启动）

```bash
# 在 deploy 用户下
curl -L --output /tmp/cloudflared.deb \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i /tmp/cloudflared.deb
cloudflared --version

# 装成 systemd 服务（粘贴从 Windows 取出的 token）
sudo cloudflared service install <你的token>

# 检查状态——如果已自动起来了，先停掉（防止和 Windows 并发）
sudo systemctl status cloudflared
sudo systemctl stop cloudflared
sudo systemctl disable cloudflared
```

#### 2. 切换（按顺序执行，越快越好）

```powershell
# === Windows 上（PowerShell 管理员）===
Stop-Service cloudflared
Set-Service cloudflared -StartupType Disabled
```

```bash
# === Linux 上 ===
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
sudo systemctl status cloudflared              # 应显示 active (running)

# 看连接日志
sudo journalctl -u cloudflared -f --no-pager
# 看到 4 行 "Registered tunnel connection" 表示已连上 Cloudflare 4 个边缘节点
```

#### 3. 验证

- 浏览器（手机也行）访问 `https://paper.aiinfraagent.com` —— 应正常打开
- 检查 `/admin` —— 应弹 Basic Auth
- 发一封测试邮件给自己：
  ```bash
  docker compose exec web paper-agent test --notifier email --user your@qq.com -c /app/config.yaml
  ```

### 阶段四：观察期 + 清理（1-2 天后）

#### 1. 观察期（不少于 24 小时）

- 让定时任务跑过至少一次完整周期（看 `digest_at` 时间）
- 检查邮件是否正常送达
- 看 admin 后台数据是否正常
- **Windows 上的 paper-agent 和 cloudflared 保留，但都是停止状态**，作为回滚兜底

#### 2. 配置每日自动备份

```bash
crontab -e
```

加这行：

```cron
0 3 * * * cd /home/deploy/paper_agent && ./scripts/backup.sh && find deploy/backups -name "paper_agent-*.db" -mtime +30 -delete
```

可选：rclone 同步到 Cloudflare R2 / Backblaze B2（防服务器整体挂掉）：

```bash
curl https://rclone.org/install.sh | sudo bash
rclone config                                  # 加 remote
# crontab 加：
# 30 3 * * * rclone sync /home/deploy/paper_agent/deploy/backups r2:my-backups/paper-agent --max-age 7d
```

#### 3. 清理 Windows（确认 Linux 稳定后）

```powershell
# 彻底关 cloudflared
Stop-Service cloudflared -ErrorAction SilentlyContinue
sc.exe delete cloudflared

# 卸载 cloudflared（可选，留着也行）
# 控制面板 → 程序卸载

# 清理 paper_agent 工作目录（建议先在另一台机器留个 zip 归档）
# 不要删 git 仓库，里面有未推送的修改要先 commit + push
```

---

## 四、回滚预案（5 分钟内回到 Windows）

如果 Linux 上发现严重问题：

```powershell
# Windows
Set-Service cloudflared -StartupType Automatic
Start-Service cloudflared
```

```bash
# Linux
sudo systemctl stop cloudflared
```

**域名瞬间切回 Windows**——Cloudflare 边缘看到 Windows tunnel 客户端连进来，路由表自动更新。整个过程不需要改 DNS。

> ⚠️ 前提：Windows 上 paper-agent daemon + web 也要重新启动。建议在迁移期间 Windows 端**只停 cloudflared，不停 paper-agent**，让数据库继续接收（虽然不对外服务），万一回滚数据更新。但这种情况下两边数据库会分叉，需要选定一份为准——所以更安全的做法是 Windows 端全停，回滚时再启动。

---

## 五、文件清单速查表（**打包带走啥**）

```
必拷（3 个文件）：
✅ paper_agent.db                      → 经 sqlite3 .backup 导出后传
✅ config.yaml                          → 复制全部内容，改 2 处路径
✅ cloudflared token                    → 从 Windows 服务命令行取

可选拷（看你需要）：
○ 自己改过的 scripts/*.sh               → 一般不用，git 仓库里有
○ 自定义 deploy/config/Caddyfile        → 如果你后续不走 cloudflared 才需要

不拷（拷了反而出问题）：
✗ paper_agent.db-wal / -shm           → .backup 已合并
✗ logs/* / *.pid                      → 旧状态干扰新服务
✗ __pycache__ / .venv                 → 平台不兼容
✗ deploy/data/* / deploy/backups/*    → 用 sqlite3 .backup 替代
```

---

## 六、迁移后常用运维命令

```bash
cd ~/paper_agent

# 看状态
./scripts/status.sh
docker compose ps
docker compose logs -f daemon

# 改配置
nano deploy/config/config.yaml          # 改 yaml
nano .env                                # 改密钥
docker compose restart                   # 立即生效，不用 rebuild

# 代码更新
git pull
docker compose build web
docker compose up -d

# 手动跑任务
docker compose exec web paper-agent run --dry-run -c /app/config.yaml
docker compose exec web paper-agent rescore --missing-fields -c /app/config.yaml
docker compose exec web paper-agent refresh-citations -c /app/config.yaml

# 查数据库
sqlite3 deploy/data/paper_agent.db
# > .tables
# > SELECT COUNT(*) FROM papers;

# 备份/恢复
./scripts/backup.sh
./scripts/restore.sh deploy/backups/paper_agent-20260622-030000.db

# Cloudflare Tunnel
sudo systemctl status cloudflared
sudo journalctl -u cloudflared -f
sudo systemctl restart cloudflared
```

---

## 七、常见坑

| 现象 | 原因 | 解决 |
|------|------|------|
| `docker compose` 起不来，提示 db 找不到 | `deploy/data/` 没创建或权限不对 | `mkdir -p deploy/data && cp paper_agent-migrate.db deploy/data/paper_agent.db` |
| 切完 cloudflared 域名打不开 | Windows 上的 cloudflared 没真正停 | `Get-Service cloudflared` 确认 Stopped；必要时 `sc.exe delete cloudflared` |
| 邮件发不出去 | QQ 邮箱境外 IP 风控 | 浏览器登录 QQ 邮箱网页版确认新地点；必要时重新生成授权码更新 `.env` |
| Claude 连不上 | 服务器到 `api.anthropic.com` 不通 | `curl -I https://api.anthropic.com` 验证；国内服务器需配代理 |
| admin 弹了认证但密码不对 | `.env` 里 `ADMIN_PASSWORD` 改了但容器没重启 | `docker compose restart web` |
| 数据库读取报 `database is locked` | WAL/SHM 没清干净 | `restore.sh` 会自动 `rm -f *-wal *-shm`，手动迁移要记得做 |
| daemon 日志一直没有新条目 | 时区不对，scheduled 时间还没到 | `docker compose exec web date` 确认是 CST；`.env` 里 `TZ=Asia/Shanghai` |

---

## 八、相关文档

- **`CLAUDE.md`**：项目架构总览、配置说明、Troubleshooting
- **`scripts/deploy.sh`**：部署脚本本体
- **`scripts/backup.sh` / `restore.sh`**：备份恢复
- **`docker-compose.yml`**：容器编排定义
- **Cloudflare Tunnel 官方文档**：https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
