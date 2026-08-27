#!/bin/bash
# deploy_env.sh — Single source of truth for all deploy paths and variables.
# Sourced by deploy.sh, check_deploy.sh, and force_deploy.sh.
#
# Production VPS installation paths. Keep these aligned with the systemd units.
# If either value changes, re-run: sudo deploy/install.sh

# ── Core paths ────────────────────────────────────────────────────
BOT_DIR="/opt/rsi_bot"
VENV_DIR="$BOT_DIR/venv"
VERSION_FILE="$BOT_DIR/VERSION"

# ── Runtime state files (/tmp) ────────────────────────────────────
STATUS_FILE="/tmp/rsi_bot_status.json"
DEPLOY_STATE="/tmp/rsi_bot_deploy_state.json"
FORCE_FLAG="/tmp/rsi_bot_force_deploy"
CANCEL_FLAG="/tmp/rsi_bot_cancel_deploy"

# ── Logging ───────────────────────────────────────────────────────
LOG_FILE="/var/log/rsi-bot-deploy.log"

# ── Systemd service name ─────────────────────────────────────────
SERVICE_NAME="rsi-bot"

# ── Deploy behavior ──────────────────────────────────────────────
STALE_THRESHOLD=300  # seconds before status file is considered stale
HEALTH_CHECK_INTERVAL=5  # seconds between health check attempts
HEALTH_CHECK_ATTEMPTS=12  # total attempts (interval * attempts = timeout)

# ── Service user (for systemd) ───────────────────────────────────
SERVICE_USER="botuser"

# ── Shared helper ─────────────────────────────────────────────────
log() { echo "[$(date -Iseconds)] $*" | tee -a "$LOG_FILE"; }
