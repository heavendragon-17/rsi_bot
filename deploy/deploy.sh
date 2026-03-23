#!/bin/bash
set -euo pipefail

# Usage: deploy.sh <tag>
# Called by check_deploy.sh or force_deploy.sh.
# Assumes production branch is already checked out at the right commit.

TAG="${1:?Usage: deploy.sh <tag>}"
BOT_DIR="/home/user/rsi_bot"
VENV_DIR="$BOT_DIR/venv"
STATUS_FILE="/tmp/rsi_bot_status.json"
DEPLOY_STATE="/tmp/rsi_bot_deploy_state.json"
VERSION_FILE="$BOT_DIR/VERSION"
LOG_FILE="/var/log/rsi-bot-deploy.log"

log() { echo "[$(date -Iseconds)] $*" | tee -a "$LOG_FILE"; }

update_deploy_state() {
    local state="$1" error="${2:-}"
    DS_STATE="$state" DS_ERROR="$error" DS_PATH="$DEPLOY_STATE" \
    python3 -c "
import json, os
from datetime import datetime, timezone
now = datetime.now(timezone.utc).isoformat()
path = os.environ['DS_PATH']
state = os.environ['DS_STATE']
error = os.environ['DS_ERROR']
try:
    with open(path) as f:
        d = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    d = {}
d['state'] = state
d['updated_at'] = now
if state in ('completed', 'failed'):
    d['last_deploy'] = now
    d['last_result'] = state
    d['last_error'] = error
    d['waiting_since'] = ''
with open(path, 'w') as f:
    json.dump(d, f, indent=2)
" 2>/dev/null || true
}

SHA=$(git -C "$BOT_DIR" rev-parse --short HEAD)
log "=== Starting deploy: $TAG ($SHA) ==="

cd "$BOT_DIR"

# 1. Install dependencies
source "$VENV_DIR/bin/activate"
pip install -r requirements.txt --quiet 2>&1 | tee -a "$LOG_FILE"

# 2. Smoke test: import check + config validation
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
    update_deploy_state "failed" "smoke_test_failed"
    exit 2
}
log "$SMOKE_OUTPUT"

# 3. Write version file
echo "{\"tag\": \"$TAG\", \"sha\": \"$SHA\", \"deployed_at\": \"$(date -Iseconds)\"}" > "$VERSION_FILE"

# 4. Restart bot
log "Restarting rsi-bot service..."
sudo systemctl restart rsi-bot

# 5. Health check: wait for status file to refresh with new version
log "Waiting for health check..."
sleep 5
for i in $(seq 1 12); do
    if [[ -f "$STATUS_FILE" ]]; then
        STATUS=$(HC_PATH="$STATUS_FILE" HC_TAG="$TAG" python3 -c "
import json, os
with open(os.environ['HC_PATH']) as f:
    d = json.load(f)
if d.get('status') == 'running' and d.get('version') == os.environ['HC_TAG']:
    print('HEALTHY')
else:
    print(f'NOT_READY: status={d.get(\"status\")}, version={d.get(\"version\")}')
" 2>&1) || STATUS="READ_ERROR"
        if [[ "$STATUS" == "HEALTHY" ]]; then
            log "Health check PASSED: bot running $TAG"
            update_deploy_state "completed"
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
update_deploy_state "failed" "health_check_timeout"
exit 3
