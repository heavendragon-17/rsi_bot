#!/bin/bash
set -euo pipefail

# check_deploy.sh — Run by systemd timer every minute.
# Checks if production branch has a new tagged commit and deploys
# when no positions are open.

# ── Load shared variables ─────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/deploy_env.sh"

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
directory = os.path.dirname(path) or '.'
fd, temporary = tempfile.mkstemp(dir=directory, prefix='.deploy-state.', text=True)
try:
    with os.fdopen(fd, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
    os.replace(temporary, path)
except Exception:
    try:
        os.unlink(temporary)
    except OSError:
        pass
    raise
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
    if d.get('status') != 'running':
        raise ValueError('bot is not running')
    updated = datetime.fromisoformat(d['updated_at'])
    age = (datetime.now(timezone.utc) - updated).total_seconds()
    if age > int(os.environ['STALE_SEC']):
        print('STALE')
    else:
        count = d['position_count']
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError('invalid position_count')
        print(count)
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
    cd "$BOT_DIR"
    git fetch origin production --tags 2>/dev/null || {
        log "Force deploy fetch failed; keeping the force flag for retry"
        exit 1
    }
    git checkout production 2>/dev/null || {
        log "Force deploy checkout failed; keeping the force flag for retry"
        exit 1
    }
    git reset --hard origin/production 2>/dev/null || {
        log "Force deploy reset failed; keeping the force flag for retry"
        exit 1
    }
    TAG=$(git tag --points-at HEAD | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -1)
    if [[ -z "$TAG" ]]; then
        log "Force deploy refused: origin/production is not an exact SemVer tag"
        exit 1
    fi
    rm -f "$FORCE_FLAG"
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
REMOTE_SHA=$(git rev-parse origin/production 2>/dev/null || echo "none")

if [[ -n "$DEPLOYED_SHA" ]] && [[ "$REMOTE_SHA" == "$DEPLOYED_SHA"* ]]; then
    exit 0  # Already running this version
fi

# Verify production HEAD has a semver tag
REMOTE_TAGS=$(git tag --points-at origin/production 2>/dev/null | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' || true)
TAG=$(echo "$REMOTE_TAGS" | sort -V | tail -1)

if [[ -z "$TAG" ]]; then
    log "New commit on production but no semver tag, skipping"
    exit 0
fi

SHORT_SHA=$(git rev-parse --short origin/production)
log "New deploy candidate: $TAG ($SHORT_SHA)"

# A failed candidate remains blocked until production moves or the operator
# explicitly requests a force deploy. This prevents restart loops every minute.
FAILED_SHA=$(DS_PATH="$DEPLOY_STATE" python3 -c "
import json, os, tempfile
try:
    with open(os.environ['DS_PATH']) as f:
        data = json.load(f)
    if data.get('last_result') == 'failed':
        print(data.get('sha', ''))
except (FileNotFoundError, json.JSONDecodeError, OSError):
    pass
" 2>/dev/null) || FAILED_SHA=""

if [[ -n "$FAILED_SHA" ]] && [[ "$REMOTE_SHA" == "$FAILED_SHA"* ]]; then
    exit 0
fi

# ── Position check ───────────────────────────────────────────────
POS_COUNT=$(get_position_count)

if [[ "$POS_COUNT" == "STALE" ]]; then
    log "WARNING: Status file stale (>5min). Bot may be down. Not deploying."
    write_state "waiting" "$TAG" "$SHORT_SHA" "status_file_stale"
    exit 0
fi

if [[ "$POS_COUNT" == "ERROR" ]]; then
    log "WARNING: Status file missing or invalid. Refusing automatic deploy."
    write_state "waiting" "$TAG" "$SHORT_SHA" "status_file_unavailable"
    exit 0
fi

if [[ ! "$POS_COUNT" =~ ^[0-9]+$ ]]; then
    log "WARNING: Status file returned an invalid position count. Refusing automatic deploy."
    write_state "waiting" "$TAG" "$SHORT_SHA" "position_count_invalid"
    exit 0
fi

if [[ "$POS_COUNT" -gt 0 ]]; then
    log "Waiting: $POS_COUNT position(s) open. Deferring deploy of $TAG."
    write_state "waiting" "$TAG" "$SHORT_SHA"
    exit 0
fi

# ── Deploy ───────────────────────────────────────────────────────
log "Positions clear. Starting deploy of $TAG ($SHORT_SHA)"
git checkout production 2>/dev/null || {
    write_state "failed" "$TAG" "$SHORT_SHA" "production_checkout_failed"
    log "ERROR: Could not check out the production branch"
    exit 1
}
git reset --hard origin/production 2>/dev/null || {
    write_state "failed" "$TAG" "$SHORT_SHA" "production_reset_failed"
    log "ERROR: Could not reset to origin/production"
    exit 1
}
write_state "deploying" "$TAG" "$SHORT_SHA"
exec "$BOT_DIR/deploy/deploy.sh" "$TAG"
