# SPEC: Auto-Deploy to VPS

**Status**: Approved
**Date**: 2026-03-23
**Scope**: CI/CD pipeline, VPS deployment automation, bot health monitoring

---

## 1. Overview

Automate deployment of the RSI trading bot to a VPS after passing all CI checks. Uses a two-branch strategy with Telegram as the deployment trigger channel — zero inbound ports on the VPS.

### Goals

- Tagged releases on dev branch promote to `production` branch and auto-deploy to VPS
- Maintenance window approach: only deploy when no positions are open
- Force-deploy override for urgent updates
- Full observability: Telegram alerts, version tracking, smoke tests, GitHub deployment status
- Zero inbound network access to VPS (maximum security)

### Non-Goals

- Multi-VPS deployment (single VPS only)
- Blue-green or canary deployment
- Auto-rollback (manual rollback via git revert)
- Docker-based deployment (bare metal + systemd)

---

## 2. Branch Strategy

```
mua-tren-the-nang (dev)  ──tag v1.x.x──►  production (VPS)
        │                                        │
   All development                    Always reflects what's
   CI runs on push/PR                 running on the VPS
```

| Branch | Purpose | CI Trigger | Deploy |
|--------|---------|------------|--------|
| `mua-tren-the-nang` | Active development | Push + PR | Never |
| `production` | VPS mirror | Tag push (via merge) | Always |

### Tag Format

**Semantic versioning**: `v<major>.<minor>.<patch>`

- `v1.0.0` — initial production release
- `v1.1.0` — new feature (e.g., new strategy, new symbol)
- `v1.0.1` — bug fix, config tweak
- `v2.0.0` — breaking change (e.g., architecture refactor)

### Release Flow

1. Developer works on `mua-tren-the-nang`
2. CI passes on push/PR (existing 10-job pipeline)
3. Developer creates a tag: `git tag v1.2.3 && git push origin v1.2.3`
4. GitHub Actions **tag workflow** triggers:
   a. Runs full CI suite on the tagged commit
   b. If CI passes → fast-forward merges tagged commit to `production`
   c. Sends Telegram deploy trigger message to deploy bot
   d. Updates GitHub deployment status
5. VPS deploy listener receives Telegram message → begins deployment

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    GitHub Actions                        │
│                                                         │
│  on tag push (v*)                                       │
│    ├─ Run full CI (10 jobs)                             │
│    ├─ Merge to production branch                        │
│    ├─ Send Telegram message: "DEPLOY v1.2.3 <sha>"     │
│    └─ Set GitHub deployment status: pending             │
└─────────────────┬───────────────────────────────────────┘
                  │ Telegram Bot API (outbound HTTPS)
                  ▼
┌─────────────────────────────────────────────────────────┐
│                VPS (bare metal, systemd)                 │
│                                                         │
│  ┌─────────────────────────────────────────────┐        │
│  │  deploy-listener.service (systemd)          │        │
│  │  Python Telegram bot (polling)              │        │
│  │                                             │        │
│  │  Receives: DEPLOY messages, user commands   │        │
│  │  Reads:    /tmp/rsi_bot_status.json         │        │
│  │  Executes: deploy.sh                        │        │
│  │  Sends:    Telegram alerts                  │        │
│  └──────────────┬──────────────────────────────┘        │
│                 │                                        │
│  ┌──────────────▼──────────────────────────────┐        │
│  │  deploy.sh (bash script)                    │        │
│  │                                             │        │
│  │  1. git fetch + checkout production         │        │
│  │  2. pip install -r requirements.txt         │        │
│  │  3. Run smoke test                          │        │
│  │  4. systemctl restart rsi-bot               │        │
│  │  5. Verify health (status file refresh)     │        │
│  │  6. Write version file                      │        │
│  └─────────────────────────────────────────────┘        │
│                                                         │
│  ┌─────────────────────────────────────────────┐        │
│  │  rsi-bot.service (systemd)                  │        │
│  │  python main.py                             │        │
│  │                                             │        │
│  │  Writes: /tmp/rsi_bot_status.json (30s)     │        │
│  │  Contains: positions, version, uptime,      │        │
│  │            last_candle_ts                    │        │
│  └─────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────┘
```

### Key Design Decisions

- **Telegram as deploy channel**: GitHub Actions sends a message, VPS polls Telegram. No inbound ports, no webhook endpoint, no Cloudflare Tunnel.
- **Separate deploy Telegram bot**: Avoids polling conflict with the trading bot's Telegram integration. Two different bot tokens, same chat ID.
- **Status file on disk**: Bot writes `/tmp/rsi_bot_status.json` every 30s. Deploy listener reads it for position checks and health verification. No HTTP endpoint needed on the bot.
- **Maintenance window by default**: Deploy waits indefinitely for positions to close. `/force_deploy` overrides this.
- **Latest tag wins**: If a newer tag arrives while waiting, cancel the old deploy and switch to the new one.

---

## 4. Components to Build

### 4.1 GitHub Actions: Tag Deploy Workflow

**File**: `.github/workflows/deploy.yml`

**Trigger**: Push of tags matching `v*`

**Jobs**:

1. **ci** — Reuse existing CI jobs (call the existing ci.yml as a reusable workflow or duplicate the jobs)
2. **promote** — After CI passes:
   - Checkout the tagged commit
   - Fast-forward merge to `production` branch
   - Push `production` branch
3. **notify** — After promote:
   - Send Telegram message via direct curl to Bot API:
     ```
     DEPLOY:<tag>:<commit_sha>:<short_message>
     ```
   - Example: `DEPLOY:v1.2.3:abc1234:Fix RSI threshold bug`
   - Update GitHub deployment status to "pending"
4. **status** — Runs after a delay or is triggered by the VPS:
   - Updates GitHub deployment status based on result

**Required GitHub Secrets**:
- `DEPLOY_TELEGRAM_BOT_TOKEN` — Deploy bot token
- `DEPLOY_TELEGRAM_CHAT_ID` — Chat ID for deploy notifications
- `GITHUB_TOKEN` — Already available (for pushing production branch)

### 4.2 Bot Status File Writer

**Location**: `app/core/status_writer.py` (or integrate into existing bot lifecycle)

**Behavior**:
- Runs in a background thread inside the bot process
- Writes to `/tmp/rsi_bot_status.json` every 30 seconds
- Atomic write (write to temp file, then rename) to prevent partial reads

**Schema**:
```json
{
  "version": "v1.2.3",
  "commit_sha": "abc1234def5678",
  "pid": 12345,
  "started_at": "2026-03-23T10:00:00Z",
  "updated_at": "2026-03-23T14:30:00Z",
  "uptime_seconds": 16200,
  "open_positions": [
    {
      "symbol": "BTC/USDT",
      "side": "BUY",
      "size": 0.001,
      "entry_price": 67500.0,
      "unrealized_pnl": 12.50
    }
  ],
  "position_count": 1,
  "last_candle_ts": "2026-03-23T14:15:00Z",
  "status": "running"
}
```

**Version source**: Read from `VERSION` file at repo root (written by deploy script), fall back to `"dev"`.

### 4.3 Deploy Listener (Telegram Bot on VPS)

**Location**: `deploy/deploy_listener.py`

**Runtime**: Python script, runs as systemd service (`deploy-listener.service`)

**Dependencies**: `python-telegram-bot` (or raw `requests` polling) — minimal, no heavy frameworks

**Behavior**:

1. Polls Telegram for updates (long polling, 30s timeout)
2. Handles two types of messages:
   - **Deploy triggers** from GitHub Actions (message format: `DEPLOY:<tag>:<sha>:<message>`)
   - **User commands**: `/force_deploy`, `/bot_version`, `/deploy_status`, `/cancel_deploy`

**Deploy trigger flow**:

```
Receive DEPLOY message
  ├─ Parse tag, sha, message
  ├─ If pending deploy exists → cancel it (latest tag wins)
  ├─ Send Telegram: "🔄 Deploy v1.2.3 received. Checking positions..."
  ├─ Read /tmp/rsi_bot_status.json
  │   ├─ position_count == 0 → proceed to deploy
  │   └─ position_count > 0 → enter wait loop
  │       ├─ Send Telegram: "⏳ Waiting for N positions to close..."
  │       ├─ Check status file every 30s
  │       ├─ If newer DEPLOY message arrives → cancel this, start new
  │       └─ When positions == 0 → proceed to deploy
  ├─ Execute deploy.sh <tag> <sha>
  │   ├─ Success → Send Telegram: "✅ v1.2.3 deployed successfully"
  │   └─ Failure → Send Telegram: "❌ Deploy v1.2.3 FAILED: <error>"
  │                Stop bot, wait for manual intervention
  └─ Report result back (for GitHub deployment status update)
```

**Telegram Commands**:

| Command | Behavior |
|---------|----------|
| `/force_deploy` | Deploy immediately, skip position check. Uses the latest pending tag, or the current production HEAD if no pending. |
| `/bot_version` | Reply with: deployed version, commit SHA, uptime, position count, last candle age. Reads from status file + VERSION file. |
| `/deploy_status` | Reply with: idle / waiting for positions (N open, waiting since HH:MM) / deploying / last deploy time and result. |
| `/cancel_deploy` | Cancel a pending deploy that's waiting for positions. |

**Security**:
- Only process messages from the configured `DEPLOY_TELEGRAM_CHAT_ID`
- Only accept DEPLOY triggers that match expected format
- Validate tag format (must match `v\d+\.\d+\.\d+`)

### 4.4 Deploy Script

**File**: `deploy/deploy.sh`

**Arguments**: `deploy.sh <tag> <sha>`

**Steps**:

```bash
#!/bin/bash
set -euo pipefail

TAG=$1
SHA=$2
BOT_DIR="/opt/rsi_bot"
VENV_DIR="$BOT_DIR/venv"
STATUS_FILE="/tmp/rsi_bot_status.json"
VERSION_FILE="$BOT_DIR/VERSION"
LOG_FILE="/var/log/rsi-bot-deploy.log"

log() { echo "[$(date -Iseconds)] $*" | tee -a "$LOG_FILE"; }

log "=== Starting deploy: $TAG ($SHA) ==="

# 1. Fetch and checkout
cd "$BOT_DIR"
git fetch origin production
git checkout production
git reset --hard "origin/production"

# 2. Verify commit matches expected SHA
ACTUAL_SHA=$(git rev-parse --short HEAD)
if [[ "$ACTUAL_SHA" != "$SHA"* ]]; then
    log "ERROR: SHA mismatch. Expected $SHA, got $ACTUAL_SHA"
    exit 1
fi

# 3. Install dependencies (only if requirements.txt changed)
source "$VENV_DIR/bin/activate"
pip install -r requirements.txt --quiet 2>&1 | tee -a "$LOG_FILE"

# 4. Smoke test: import check + config validation
log "Running smoke test..."
python -c "
from app.core import interfaces, config, constants, actions
from app.trading.strategy import rsi_no_retest
from app.data import indicators
cfg = config.AppConfig.from_yaml('config.yaml')
print(f'Config loaded: mode={cfg.bot.mode}, symbols={cfg.symbols}')
print('Smoke test PASSED')
" 2>&1 | tee -a "$LOG_FILE"

if [[ $? -ne 0 ]]; then
    log "ERROR: Smoke test FAILED"
    exit 2
fi

# 5. Write version file
echo "{\"tag\": \"$TAG\", \"sha\": \"$SHA\", \"deployed_at\": \"$(date -Iseconds)\"}" > "$VERSION_FILE"

# 6. Restart bot
log "Restarting rsi-bot service..."
sudo systemctl restart rsi-bot

# 7. Health check: wait for status file to refresh with new PID
log "Waiting for health check..."
sleep 5
for i in {1..12}; do  # 12 * 5s = 60s max
    if [[ -f "$STATUS_FILE" ]]; then
        STATUS=$(python3 -c "
import json, sys
with open('$STATUS_FILE') as f:
    d = json.load(f)
if d.get('status') == 'running' and d.get('version') == '$TAG':
    print('HEALTHY')
else:
    print(f'NOT_READY: status={d.get(\"status\")}, version={d.get(\"version\")}')
        ")
        if [[ "$STATUS" == "HEALTHY" ]]; then
            log "Health check PASSED: bot running $TAG"
            exit 0
        fi
    fi
    log "Health check attempt $i/12: $STATUS"
    sleep 5
done

log "ERROR: Health check FAILED after 60s. Stopping bot."
sudo systemctl stop rsi-bot
exit 3
```

### 4.5 Force Deploy Script (Manual SSH Backup)

**File**: `deploy/force_deploy.sh`

**Purpose**: Manual SSH escape hatch when Telegram-based deploy is unavailable.

```bash
#!/bin/bash
# Usage: ./force_deploy.sh [tag]
# If no tag given, pulls latest from production branch.
TAG=${1:-"latest"}
# ... same logic as deploy.sh but skips position check
```

### 4.6 Systemd Service Files

**File**: `deploy/systemd/rsi-bot.service`

```ini
[Unit]
Description=RSI Trading Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=user
WorkingDirectory=/opt/rsi_bot
Environment=PATH=/opt/rsi_bot/venv/bin:/usr/bin:/bin
ExecStart=/opt/rsi_bot/venv/bin/python main.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**File**: `deploy/systemd/deploy-listener.service`

```ini
[Unit]
Description=RSI Bot Deploy Listener (Telegram)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=user
WorkingDirectory=/opt/rsi_bot/deploy
Environment=PATH=/opt/rsi_bot/venv/bin:/usr/bin:/bin
EnvironmentFile=/opt/rsi_bot/deploy/.env.deploy
ExecStart=/opt/rsi_bot/venv/bin/python deploy_listener.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### 4.7 Version Tracking

**File at repo root**: `VERSION`

Written by deploy script on each deploy:
```json
{"tag": "v1.2.3", "sha": "abc1234", "deployed_at": "2026-03-23T14:30:00+00:00"}
```

- Read by the bot's status writer to populate `version` field
- Read by deploy listener for `/bot_version` command
- `.gitignore`'d (not committed, VPS-only)

### 4.8 GitHub Deployment Status

The deploy workflow uses GitHub's Deployments API to track deployment state:

- `pending` — after CI passes, deploy message sent
- `success` — after VPS confirms successful deploy (via Telegram callback to a second GH Actions workflow, or simply set on the workflow itself)
- `failure` — if deploy fails

For simplicity in v1: set `success` optimistically after the Telegram message is sent. The VPS Telegram alerts provide the real status. GitHub Deployments API integration can be enhanced later.

---

## 5. Configuration & Secrets

### GitHub Secrets (repo settings)

| Secret | Purpose |
|--------|---------|
| `DEPLOY_TELEGRAM_BOT_TOKEN` | Telegram bot token for deploy bot |
| `DEPLOY_TELEGRAM_CHAT_ID` | Chat ID for deploy notifications |

### VPS Deploy Listener Config

**File**: `deploy/.env.deploy`

```bash
DEPLOY_TELEGRAM_BOT_TOKEN=<deploy bot token>
DEPLOY_TELEGRAM_CHAT_ID=<chat id>
BOT_DIR=/opt/rsi_bot
STATUS_FILE=/tmp/rsi_bot_status.json
VERSION_FILE=/opt/rsi_bot/VERSION
```

### VPS Files NOT in Git

- `config.yaml` — production trading config (risk params, symbols, mode=live)
- `.env` — Binance API keys, trading Telegram bot token
- `deploy/.env.deploy` — deploy bot credentials
- `VERSION` — written by deploy script

---

## 6. Failure Handling

### Deploy Failure Scenarios

| Scenario | Detection | Response |
|----------|-----------|----------|
| CI fails on tag | GitHub Actions job fails | No deploy triggered. Developer fixes and re-tags. |
| Git pull fails on VPS | `deploy.sh` exits non-zero | Telegram alert: "Deploy FAILED: git error". Bot keeps running old version. |
| Smoke test fails | `deploy.sh` exits code 2 | Telegram alert: "Deploy FAILED: smoke test". Bot keeps running old version (not restarted yet). |
| Bot fails to start | Health check fails after 60s | Telegram alert: "Deploy FAILED: health check". **Bot is stopped.** Manual intervention required. |
| Bot starts but crashes later | Status file goes stale (>5 min) | Not auto-detected by deploy listener. Systemd `Restart=on-failure` handles restart. Telegram silence alerts the operator. |
| Position check stale | Status file older than 5 min | Deploy listener treats as "bot may be down". Alerts operator, does NOT proceed with deploy. |

### Rollback Procedure

1. On `mua-tren-the-nang`: `git revert <bad-commit>`
2. Tag the revert: `git tag v1.2.4`
3. Push: `git push origin v1.2.4`
4. Normal deploy flow triggers with the fix

For emergencies: SSH into VPS, run `deploy/force_deploy.sh v1.2.2` to roll back to a known-good tag.

---

## 7. File Inventory

### New Files

```
.github/workflows/deploy.yml          — Tag-triggered deploy workflow
deploy/
  deploy_listener.py                   — Telegram bot for deploy orchestration
  deploy.sh                            — VPS deploy script (git pull, smoke, restart)
  force_deploy.sh                      — Manual SSH deploy script
  requirements.txt                     — Deploy listener dependencies (minimal)
  .env.deploy.example                  — Template for deploy listener config
  systemd/
    rsi-bot.service                    — Bot systemd unit
    deploy-listener.service            — Deploy listener systemd unit
app/core/status_writer.py             — Background thread writing status JSON
```

### Modified Files

```
.github/workflows/ci.yml              — Make reusable (workflow_call) for deploy.yml
.gitignore                             — Add VERSION
main.py                                — Start StatusWriter thread
app/core/constants.py                  — Add STATUS_FILE_PATH, STATUS_WRITE_INTERVAL
```

---

## 8. Security Considerations

- **Zero inbound ports on VPS**: All communication is outbound (Telegram polling, GitHub git pull)
- **Separate Telegram bot**: Deploy bot token is isolated from trading bot token
- **Chat ID validation**: Deploy listener only processes messages from the configured chat
- **DEPLOY message format validation**: Rejects malformed trigger messages
- **SHA verification**: Deploy script verifies the checked-out commit matches the expected SHA
- **Sudoers**: Deploy user needs passwordless `sudo systemctl restart rsi-bot` and `sudo systemctl stop rsi-bot` only. Add to sudoers:
  ```
  user ALL=(ALL) NOPASSWD: /bin/systemctl restart rsi-bot, /bin/systemctl stop rsi-bot
  ```
- **Config isolation**: config.yaml and .env never leave the VPS, never in git
- **No secrets in logs**: deploy.sh must not echo tokens or keys

---

## 9. VPS Setup Checklist (One-Time)

1. Create deploy Telegram bot via @BotFather, save token
2. Create `deploy/.env.deploy` with bot token and chat ID
3. Install systemd services:
   ```bash
   sudo cp deploy/systemd/rsi-bot.service /etc/systemd/system/
   sudo cp deploy/systemd/deploy-listener.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable rsi-bot deploy-listener
   sudo systemctl start rsi-bot deploy-listener
   ```
4. Configure sudoers for passwordless systemctl
5. Ensure `production` branch is checked out on VPS
6. Create `config.yaml` and `.env` on VPS with production values
7. Test deploy flow: push a test tag, verify end-to-end

---

## 10. Implementation Order

1. **Status writer** (`app/core/status_writer.py`) + integration into `main.py`
2. **Deploy script** (`deploy/deploy.sh`) + smoke test
3. **Systemd service files** (`deploy/systemd/`)
4. **GitHub Actions deploy workflow** (`.github/workflows/deploy.yml`)
5. **Deploy listener** (`deploy/deploy_listener.py`) with Telegram commands
6. **Force deploy script** (`deploy/force_deploy.sh`)
7. **Update .gitignore, constants.py**
8. **End-to-end testing**

---

## 11. Open Questions / Future Enhancements

- **Dependency caching on VPS**: `pip install` could be slow. Consider caching wheels or using `pip install --upgrade` only when requirements.txt changes (checksum comparison).
- **Log aggregation**: Currently logs go to journald. Consider shipping to a centralized logging service for long-term retention.
- **Multiple VPS**: If scaling to multiple VPS instances in the future, consider a pull-based approach (each VPS polls independently) rather than push-based.
- **Database migrations**: If SQLite schema changes, the deploy script needs a migration step. Currently not needed (backtest DB only).
- **Frontend deployment**: The backtest UI (React) is not deployed to VPS in this spec. Add if needed later.
- **GitHub Deployments API v2**: Replace optimistic status with real VPS confirmation via a callback mechanism.
