#!/bin/bash
set -euo pipefail

# Usage: force_deploy.sh [tag]
# Manual SSH fallback deploy. Skips position check.
# If no tag given, pulls latest from production branch.

BOT_DIR="/home/user/rsi_bot"
VENV_DIR="$BOT_DIR/venv"
VERSION_FILE="$BOT_DIR/VERSION"
LOG_FILE="/var/log/rsi-bot-deploy.log"

log() { echo "[$(date -Iseconds)] $*" | tee -a "$LOG_FILE"; }

TAG="${1:-latest}"

cd "$BOT_DIR"
git fetch origin production
git checkout production
git reset --hard "origin/production"

SHA=$(git rev-parse --short HEAD)

if [[ "$TAG" == "latest" ]]; then
    # Derive tag from the latest git tag on this commit, or use SHA
    TAG=$(git describe --tags --exact-match 2>/dev/null || echo "manual-$SHA")
fi

log "=== Force deploy: $TAG ($SHA) ==="

source "$VENV_DIR/bin/activate"
pip install -r requirements.txt --quiet 2>&1 | tee -a "$LOG_FILE"

# Smoke test
log "Running smoke test..."
python -c "
from app.core import interfaces, config, constants, actions
from app.data import indicators
cfg = config.AppConfig.from_yaml('config.yaml')
print(f'Config loaded: mode={cfg.bot.mode}, symbols={cfg.symbols}')
print('Smoke test PASSED')
" 2>&1 | tee -a "$LOG_FILE" || {
    log "ERROR: Smoke test FAILED. Aborting."
    exit 2
}

# Write version file
echo "{\"tag\": \"$TAG\", \"sha\": \"$SHA\", \"deployed_at\": \"$(date -Iseconds)\"}" > "$VERSION_FILE"

# Restart bot
log "Restarting rsi-bot service..."
sudo systemctl restart rsi-bot

log "Force deploy complete. Check bot health manually: journalctl -u rsi-bot -f"
