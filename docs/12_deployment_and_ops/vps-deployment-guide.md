# VPS Deployment Guide

Step-by-step guide to deploy the RSI Bot on a fresh VPS (Ubuntu/Debian).

---

## 1. VPS Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 1 vCPU | 2 vCPU |
| RAM | 1 GB | 2 GB |
| Disk | 10 GB | 20 GB (for backtest data) |
| OS | Ubuntu 22.04+ / Debian 12+ | Ubuntu 24.04 LTS |
| Python | 3.11+ | 3.12 |

---

## 2. Can I Install in `/opt`?

**Yes**, `/opt` is a perfectly valid location. It's the standard Linux directory for
optional/third-party software. However, the deploy scripts and systemd services in this
repo default to `/home/user/rsi_bot`. You have two options:

### Option A: Use `/home/<your-user>/rsi_bot` (default — zero config changes)

Everything works out of the box. The systemd services, deploy scripts, and paths all
match. **This is the recommended option** unless you have a specific reason to use `/opt`.

### Option B: Use `/opt/rsi_bot` (requires path updates)

After cloning, update these files to replace `/home/user/rsi_bot` with `/opt/rsi_bot`:

| File | What to change |
|------|----------------|
| `deploy/deploy.sh` | `BOT_DIR="/opt/rsi_bot"` |
| `deploy/check_deploy.sh` | `BOT_DIR="/opt/rsi_bot"` |
| `deploy/force_deploy.sh` | `BOT_DIR="/opt/rsi_bot"` |
| `deploy/systemd/rsi-bot.service` | `WorkingDirectory`, `Environment`, `ExecStart` |
| `deploy/systemd/check-deploy.service` | `WorkingDirectory`, `ExecStart` |

Also ensure your bot user has ownership:

```bash
sudo mkdir -p /opt/rsi_bot
sudo chown your-user:your-user /opt/rsi_bot
```

The rest of this guide uses `/home/user/rsi_bot` as the default. Replace paths if using `/opt`.

---

## 3. Initial Server Setup

### 3.1 Create a dedicated user (if not using root)

```bash
sudo adduser botuser
sudo usermod -aG sudo botuser
su - botuser
```

### 3.2 Install system dependencies

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.11 python3.11-venv python3-pip git
```

### 3.3 (Optional) Firewall — lock down inbound ports

The bot only needs **outbound** HTTPS. No inbound ports required for the trading bot
itself. Only open SSH for your management access.

```bash
sudo ufw allow OpenSSH
sudo ufw enable
```

If you want to run the backtest UI remotely, also open port 8000:

```bash
sudo ufw allow 8000/tcp   # Only if running backtest API
```

---

## 4. Clone and Configure

### 4.1 Clone the repository

```bash
cd ~
git clone https://github.com/heavendragon-17/rsi_bot.git
cd rsi_bot
```

### 4.2 Create Python virtual environment

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 4.3 Configure environment variables

```bash
cp .env.example .env
nano .env
```

Fill in your keys:

```
BINANCE_API_KEY=your_mainnet_api_key
BINANCE_SECRET_KEY=your_mainnet_secret_key
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

> **Security**: On Binance, create an API key with **Futures trading only**,
> **no withdrawals**, and **IP whitelist** restricted to your VPS IP.

### 4.4 Configure the bot

```bash
nano config.yaml
```

Key settings to adjust for production:

```yaml
bot:
  active: true
  mode: "live"      # or "paper" for testnet first
  debug: false      # disable verbose logging in production

risk:
  max_position_size_pct: 0.20    # start conservative
  risk_per_trade_pct: 0.01       # 1% risk per trade
  leverage: 5                     # don't max out leverage
```

### 4.5 Smoke test

```bash
source venv/bin/activate
python -c "
from app.core import interfaces, config, constants, actions
from app.data import indicators
cfg = config.AppConfig.from_yaml('config.yaml')
print(f'Config loaded: mode={cfg.bot.mode}, symbols={cfg.symbols}')
print('Smoke test PASSED')
"
```

---

## 5. Set Up systemd Services

### 5.1 Install the bot service

```bash
sudo cp deploy/systemd/rsi-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable rsi-bot
sudo systemctl start rsi-bot
```

### 5.2 Verify it's running

```bash
sudo systemctl status rsi-bot
journalctl -u rsi-bot -f   # follow live logs
```

### 5.3 (Optional) Install auto-deploy timer

If you want automatic deployments when you push tagged versions:

```bash
sudo cp deploy/systemd/check-deploy.service /etc/systemd/system/
sudo cp deploy/systemd/check-deploy.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now check-deploy.timer
```

### 5.4 Create deploy log file

```bash
sudo touch /var/log/rsi-bot-deploy.log
sudo chown user:user /var/log/rsi-bot-deploy.log
```

---

## 6. Managing the Bot

### Start / Stop / Restart

```bash
sudo systemctl start rsi-bot
sudo systemctl stop rsi-bot
sudo systemctl restart rsi-bot
```

### View logs

```bash
# Live tail
journalctl -u rsi-bot -f

# Last 100 lines
journalctl -u rsi-bot -n 100

# Since today
journalctl -u rsi-bot --since today
```

### Check bot health

```bash
cat /tmp/rsi_bot_status.json | python3 -m json.tool
```

### Manual deploy (SSH)

```bash
cd ~/rsi_bot
git pull origin production
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart rsi-bot
```

Or use the deploy script:

```bash
deploy/force_deploy.sh         # auto-detects latest tag
deploy/force_deploy.sh v1.2.3  # specific version
```

---

## 7. Running the Backtest UI (Optional)

If you want the backtest web interface on your VPS:

```bash
# Terminal 1: Backend API
source venv/bin/activate
python -m uvicorn app.api.main:app --host 0.0.0.0 --port 8000

# Terminal 2: Frontend (requires Node.js)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
cd ui
npm install
npm run build    # production build
npx serve build  # serve static files on port 3000
```

For production, consider using nginx as a reverse proxy in front of both services.

---

## 8. Security Checklist

- [ ] API key: Futures only, no withdrawals, IP-whitelisted to VPS IP
- [ ] `.env` file permissions: `chmod 600 .env`
- [ ] Firewall: Only SSH open inbound (+ 8000 if running backtest UI)
- [ ] SSH: Key-based auth only, disable password login
- [ ] Bot user: Non-root, minimal sudo privileges
- [ ] API key rotation: Every 90 days
- [ ] Monitor via Telegram notifications

---

## 9. Deployment Flow Summary

```
Local Development
    │
    ├── git tag v1.2.3 && git push --tags
    │
    ▼
GitHub Actions (CI)
    │
    ├── Run tests
    ├── Merge to production branch
    │
    ▼
VPS (check-deploy.timer — runs every 60s)
    │
    ├── git fetch origin production
    ├── Compare deployed SHA vs remote SHA
    ├── Check /tmp/rsi_bot_status.json for open positions
    ├── If positions clear → deploy.sh
    │   ├── pip install -r requirements.txt
    │   ├── Smoke test
    │   ├── Write VERSION file
    │   ├── systemctl restart rsi-bot
    │   └── Health check (60s timeout)
    └── If positions open → wait and retry next minute
```

---

## 10. Troubleshooting

| Problem | Fix |
|---------|-----|
| Bot won't start | `journalctl -u rsi-bot -n 50` — check for import/config errors |
| "Config validation failed" | Run the smoke test manually (section 4.5) |
| No Telegram notifications | Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env` |
| Deploy stuck in "waiting" | Create force flag: `touch /tmp/rsi_bot_force_deploy` |
| Cancel pending deploy | `touch /tmp/rsi_bot_cancel_deploy` |
| Status file stale | Bot may have crashed — `systemctl restart rsi-bot` |
| Permission denied on `/opt` | `sudo chown -R your-user:your-user /opt/rsi_bot` |
