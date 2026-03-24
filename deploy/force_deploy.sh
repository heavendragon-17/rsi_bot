#!/bin/bash
set -euo pipefail

# Usage: force_deploy.sh [tag]
# Manual SSH fallback deploy. Skips position check.
# If no tag given, pulls latest from production branch.

BOT_DIR="/opt/rsi_bot"
LOG_FILE="/var/log/rsi-bot-deploy.log"

log() { echo "[$(date -Iseconds)] $*" | tee -a "$LOG_FILE"; }

cd "$BOT_DIR"
git fetch origin production
git checkout production
git reset --hard "origin/production"

TAG="${1:-}"
if [[ -z "$TAG" ]]; then
    TAG=$(git tag --points-at HEAD | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | tail -1)
    TAG="${TAG:-manual-$(git rev-parse --short HEAD)}"
fi

log "=== Force deploy (SSH): $TAG ==="
exec "$BOT_DIR/deploy/deploy.sh" "$TAG"
