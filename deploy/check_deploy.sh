#!/bin/bash
set -euo pipefail

# check_deploy.sh — Run by systemd timer every minute.
# Checks if production branch has a new tagged commit and deploys
# when no positions are open.
#
# State file: /tmp/rsi_bot_deploy_state.json
# Flag files: /tmp/rsi_bot_force_deploy, /tmp/rsi_bot_cancel_deploy

BOT_DIR="/home/user/rsi_bot"
STATUS_FILE="/tmp/rsi_bot_status.json"
DEPLOY_STATE="/tmp/rsi_bot_deploy_state.json"
FORCE_FLAG="/tmp/rsi_bot_force_deploy"
CANCEL_FLAG="/tmp/rsi_bot_cancel_deploy"
VERSION_FILE="$BOT_DIR/VERSION"
LOG_FILE="/var/log/rsi-bot-deploy.log"
STALE_THRESHOLD=300  # 5 minutes

log() { echo "[$(date -Iseconds)] $*" >> "$LOG_FILE"; }

write_state() {
    # Usage: write_state <state> <tag> <sha> [error]
    DS_STATE="$1" DS_TAG="$2" DS_SHA="$3" DS_ERROR="${4:-}" \
    DS_PATH="$DEPLOY_STATE" \
    python3 -c "
import json, os
from datetime import datetime, timezone
now = datetime.now(timezone.utc).isoformat()
path = os.environ['DS_PATH']
state = os.environ['DS_STATE']
try:
    with open(path) as f:
        existing = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    existing = {}
data = {
    'state': state,
    'tag': os.environ['DS_TAG'],
    'sha': os.environ['DS_SHA'],
    'updated_at': now,
    'waiting_since': existing.get('waiting_since', '') if state == 'waiting' else '',
    'last_deploy': existing.get('last_deploy', ''),
    'last_result': existing.get('last_result', ''),
    'last_error': os.environ['DS_ERROR'] or existing.get('last_error', ''),
}
if state == 'waiting' and not existing.get('waiting_since'):
    data['waiting_since'] = now
if state in ('completed', 'failed'):
    data['last_deploy'] = now
    data['last_result'] = state
with open(path, 'w') as f:
    json.dump(data, f, indent=2)
"
}

get_position_count() {
    STATUS_PATH="$STATUS_FILE" STALE_SEC="$STALE_THRESHOLD" \
    python3 -c "
import json, os
from datetime import datetime, timezone
try:
    with open(os.environ['STATUS_PATH']) as f:
        d = json.load(f)
    updated = datetime.fromisoformat(d['updated_at'])
    age = (datetime.now(timezone.utc) - updated).total_seconds()
    if age > int(os.environ['STALE_SEC']):
        print('STALE')
    else:
        print(d.get('position_count', 0))
except Exception:
    print('ERROR')
" 2>/dev/null
}

# ── Handle cancel flag ────────────────────────────────────────────
if [[ -f "$CANCEL_FLAG" ]]; then
    rm -f "$CANCEL_FLAG"
    write_state "idle" "" ""
    log "Deploy cancelled by user"
    exit 0
fi

# ── Handle force deploy flag ─────────────────────────────────────
if [[ -f "$FORCE_FLAG" ]]; then
    rm -f "$FORCE_FLAG"
    cd "$BOT_DIR"
    git fetch origin production 2>/dev/null
    git checkout production 2>/dev/null
    git reset --hard origin/production 2>/dev/null
    TAG=$(git tag --points-at HEAD | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | tail -1)
    TAG="${TAG:-force-$(git rev-parse --short HEAD)}"
    log "Force deploy triggered: $TAG"
    write_state "deploying" "$TAG" "$(git rev-parse --short HEAD)"
    exec "$BOT_DIR/deploy/deploy.sh" "$TAG"
fi

# ── Normal flow: check for new commits on production ─────────────
cd "$BOT_DIR"
git fetch origin production --tags 2>/dev/null || { log "git fetch failed"; exit 1; }

# Compare deployed SHA (from VERSION file) with remote production HEAD.
# This is safer than comparing git HEAD which depends on the current branch.
DEPLOYED_SHA=$(VF="$VERSION_FILE" python3 -c "
import json, os
try:
    with open(os.environ['VF']) as f:
        print(json.load(f).get('sha', ''))
except Exception:
    print('')
" 2>/dev/null) || DEPLOYED_SHA=""
REMOTE_SHA=$(git rev-parse --short origin/production 2>/dev/null || echo "none")

if [[ -n "$DEPLOYED_SHA" ]] && [[ "$REMOTE_SHA" == "$DEPLOYED_SHA"* ]]; then
    exit 0  # Already running this version
fi

# Verify production HEAD has a semver tag
REMOTE_TAGS=$(git tag --points-at origin/production 2>/dev/null | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' || true)
TAG=$(echo "$REMOTE_TAGS" | tail -1)

if [[ -z "$TAG" ]]; then
    log "New commit on production but no semver tag, skipping"
    exit 0
fi

SHORT_SHA=$(git rev-parse --short origin/production)
log "New deploy candidate: $TAG ($SHORT_SHA)"

# ── Position check ───────────────────────────────────────────────
POS_COUNT=$(get_position_count)

if [[ "$POS_COUNT" == "STALE" ]]; then
    log "WARNING: Status file stale (>5min). Bot may be down. Not deploying."
    write_state "waiting" "$TAG" "$SHORT_SHA" "status_file_stale"
    exit 0
fi

if [[ "$POS_COUNT" == "ERROR" ]]; then
    # Status file missing — bot might not be running. Proceed with deploy.
    log "WARNING: Status file missing. Proceeding with deploy."
fi

if [[ "$POS_COUNT" =~ ^[0-9]+$ ]] && [[ "$POS_COUNT" -gt 0 ]]; then
    log "Waiting: $POS_COUNT position(s) open. Deferring deploy of $TAG."
    write_state "waiting" "$TAG" "$SHORT_SHA"
    exit 0
fi

# ── Deploy ───────────────────────────────────────────────────────
log "Positions clear. Starting deploy of $TAG ($SHORT_SHA)"
git checkout production 2>/dev/null
git reset --hard origin/production 2>/dev/null
write_state "deploying" "$TAG" "$SHORT_SHA"
exec "$BOT_DIR/deploy/deploy.sh" "$TAG"
