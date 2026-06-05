# Docker VPS Deployment Guide

This guide deploys Paper Agent on a Linux VPS with Docker Compose.

## 1. Prerequisites

Install Docker and Docker Compose on your server.

```bash
docker --version
docker compose version
```

Open the public web port in your firewall/security group. The default host port is `8000`.

## 2. Prepare environment

```bash
git clone <your-repo-url> paper_agent
cd paper_agent
cp .env.example .env
cp deploy/config/config.yaml.example deploy/config/config.yaml
```

Edit `.env` and fill secrets:

```env
ANTHROPIC_API_KEY=...
SMTP_HOST=smtp.qq.com
SMTP_PORT=587
SMTP_USER=your@qq.com
SMTP_PASSWORD=your_smtp_authorization_code
SMTP_SENDER=your@qq.com
WEB_PORT=8000
TZ=Asia/Shanghai
```

Do not commit `.env` or `deploy/config/config.yaml`.

## 3. Review config

Edit `deploy/config/config.yaml` if you need to change:

- arXiv fetch keywords/categories
- scoring model/base URL
- schedule time
- thresholds and manually configured users

The Docker template stores runtime data under `/app/data`, mapped to `deploy/data` on the host.

## 4. Deploy

```bash
./scripts/deploy.sh
```

The script:

1. checks `.env` and `deploy/config/config.yaml`
2. creates `deploy/data`, `deploy/logs`, `deploy/backups`
3. builds the Docker image
4. runs `paper-agent doctor`
5. starts `web` and `daemon`

Access the app:

```text
http://SERVER_IP:8000
```

## 5. Operations

View logs:

```bash
docker compose logs -f web
docker compose logs -f daemon
```

Restart:

```bash
docker compose restart
```

Stop:

```bash
docker compose down
```

Upgrade after pulling new code:

```bash
git pull
docker compose build
docker compose up -d
```

## 6. Backup and restore

Backup SQLite database:

```bash
./scripts/backup.sh
```

Restore a backup:

```bash
./scripts/restore.sh deploy/backups/paper_agent-YYYYMMDD-HHMMSS.db
docker compose up -d
```

## 7. HTTPS and domain name

For production, put the app behind HTTPS. Recommended options:

- Caddy reverse proxy
- Nginx + Let's Encrypt
- Cloudflare Tunnel / Cloudflare proxy

Example Caddyfile:

```caddyfile
paper.example.com {
  reverse_proxy localhost:8000
}
```

## 8. Security checklist

- Keep `.env` private.
- Do not commit `deploy/config/config.yaml` if it contains secrets.
- Use HTTPS before sharing with public users.
- Restrict server firewall to necessary ports.
- Back up `deploy/data/paper_agent.db` regularly.
- Monitor logs for SMTP failures and API errors.

## 9. Troubleshooting

### `doctor` reports missing SMTP fields

Fill these in `.env`:

```env
SMTP_HOST=...
SMTP_USER=...
SMTP_PASSWORD=...
SMTP_SENDER=...
```

### Web container unhealthy

Check logs:

```bash
docker compose logs web
```

Then verify the health endpoint:

```bash
curl http://localhost:8000/health
```

### Port already in use

Change `WEB_PORT` in `.env` or stop the process using the port.

### Database permission errors

Ensure host directories exist and are writable:

```bash
mkdir -p deploy/data deploy/logs deploy/backups
```

### Emails not received

Check:

1. `email.enabled=true` in `deploy/config/config.yaml`
2. SMTP credentials in `.env`
3. spam/junk folder
4. daemon logs: `docker compose logs daemon`
