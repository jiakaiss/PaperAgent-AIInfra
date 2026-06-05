## Why

当前项目可以在本地运行，但要部署到外网给其他人访问，需要手动准备 Python 环境、配置文件、后台 daemon、数据库持久化、SMTP/LLM 密钥和服务启动方式，步骤多且容易遗漏。提供 Docker + VPS 一键部署能力，可以让项目在任意云服务器上稳定运行 Web UI 和定时推送任务，并为后续域名/HTTPS/备份打基础。

## What Changes

- 新增 Docker 部署产物：`Dockerfile`、`.dockerignore`、`docker-compose.yml`
- 新增环境变量模板：`.env.example`，覆盖 LLM API、SMTP、服务端口、数据库路径等外网部署必填项
- 新增部署脚本：`scripts/deploy.sh`，支持构建镜像、创建数据目录、启动 web + daemon 服务
- 新增运维脚本：`scripts/backup.sh` 和 `scripts/restore.sh`，用于备份/恢复 SQLite 数据库
- 新增部署前自检命令：`paper-agent doctor -c config.yaml`，检查配置、数据库可写性、SMTP 可用性、Web 静态资源和端口配置
- 新增部署文档：说明 VPS 准备、环境变量填写、启动、查看日志、备份、升级、常见问题
- 保持现有本地开发方式不变；Docker 部署为新增能力，不破坏现有 CLI/API

## Capabilities

### New Capabilities
- `docker-deployment`: Docker/VPS 一键部署能力，包括镜像构建、compose 编排、数据持久化、web/daemon 双服务运行
- `deployment-doctor`: 部署前/运行时自检能力，检查配置、依赖、数据库、SMTP、Web 资源和端口
- `deployment-operations`: 部署运维能力，包括日志查看、备份、恢复、升级和故障排查

### Modified Capabilities
- `web-server`: 明确 Web 服务在容器中必须绑定 `0.0.0.0`，并提供健康检查用于容器编排
- `global-email-config`: 明确 Docker 部署下 SMTP 凭据应通过环境变量注入，不能写死在镜像中

## Impact

- **Repo root**: 新增 Dockerfile、docker-compose.yml、.dockerignore、.env.example
- **scripts/**: 新增 deploy/backup/restore 等运维脚本
- **CLI**: 新增 `paper-agent doctor` 命令
- **Docs**: 更新 README/CLAUDE.md 或新增部署文档
- **Runtime**: Docker Compose 将运行两个服务：`web` 和 `daemon`，共享 SQLite 数据卷
- **Security**: 敏感信息通过 `.env` 注入；`config.yaml`/`.env` 不应提交到 git
