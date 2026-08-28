#!/bin/bash
set -euo pipefail

# Usage: deploy.sh <tag>
# Called by check_deploy.sh or force_deploy.sh after the production checkout
# has been moved to the candidate commit.

TAG="${1:?Usage: deploy.sh <tag>}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/deploy_env.sh"

update_deploy_state() {
    local state="$1" error="${2:-}"
    DS_STATE="$state" DS_ERROR="$error" DS_PATH="$DEPLOY_STATE" \
    python3 -c "
import json, os, tempfile
from datetime import datetime, timezone
now = datetime.now(timezone.utc).isoformat()
path = os.environ['DS_PATH']
state = os.environ['DS_STATE']
error = os.environ['DS_ERROR']
try:
    with open(path) as f:
        data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    data = {}
data['state'] = state
data['updated_at'] = now
if state in ('completed', 'failed'):
    data['last_deploy'] = now
    data['last_result'] = state
    data['last_error'] = error
    data['waiting_since'] = ''
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
" 2>/dev/null || true
}

read_version_field() {
    local field="$1"
    VF_PATH="$VERSION_FILE" VF_FIELD="$field" python3 -c "
import json, os
try:
    with open(os.environ['VF_PATH']) as f:
        print(json.load(f).get(os.environ['VF_FIELD'], ''))
except (FileNotFoundError, json.JSONDecodeError, OSError):
    print('')
" 2>/dev/null
}

write_version() {
    local tag="$1" sha="$2"
    VF_PATH="$VERSION_FILE" VF_TAG="$tag" VF_SHA="$sha" python3 -c "
import json, os, tempfile
from datetime import datetime, timezone
path = os.environ['VF_PATH']
directory = os.path.dirname(path) or '.'
fd, temporary = tempfile.mkstemp(dir=directory, prefix='.VERSION.', text=True)
try:
    with os.fdopen(fd, 'w') as f:
        json.dump({
            'tag': os.environ['VF_TAG'],
            'sha': os.environ['VF_SHA'],
            'deployed_at': datetime.now(timezone.utc).isoformat(),
        }, f)
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

install_requirements() {
    source "$VENV_DIR/bin/activate"
    python -m pip install -r requirements.txt --quiet 2>&1 | tee -a "$LOG_FILE"
}

wait_for_health() {
    local expected_tag="$1" expected_sha="$2" minimum_started_epoch="$3"
    local status attempt timeout

    sleep "$HEALTH_CHECK_INTERVAL"
    for attempt in $(seq 1 "$HEALTH_CHECK_ATTEMPTS"); do
        if [[ -f "$STATUS_FILE" ]]; then
            status=$(HC_PATH="$STATUS_FILE" HC_TAG="$expected_tag" \
                HC_SHA="$expected_sha" HC_STARTED="$minimum_started_epoch" \
                python3 -c "
import json, os
from datetime import datetime
with open(os.environ['HC_PATH']) as f:
    data = json.load(f)
reported_sha = str(data.get('commit_sha', ''))
expected_sha = os.environ['HC_SHA']
sha_matches = (
    bool(reported_sha)
    and (expected_sha.startswith(reported_sha) or reported_sha.startswith(expected_sha))
)
started = datetime.fromisoformat(str(data.get('started_at', '')).replace('Z', '+00:00'))
started_after_restart = started.timestamp() >= int(os.environ['HC_STARTED'])
if (
    data.get('status') == 'running'
    and data.get('version') == os.environ['HC_TAG']
    and sha_matches
    and started_after_restart
):
    print('HEALTHY')
else:
    print(
        'NOT_READY: '
        f\"status={data.get('status')}, version={data.get('version')}, \"
        f\"sha={reported_sha}, started_at={data.get('started_at')}\"
    )
" 2>&1) || status="READ_ERROR"
            if [[ "$status" == "HEALTHY" ]]; then
                return 0
            fi
        else
            status="NO_STATUS_FILE"
        fi
        log "Health check attempt $attempt/$HEALTH_CHECK_ATTEMPTS: $status"
        sleep "$HEALTH_CHECK_INTERVAL"
    done

    timeout=$((HEALTH_CHECK_INTERVAL * HEALTH_CHECK_ATTEMPTS))
    log "ERROR: Health check failed after ${timeout}s."
    return 1
}

restore_previous_version() {
    if [[ "$HAD_PREVIOUS_VERSION" == "1" ]]; then
        cp -- "$VERSION_BACKUP" "$VERSION_FILE"
    else
        rm -f -- "$VERSION_FILE"
    fi
}

rollback_release() {
    local reason="$1" rollback_started

    if [[ -z "$ROLLBACK_SHA" || -z "$PREVIOUS_TAG" ]]; then
        restore_previous_version
        update_deploy_state "failed" "${reason}_no_rollback_available"
        log "ERROR: No verified previous release is available for rollback."
        return 1
    fi

    log "Rolling back to $PREVIOUS_TAG ($ROLLBACK_SHA)..."
    if ! git reset --hard "$ROLLBACK_SHA" >>"$LOG_FILE" 2>&1; then
        restore_previous_version
        update_deploy_state "failed" "${reason}_rollback_checkout_failed"
        log "ERROR: Could not restore the previous source revision."
        return 1
    fi

    if ! install_requirements; then
        restore_previous_version
        update_deploy_state "failed" "${reason}_rollback_dependencies_failed"
        log "ERROR: Could not restore the previous dependencies."
        return 1
    fi

    restore_previous_version
    rm -f -- "$STATUS_FILE"
    rollback_started=$(date +%s)
    if ! sudo -n systemctl restart "$SERVICE_NAME"; then
        update_deploy_state "failed" "${reason}_rollback_restart_failed"
        log "ERROR: Previous release was restored on disk but could not be restarted."
        return 1
    fi

    if wait_for_health "$PREVIOUS_TAG" "$ROLLBACK_SHA" "$rollback_started"; then
        update_deploy_state "failed" "${reason}_rolled_back"
        log "Rollback health check passed; $PREVIOUS_TAG is running."
        return 0
    fi

    update_deploy_state "failed" "${reason}_rollback_health_failed"
    log "ERROR: Rollback completed on disk but did not become healthy."
    return 1
}

cd "$BOT_DIR"

CANDIDATE_SHA=$(git rev-parse HEAD)
if [[ ! "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    log "ERROR: Deployment tag must match vMAJOR.MINOR.PATCH; received '$TAG'."
    update_deploy_state "failed" "invalid_release_tag"
    exit 2
fi
TAG_SHA=$(git rev-parse --verify "${TAG}^{commit}" 2>/dev/null || true)
if [[ -z "$TAG_SHA" || "$TAG_SHA" != "$CANDIDATE_SHA" ]]; then
    log "ERROR: $TAG does not resolve to the checked-out candidate $CANDIDATE_SHA."
    update_deploy_state "failed" "release_tag_mismatch"
    exit 2
fi
PREVIOUS_TAG=$(read_version_field tag)
PREVIOUS_SHA=$(read_version_field sha)
ROLLBACK_SHA=""
if [[ -n "$PREVIOUS_SHA" ]]; then
    ROLLBACK_SHA=$(git rev-parse --verify "${PREVIOUS_SHA}^{commit}" 2>/dev/null || true)
fi

VERSION_BACKUP=$(mktemp)
HAD_PREVIOUS_VERSION=0
if [[ -f "$VERSION_FILE" ]]; then
    cp -- "$VERSION_FILE" "$VERSION_BACKUP"
    HAD_PREVIOUS_VERSION=1
fi
trap 'rm -f -- "$VERSION_BACKUP"' EXIT

log "=== Starting deploy: $TAG ($CANDIDATE_SHA) ==="

if ! install_requirements; then
    log "ERROR: Dependency installation failed."
    rollback_release "dependency_install_failed" || true
    exit 2
fi

log "Running smoke test..."
SMOKE_OUTPUT=$(python -c "
from app.core import interfaces, config, constants, actions
from app.data import indicators
cfg = config.AppConfig.from_yaml('config.yaml')
print(f'Config loaded: mode={cfg.exchange.mode}, symbols={cfg.symbols}')
print('Smoke test PASSED')
" 2>&1) || {
    log "ERROR: Smoke test failed."
    log "$SMOKE_OUTPUT"
    rollback_release "smoke_test_failed" || true
    exit 2
}
log "$SMOKE_OUTPUT"

if ! write_version "$TAG" "$CANDIDATE_SHA"; then
    log "ERROR: Could not stage the candidate VERSION file."
    rollback_release "version_write_failed" || true
    exit 2
fi
if ! rm -f -- "$STATUS_FILE"; then
    log "ERROR: Could not clear the previous status file."
    rollback_release "status_clear_failed" || true
    exit 2
fi

log "Restarting $SERVICE_NAME service..."
RESTARTED_AT=$(date +%s)
if ! sudo -n systemctl restart "$SERVICE_NAME"; then
    log "ERROR: Service restart failed."
    rollback_release "service_restart_failed" || true
    exit 3
fi

log "Waiting for candidate health check..."
if wait_for_health "$TAG" "$CANDIDATE_SHA" "$RESTARTED_AT"; then
    log "Health check passed: bot running $TAG"
    update_deploy_state "completed"
    exit 0
fi

log "Candidate health check failed; starting rollback."
rollback_release "health_check_timeout" || true
exit 3
