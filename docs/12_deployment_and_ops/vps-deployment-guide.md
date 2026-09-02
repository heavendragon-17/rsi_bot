# VPS Deployment Guide

Step-by-step guide to deploy the RSI Bot on a fresh VPS (Ubuntu/Debian).

---

## 1. VPS Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 1 vCPU | 2 vCPU |
| RAM | 1 GB | 2 GB |
| Disk | 10 GB | 20 GB (for backtest data) |
| OS | Linux with systemd | A supported Ubuntu/Debian release |
| Python | 3.13 | 3.13 |

---

## 2. Can I Install in `/opt`?

**Yes.** Production defaults to `/opt/rsi_bot`; all deployment paths are
centralized in `deploy/deploy_env.sh`. Complete the user and dependency setup
below, clone as `botuser`, and change this one file if a different path is
required:

```bash
BOT_DIR="/opt/rsi_bot"
SERVICE_USER="botuser"
```

That's it — all scripts and systemd services read from `deploy_env.sh` automatically.

---

## 3. Initial Server Setup

### 3.1 Create a dedicated user (if not using root)

```bash
sudo adduser --disabled-password --gecos "" botuser
```

### 3.2 Install system dependencies

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git python3-venv python3-pip
python3 --version  # must report Python 3.13.x
```

Distribution packages differ. If `python3` is older than 3.13, install Python
3.13 from a trusted distribution source before creating the virtual
environment. Do not replace the operating system's own `/usr/bin/python3`.

### 3.3 (Optional) Firewall — lock down inbound ports

The bot only needs **outbound** HTTPS. No inbound ports required for the trading bot
itself. Only open SSH for your management access.

```bash
sudo ufw allow OpenSSH
sudo ufw enable
```

Do not expose the backtest API directly. It has administrative endpoints and
does not implement user authentication. Use an SSH tunnel or an authenticated
TLS reverse proxy if remote UI access is required.

---

## 4. Clone and Configure

### 4.1 Clone the repository

```bash
sudo install -d -o botuser -g botuser /opt/rsi_bot
sudo -u botuser git clone https://github.com/heavendragon-17/rsi_bot.git /opt/rsi_bot
cd /opt/rsi_bot
```

### 4.2 Create Python virtual environment

```bash
sudo -u botuser python3.13 -m venv venv
sudo -u botuser venv/bin/python -m pip install --upgrade pip
sudo -u botuser venv/bin/python -m pip install -r requirements.txt
```

### 4.3 Configure environment variables

```bash
sudo -u botuser cp .env.example .env
sudo -u botuser chmod 600 .env
sudo -u botuser nano .env
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
sudo -u botuser nano config.yaml
```

Key settings to adjust for production:

```yaml
bot:
  mode: "live"      # or "paper" for testnet first
  debug: false      # disable verbose logging in production

risk:
  max_position_size_pct: 0.20    # start conservative
  risk_per_trade_pct: 0.01       # 1% risk per trade
    leverage: 5                     # don't max out leverage
```

`bot.active` is currently a compatibility field, not a stop switch. Use
`systemctl stop rsi-bot` to stop execution; see the
[configuration reference](../03_setup_and_installation/configuration.md).

### 4.5 Smoke test

```bash
sudo -u botuser venv/bin/python -c "
from app.core import interfaces, config, constants, actions
from app.data import indicators
cfg = config.AppConfig.from_yaml('config.yaml')
print(f'Config loaded: mode={cfg.exchange.mode}, symbols={cfg.symbols}')
print('Smoke test PASSED')
"
```

---

## 5. Set Up systemd Services

### 5.1 Install services (one command)

The install script reads `deploy/deploy_env.sh`, validates ownership and the
virtual environment, generates the systemd units, installs a narrow sudoers
rule for this service only, creates the protected deploy log, and enables the
bot service:

```bash
sudo deploy/install.sh
sudo systemctl start rsi-bot
```

### 5.2 Verify it's running

```bash
sudo systemctl status rsi-bot
journalctl -u rsi-bot -f   # follow live logs
```

### 5.3 (Optional) Enable auto-deploy timer

If you want automatic deployments when you push tagged versions:

```bash
sudo systemctl enable --now check-deploy.timer
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

Use the guarded deploy script from the configured production checkout:

```bash
cd /opt/rsi_bot
deploy/force_deploy.sh         # deploy the promoted production commit
deploy/force_deploy.sh v1.2.5  # assert production is tagged v1.2.5, then deploy
```

The optional tag does not select an arbitrary checkout. Promote a rollback tag
through the GitHub Deploy workflow first, then run the force command if the VPS
needs immediate recovery. The command refuses an untagged production commit.

---

## 7. Running the Backtest UI (Optional)

The UI bundle is generated from the frontend source and is ignored by Git. To
serve it from FastAPI on a VPS, build it during deployment on a machine with
Node.js, then run the application without Node.js at runtime. Bind it to
loopback and reach it through an SSH tunnel:

```bash
cd /opt/rsi_bot/ui
npm ci
npm run build
cd /opt/rsi_bot
```

```bash
source venv/bin/activate
API_HOST=127.0.0.1 API_PORT=8100 python -m app.api.main
```

From your workstation:

```bash
ssh -L 8100:127.0.0.1:8100 botuser@your-vps
```

Open `http://localhost:8100`. If a reverse proxy is required, add TLS and
authentication before allowing network access.

---

## 8. Security Checklist

- [ ] API key: Futures only, no withdrawals, IP-whitelisted to VPS IP
- [ ] `.env` file permissions: `chmod 600 .env`
- [ ] Firewall: Only SSH open inbound; access the UI through a tunnel or authenticated proxy
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
    ├── Validate the exact tag commit with all CI jobs
    ├── Promote with a force-with-lease guard to production
    │
    ▼
VPS (check-deploy.timer — runs every 60s)
    │
    ├── git fetch origin production
    ├── Compare deployed SHA vs remote SHA
    ├── Fail closed if /tmp/rsi_bot_status.json is stale, missing, or invalid
    ├── Check for open positions
    ├── If positions clear → deploy.sh
    │   ├── pip install -r requirements.txt
    │   ├── Smoke test
    │   ├── Stage VERSION atomically
    │   ├── systemctl restart rsi-bot
    │   ├── Verify tag, commit, and process start time
    │   └── Roll back source, dependencies, VERSION, and service on failure
    └── If positions open → wait and retry next minute
```

---

## 10. Troubleshooting

| Problem | Fix |
|---------|-----|
| Bot won't start | `journalctl -u rsi-bot -n 50` — check for import/config errors |
| "Config validation failed" | Run the smoke test manually (section 4.5) |
| No Telegram notifications | Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env` |
| Deploy stuck in "waiting" with `Positions: N > 0` but `/status` shows 0 | Pre-fix this was a stale `PortfolioManager.positions` dict (sync was a no-op). Fixed by `sync_from_exchange()` reconciling via `fetch_positions()` and a `position_closed` callback in sim. If you see this on an old build, force-deploy via `touch /tmp/rsi_bot_force_deploy`. |
| Deploy stuck in "waiting" with real open positions | Wait for them to close, or `touch /tmp/rsi_bot_force_deploy` to override |
| Cancel pending deploy | `touch /tmp/rsi_bot_cancel_deploy` |
| Automatic deploy reports `status_file_unavailable` | Restore bot health/status output, or deliberately use `/force_deploy`; automatic deployment fails closed |
| Candidate is marked failed and no longer retries | Fix or promote a newer tag; use `/force_deploy` only after reviewing the failure. This prevents one-minute restart loops |
| Rollback reports failure | Inspect `journalctl -u rsi-bot` and `/var/log/rsi-bot-deploy.log`; keep production disabled until the prior release is healthy |
| Deploy log repeats `Positions clear. Starting deploy` every minute but the service never restarts | The automatic checker hit an embedded Python runtime error after resetting the production checkout and before invoking `deploy.sh` | Inspect `sudo journalctl -u check-deploy.service -n 50` for the traceback and run `tests/test_deploy_scripts.py`. After promoting a fixed tag, allow the timer to self-heal; if it does not, use the guarded `deploy/force_deploy.sh <tag>` command after confirming the tag is on `production` |
| Status file stale | Bot may have crashed — `systemctl restart rsi-bot` |
| Sim balance reset after deploy | Snapshot at `/tmp/rsi_bot_sim_state.json` should restore it. If missing, check that `StatusWriter` is running and that the configured `sim.initial_balance` matches the snapshot's anchor (a config change discards the snapshot). |
| Permission denied on `/opt` | `sudo chown -R your-user:your-user /opt/rsi_bot` |

### State files written at runtime

| Path | Writer | Purpose |
|------|--------|---------|
| `/tmp/rsi_bot_status.json` | `StatusWriter` (every 30s) | Bot health + position count read by the deploy gate |
| `/tmp/rsi_bot_deploy_state.json` | `check_deploy.sh` / `deploy.sh` | Current deploy state (`idle` / `waiting` / `deploying` / `completed` / `failed`) |
| `/tmp/rsi_bot_sim_state.json` | `StatusWriter` (sim mode only, every 30s) | Persists `balance`, `initial_balance` (session anchor), and cumulative fees across restarts so a deploy doesn't wipe the user's session P&L. Open positions are NOT persisted — they roll over via `cleanup_on_startup` against the live exchange. Discarded automatically if `sim.initial_balance` is changed in config. |
