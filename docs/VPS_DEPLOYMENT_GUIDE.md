# VPS Deployment Guide — RSI Bot

Complete guide to deploy the RSI bot on a VPS with automatic updates from the `production` branch.

---

## Table of Contents

1. [VPS Requirements](#1-vps-requirements)
2. [Initial VPS Setup](#2-initial-vps-setup)
3. [Clone the Repository](#3-clone-the-repository)
4. [Python Environment Setup](#4-python-environment-setup)
5. [Configure the Bot](#5-configure-the-bot)
6. [Test Run](#6-test-run)
7. [Install Systemd Services](#7-install-systemd-services)
8. [Start the Bot](#8-start-the-bot)
9. [Enable Auto-Deploy](#9-enable-auto-deploy)
10. [How Auto-Deploy Works](#10-how-auto-deploy-works)
11. [Day-to-Day Operations](#11-day-to-day-operations)
12. [Deploying a New Version](#12-deploying-a-new-version)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. VPS Requirements

| Requirement | Minimum |
|---|---|
| OS | Ubuntu 22.04+ / Debian 12+ |
| RAM | 1 GB |
| CPU | 1 vCPU |
| Disk | 10 GB |
| Python | 3.11+ |
| Network | Outbound HTTPS (Binance API, Telegram) |

---

## 2. Initial VPS Setup

SSH into your VPS and install system dependencies:

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.11+ and essentials
sudo apt install -y python3.11 python3.11-venv python3.11-dev git curl

# Verify Python version (must be 3.11+)
python3.11 --version

# (Optional) If python3.11 is not available in default repos:
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev
```

> **Note:** If your distro ships Python 3.12+, use that instead. Replace `python3.11` with `python3.12` throughout this guide.

### Create a dedicated user (recommended)

```bash
# If you want a dedicated user instead of root:
sudo adduser rsibot
sudo usermod -aG sudo rsibot
su - rsibot
```

Or just use your existing user — the deploy scripts use `$USER` by default.

---

## 3. Clone the Repository

```bash
# Navigate to home directory
cd ~

# Clone the repo
git clone https://github.com/heavendragon-17/rsi_bot.git
cd rsi_bot

# Switch to the production branch
git checkout production
```

> **Important:** The bot runs from the `production` branch on the VPS. The auto-deploy system watches this branch for new tagged commits.

---

## 4. Python Environment Setup

```bash
# Create virtual environment
python3.11 -m venv venv

# Activate it
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

Verify the installation:

```bash
python -c "from app.core import interfaces, config, constants, actions; print('OK')"
```

---

## 5. Configure the Bot

### 5a. Environment Variables

```bash
# Copy the example env file
cp .env.example .env

# Edit with your actual keys
nano .env
```

Fill in these **required** values:

```env
# Binance Futures (mainnet for live trading)
BINANCE_API_KEY=your_mainnet_api_key
BINANCE_SECRET_KEY=your_mainnet_secret_key

# Telegram Notifications
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
```

> **Security:** The `.env` file contains secrets. Never commit it to git. It's already in `.gitignore`.

### 5b. Bot Configuration

```bash
nano config.yaml
```

Key settings to change for production:

```yaml
bot:
  active: true
  mode: "live"       # Change from "sim" to "live" for real trading
  debug: false       # Disable verbose logging in production

exchange:
  name: "binanceusdm"

strategy: "rsi_no_retest"    # Your chosen strategy

symbols:
  - "BTC/USDT"
  - "ETH/USDT"
  # ... add your symbols

risk:
  max_position_size_pct: 10
  risk_per_trade_pct: 0.002
  leverage: 10
```

> **Warning:** Double-check `mode: "live"` means real money. Start with `mode: "paper"` (Binance testnet) to verify everything works first.

---

## 6. Test Run

Before setting up systemd, verify the bot starts correctly:

```bash
source venv/bin/activate
python main.py
```

You should see:
- Config loaded successfully
- Exchange connection established
- WebSocket streams connecting
- Telegram notification sent (if configured)

Press `Ctrl+C` to stop once you confirm it works.

---

## 7. Install Systemd Services

This installs three systemd units:
- **rsi-bot.service** — Runs the bot, auto-restarts on crash
- **check-deploy.service** — Checks for new versions
- **check-deploy.timer** — Triggers the check every 60 seconds

### 7a. Update deploy paths (if needed)

If your bot is NOT at `/home/user/rsi_bot`, edit `deploy/deploy_env.sh`:

```bash
nano deploy/deploy_env.sh
```

Change `BOT_DIR` to your actual path:

```bash
BOT_DIR="/home/youruser/rsi_bot"
```

### 7b. Allow passwordless restart (required for auto-deploy)

The deploy script needs `sudo systemctl restart rsi-bot` without a password prompt:

```bash
sudo visudo -f /etc/sudoers.d/rsi-bot
```

Add this line (replace `user` with your actual username):

```
user ALL=(ALL) NOPASSWD: /bin/systemctl restart rsi-bot, /bin/systemctl stop rsi-bot
```

### 7c. Run the installer

```bash
sudo deploy/install.sh
```

This generates the systemd unit files and enables the bot service.

---

## 8. Start the Bot

```bash
# Start the bot
sudo systemctl start rsi-bot

# Check status
sudo systemctl status rsi-bot

# View live logs
journalctl -u rsi-bot -f
```

The bot will automatically restart if it crashes (after 10 seconds).

---

## 9. Enable Auto-Deploy

```bash
sudo systemctl enable --now check-deploy.timer
```

Verify the timer is active:

```bash
systemctl list-timers | grep check-deploy
```

You should see `check-deploy.timer` listed with the next trigger time.

---

## 10. How Auto-Deploy Works

The auto-deploy system is tag-based and position-aware:

```
Every 60s:
  check-deploy.timer → check_deploy.sh
    ├── git fetch origin production --tags
    ├── Compare deployed SHA vs remote production HEAD
    ├── If same → exit (nothing to do)
    ├── If different → check for semver tag (v1.2.3)
    │   ├── No tag → skip (won't deploy untagged commits)
    │   └── Has tag → check open positions
    │       ├── Positions open → wait (defer deploy)
    │       └── No positions → deploy!
    │           ├── pip install requirements
    │           ├── Smoke test (import + config validation)
    │           ├── Write VERSION file
    │           ├── Restart rsi-bot service
    │           └── Health check (12 attempts × 5s)
    └── Done
```

### Key safety features:
- **Won't deploy while positions are open** — waits until all positions close
- **Requires a semver tag** — untagged commits are ignored
- **Smoke test** — validates imports and config before restarting
- **Health check** — if bot doesn't come up healthy, it's stopped
- **Stale detection** — if status file is >5 min old, deploy is deferred

---

## 11. Day-to-Day Operations

### View bot logs
```bash
journalctl -u rsi-bot -f              # Live tail
journalctl -u rsi-bot --since "1h ago" # Last hour
journalctl -u rsi-bot -n 100          # Last 100 lines
```

### View deploy logs
```bash
cat /var/log/rsi-bot-deploy.log
tail -f /var/log/rsi-bot-deploy.log
```

### Check deploy state
```bash
cat /tmp/rsi_bot_deploy_state.json | python3 -m json.tool
```

### Check bot health status
```bash
cat /tmp/rsi_bot_status.json | python3 -m json.tool
```

### Check current deployed version
```bash
cat ~/rsi_bot/VERSION | python3 -m json.tool
```

### Restart the bot manually
```bash
sudo systemctl restart rsi-bot
```

### Stop the bot
```bash
sudo systemctl stop rsi-bot
```

### Force deploy (skip position check)
```bash
~/rsi_bot/deploy/force_deploy.sh
# Or with a specific tag:
~/rsi_bot/deploy/force_deploy.sh v1.2.3
```

### Cancel a pending deploy
```bash
touch /tmp/rsi_bot_cancel_deploy
```

---

## 12. Deploying a New Version

This is the workflow you'll use every time you want to push an update to the VPS:

### From your local machine:

```bash
# 1. Make sure you're on the main development branch
git checkout mua-tren-the-nang

# 2. Do your work, commit changes
git add ...
git commit -m "your changes"

# 3. Merge into production
git checkout production
git merge mua-tren-the-nang

# 4. Tag with a semver version
git tag v1.0.0    # Use appropriate version number

# 5. Push production branch AND tags
git push origin production --tags
```

### What happens on the VPS:

1. Within 60 seconds, `check-deploy.timer` fires
2. `check_deploy.sh` fetches and sees the new tag
3. If no positions are open → deploys immediately
4. If positions are open → waits and retries every 60s
5. `deploy.sh` installs deps, runs smoke test, restarts bot
6. Health check confirms bot is running the new version
7. You get a Telegram notification (if configured)

---

## 13. Troubleshooting

### Bot won't start

```bash
# Check service status for error messages
sudo systemctl status rsi-bot

# Check recent logs
journalctl -u rsi-bot -n 50

# Try running manually to see errors
cd ~/rsi_bot
source venv/bin/activate
python main.py
```

### Auto-deploy not working

```bash
# Check timer is running
systemctl list-timers | grep check-deploy

# Check deploy logs
tail -20 /var/log/rsi-bot-deploy.log

# Check deploy state
cat /tmp/rsi_bot_deploy_state.json

# Manual test of check script
~/rsi_bot/deploy/check_deploy.sh
```

### Deploy stuck in "waiting" state

The bot is waiting for open positions to close. Options:
- Wait for positions to close naturally
- Force deploy: `~/rsi_bot/deploy/force_deploy.sh`
- Cancel: `touch /tmp/rsi_bot_cancel_deploy`

### Permission denied on systemctl

Make sure the sudoers rule is set up (Step 7b):
```bash
sudo visudo -f /etc/sudoers.d/rsi-bot
# Add: user ALL=(ALL) NOPASSWD: /bin/systemctl restart rsi-bot, /bin/systemctl stop rsi-bot
```

### Git fetch fails

Check SSH/HTTPS access to GitHub:
```bash
# If using HTTPS:
git remote -v
# Should show: https://github.com/heavendragon-17/rsi_bot.git

# If using SSH:
ssh -T git@github.com
```

For HTTPS with private repo, set up a credential helper or personal access token:
```bash
git config --global credential.helper store
git pull origin production
# Enter username + personal access token (not password)
```

### Bot crashes repeatedly

```bash
# Check if it's restarting too fast
systemctl status rsi-bot
# Look for "start-limit-hit"

# Reset the failure counter
sudo systemctl reset-failed rsi-bot
sudo systemctl start rsi-bot
```

---

## Quick Reference Card

| Action | Command |
|---|---|
| Start bot | `sudo systemctl start rsi-bot` |
| Stop bot | `sudo systemctl stop rsi-bot` |
| Restart bot | `sudo systemctl restart rsi-bot` |
| Bot status | `sudo systemctl status rsi-bot` |
| Live logs | `journalctl -u rsi-bot -f` |
| Deploy logs | `tail -f /var/log/rsi-bot-deploy.log` |
| Health check | `cat /tmp/rsi_bot_status.json` |
| Current version | `cat ~/rsi_bot/VERSION` |
| Force deploy | `~/rsi_bot/deploy/force_deploy.sh` |
| Cancel deploy | `touch /tmp/rsi_bot_cancel_deploy` |
| Enable auto-deploy | `sudo systemctl enable --now check-deploy.timer` |
| Disable auto-deploy | `sudo systemctl stop check-deploy.timer` |
