#!/bin/bash
set -euo pipefail

# install.sh — Generate and install systemd services from deploy_env.sh.
# Run this once on the VPS after cloning, or after changing BOT_DIR.
#
# Usage: sudo deploy/install.sh

# ── Load shared variables ─────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/deploy_env.sh"

SYSTEMD_DIR="/etc/systemd/system"

echo "Installing services with:"
echo "  BOT_DIR       = $BOT_DIR"
echo "  VENV_DIR      = $VENV_DIR"
echo "  SERVICE_USER  = $SERVICE_USER"
echo "  SERVICE_NAME  = $SERVICE_NAME"
echo ""

# ── Generate rsi-bot.service ─────────────────────────────────────
cat > "$SYSTEMD_DIR/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=RSI Trading Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${BOT_DIR}
Environment=PATH=${VENV_DIR}/bin:/usr/bin:/bin
ExecStart=${VENV_DIR}/bin/python main.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

echo "Wrote $SYSTEMD_DIR/${SERVICE_NAME}.service"

# ── Generate check-deploy.service ────────────────────────────────
cat > "$SYSTEMD_DIR/check-deploy.service" <<EOF
[Unit]
Description=Check and deploy RSI Bot if new version available
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=${SERVICE_USER}
WorkingDirectory=${BOT_DIR}
ExecStart=${BOT_DIR}/deploy/check_deploy.sh
StandardOutput=journal
StandardError=journal
EOF

echo "Wrote $SYSTEMD_DIR/check-deploy.service"

# ── Generate check-deploy.timer ──────────────────────────────────
cat > "$SYSTEMD_DIR/check-deploy.timer" <<EOF
[Unit]
Description=Check for new RSI Bot deployments (every 1 min)

[Timer]
OnBootSec=60
OnUnitActiveSec=60
AccuracySec=5

[Install]
WantedBy=timers.target
EOF

echo "Wrote $SYSTEMD_DIR/check-deploy.timer"

# ── Create log file ──────────────────────────────────────────────
touch "$LOG_FILE"
chown "$SERVICE_USER":"$SERVICE_USER" "$LOG_FILE"
echo "Created $LOG_FILE"

# ── Reload and enable ────────────────────────────────────────────
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
echo ""
echo "Done. To start the bot:"
echo "  sudo systemctl start $SERVICE_NAME"
echo ""
echo "To enable auto-deploy:"
echo "  sudo systemctl enable --now check-deploy.timer"
