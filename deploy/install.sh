#!/bin/bash
set -euo pipefail

# install.sh — Generate and install systemd services from deploy_env.sh.
# Run this once on the VPS after cloning, or after changing BOT_DIR.
#
# Usage: sudo deploy/install.sh

if [[ "$EUID" -ne 0 ]]; then
    echo "ERROR: install.sh must run as root (use sudo)." >&2
    exit 1
fi

# ── Load shared variables ─────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/deploy_env.sh"

SYSTEMD_DIR="/etc/systemd/system"

if [[ ! "$SERVICE_USER" =~ ^[a-z_][a-z0-9_-]*$ ]]; then
    echo "ERROR: Invalid SERVICE_USER: $SERVICE_USER" >&2
    exit 1
fi
if [[ ! "$SERVICE_NAME" =~ ^[A-Za-z0-9@_.-]+$ ]]; then
    echo "ERROR: Invalid SERVICE_NAME: $SERVICE_NAME" >&2
    exit 1
fi
if [[ ! "$CORE_SERVICE_NAME" =~ ^[A-Za-z0-9@_.-]+$ ]]; then
    echo "ERROR: Invalid CORE_SERVICE_NAME: $CORE_SERVICE_NAME" >&2
    exit 1
fi
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    echo "ERROR: Service user '$SERVICE_USER' does not exist." >&2
    exit 1
fi
if [[ ! -d "$BOT_DIR" || ! -x "$VENV_DIR/bin/python" ]]; then
    echo "ERROR: BOT_DIR or its virtual environment is not ready." >&2
    exit 1
fi
if ! sudo -u "$SERVICE_USER" test -w "$BOT_DIR"; then
    echo "ERROR: $SERVICE_USER must own or be able to write $BOT_DIR." >&2
    exit 1
fi

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
Environment=PYTHONUNBUFFERED=1
ExecStart=${VENV_DIR}/bin/python main.py
Restart=on-failure
RestartSec=10
UMask=0077
NoNewPrivileges=true
PrivateDevices=true
ProtectControlGroups=true
ProtectKernelModules=true
ProtectKernelTunables=true
RestrictSUIDSGID=true
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

echo "Wrote $SYSTEMD_DIR/${SERVICE_NAME}.service"

# ── Generate the optional Core V2.1 signal-only service ──────────
cat > "$SYSTEMD_DIR/${CORE_SERVICE_NAME}.service" <<EOF
[Unit]
Description=RSI Core V2.1 Signal Runtime
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${BOT_DIR}
Environment=PATH=${VENV_DIR}/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-${BOT_DIR}/.env
ExecStart=${VENV_DIR}/bin/python -m app.signal.core_v2_1.live --config ${BOT_DIR}/config.yaml --state-db ${CORE_STATE_FILE} --data-dir ${CORE_DATA_DIR} --poll-seconds 15
Restart=on-failure
RestartSec=15
UMask=0077
NoNewPrivileges=true
PrivateDevices=true
ProtectControlGroups=true
ProtectKernelModules=true
ProtectKernelTunables=true
RestrictSUIDSGID=true
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

echo "Wrote $SYSTEMD_DIR/${CORE_SERVICE_NAME}.service"

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
UMask=0077
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
Persistent=true

[Install]
WantedBy=timers.target
EOF

echo "Wrote $SYSTEMD_DIR/check-deploy.timer"

# ── Allow only the service lifecycle commands used by deploy.sh ──
SYSTEMCTL_PATH=$(command -v systemctl)
SUDOERS_FILE="/etc/sudoers.d/rsi-bot-deploy"
SUDOERS_TMP=$(mktemp)
trap 'rm -f -- "$SUDOERS_TMP"' EXIT
cat > "$SUDOERS_TMP" <<EOF
Cmnd_Alias RSI_BOT_SYSTEMD = ${SYSTEMCTL_PATH} restart ${SERVICE_NAME}, ${SYSTEMCTL_PATH} start ${SERVICE_NAME}, ${SYSTEMCTL_PATH} stop ${SERVICE_NAME}, ${SYSTEMCTL_PATH} restart ${CORE_SERVICE_NAME}, ${SYSTEMCTL_PATH} start ${CORE_SERVICE_NAME}, ${SYSTEMCTL_PATH} stop ${CORE_SERVICE_NAME}
${SERVICE_USER} ALL=(root) NOPASSWD: RSI_BOT_SYSTEMD
EOF
chmod 0440 "$SUDOERS_TMP"
visudo -cf "$SUDOERS_TMP"
install -m 0440 "$SUDOERS_TMP" "$SUDOERS_FILE"
echo "Wrote $SUDOERS_FILE"

# ── Create log file ──────────────────────────────────────────────
touch "$LOG_FILE"
chown "$SERVICE_USER":"$SERVICE_USER" "$LOG_FILE"
chmod 0600 "$LOG_FILE"
echo "Created $LOG_FILE"

# ── Reload and enable ────────────────────────────────────────────
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl enable "$CORE_SERVICE_NAME"
echo ""
echo "Done. To start the bot:"
echo "  sudo systemctl start $SERVICE_NAME"
echo "Core V2.1 is controlled by core_v2_1.active in config.yaml."
echo "  sudo systemctl start $CORE_SERVICE_NAME"
echo ""
echo "To enable auto-deploy:"
echo "  sudo systemctl enable --now check-deploy.timer"
