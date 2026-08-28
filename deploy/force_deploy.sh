#!/bin/bash
set -euo pipefail

# Usage: force_deploy.sh [expected-tag]
# Manual SSH fallback deploy. Skips the position check but always deploys the
# commit currently promoted on origin/production. An optional tag is an
# assertion, not an alternate checkout target.

# ── Load shared variables ─────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/deploy_env.sh"

cd "$BOT_DIR"
git fetch origin production
git checkout production
git reset --hard "origin/production"

PROMOTED_TAG=$(git tag --points-at HEAD | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -1)
EXPECTED_TAG="${1:-}"

if [[ -z "$PROMOTED_TAG" ]]; then
    log "ERROR: origin/production is not an exact SemVer tag."
    log "Promote a release through the GitHub Deploy workflow first."
    exit 2
fi

if [[ -n "$EXPECTED_TAG" && "$EXPECTED_TAG" != "$PROMOTED_TAG" ]]; then
    log "ERROR: origin/production is ${PROMOTED_TAG:-untagged}, not $EXPECTED_TAG"
    log "Promote the requested tag through the GitHub Deploy workflow first."
    exit 2
fi

TAG="$PROMOTED_TAG"

log "=== Force deploy (SSH): $TAG ==="
exec "$BOT_DIR/deploy/deploy.sh" "$TAG"
