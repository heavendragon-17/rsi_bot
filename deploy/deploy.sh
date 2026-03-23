#!/bin/bash
set -euo pipefail

# Usage: deploy.sh <tag> <sha>
# Deploys the given tag to production by checking out the production branch,
# running a smoke test, restarting the bot, and verifying health.

TAG="${1:?Usage: deploy.sh <tag> <sha>}"
SHA="${2:?Usage: deploy.sh <tag> <sha>}"
BOT_DIR="/home/user/rsi_bot"
VENV_DIR="$BOT_DIR/venv"
STATUS_FILE="/tmp/rsi_bot_status.json"
VERSION_FILE="$BOT_DIR/VERSION"
LOG_FILE="/var/log/rsi-bot-deploy.log"

log() { echo "[$(date -Iseconds)] $*" | tee -a "$LOG_FILE"; }

log "=== Starting deploy: $TAG ($SHA) ==="

# 1. Fetch and checkout production
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

# 3. Install dependencies
source "$VENV_DIR/bin/activate"
pip install -r requirements.txt --quiet 2>&1 | tee -a "$LOG_FILE"

# 4. Smoke test: import check + config validation
log "Running smoke test..."
SMOKE_OUTPUT=$(python -c "
from app.core import interfaces, config, constants, actions
from app.data import indicators
cfg = config.AppConfig.from_yaml('config.yaml')
print(f'Config loaded: mode={cfg.bot.mode}, symbols={cfg.symbols}')
print('Smoke test PASSED')
" 2>&1) || {
    log "ERROR: Smoke test FAILED"
    log "$SMOKE_OUTPUT"
    exit 2
}
log "$SMOKE_OUTPUT"

# 5. Write version file
echo "{\"tag\": \"$TAG\", \"sha\": \"$SHA\", \"deployed_at\": \"$(date -Iseconds)\"}" > "$VERSION_FILE"

# 6. Restart bot
log "Restarting rsi-bot service..."
sudo systemctl restart rsi-bot

# 7. Health check: wait for status file to refresh with new version
log "Waiting for health check..."
sleep 5
for i in $(seq 1 12); do
    if [[ -f "$STATUS_FILE" ]]; then
        STATUS=$(python3 -c "
import json
with open('$STATUS_FILE') as f:
    d = json.load(f)
if d.get('status') == 'running' and d.get('version') == '$TAG':
    print('HEALTHY')
else:
    print(f'NOT_READY: status={d.get(\"status\")}, version={d.get(\"version\")}')
" 2>&1) || STATUS="READ_ERROR"
        if [[ "$STATUS" == "HEALTHY" ]]; then
            log "Health check PASSED: bot running $TAG"
            exit 0
        fi
    else
        STATUS="NO_STATUS_FILE"
    fi
    log "Health check attempt $i/12: $STATUS"
    sleep 5
done

log "ERROR: Health check FAILED after 60s. Stopping bot."
sudo systemctl stop rsi-bot
exit 3
