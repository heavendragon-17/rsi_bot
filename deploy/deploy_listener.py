"""
Telegram-based deploy listener for VPS.

Polls Telegram for deploy triggers from GitHub Actions and user commands.
Runs as a systemd service (deploy-listener.service).

Commands:
  DEPLOY:<tag>:<sha>:<message>  — Auto-deploy trigger from CI
  /force_deploy                 — Deploy immediately, skip position check
  /bot_version                  — Show deployed version and health info
  /deploy_status                — Show current deploy state
  /cancel_deploy                — Cancel a pending deploy
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------
TELEGRAM_TOKEN = os.environ["DEPLOY_TELEGRAM_BOT_TOKEN"]
CHAT_ID = int(os.environ["DEPLOY_TELEGRAM_CHAT_ID"])
BOT_DIR = os.environ.get("BOT_DIR", "/home/user/rsi_bot")
STATUS_FILE = os.environ.get("STATUS_FILE", "/tmp/rsi_bot_status.json")
VERSION_FILE = os.environ.get("VERSION_FILE", f"{BOT_DIR}/VERSION")
DEPLOY_SCRIPT = str(Path(__file__).parent / "deploy.sh")

POLL_TIMEOUT = 30  # Telegram long-poll seconds
POSITION_CHECK_INTERVAL = 30  # seconds between position checks
STATUS_STALE_THRESHOLD = 300  # 5 minutes

TAG_PATTERN = re.compile(r"^v\d+\.\d+\.\d+$")
DEPLOY_MSG_PATTERN = re.compile(r"^DEPLOY:(v[\d.]+):([a-f0-9]+):(.*)$")

API_BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("deploy-listener")

# ---------------------------------------------------------------------------
# Telegram helpers
# ---------------------------------------------------------------------------


def send_message(text: str) -> None:
    """Send a Telegram message to the deploy chat."""
    try:
        requests.post(
            f"{API_BASE}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text},
            timeout=10,
        )
    except Exception:
        log.exception("Failed to send Telegram message")


def get_updates(offset: int) -> list[dict]:
    """Long-poll Telegram for new messages."""
    try:
        resp = requests.get(
            f"{API_BASE}/getUpdates",
            params={"offset": offset, "timeout": POLL_TIMEOUT},
            timeout=POLL_TIMEOUT + 10,
        )
        data = resp.json()
        if data.get("ok"):
            return data.get("result", [])
    except Exception:
        log.exception("Failed to get Telegram updates")
    return []


# ---------------------------------------------------------------------------
# Status file helpers
# ---------------------------------------------------------------------------


def read_status() -> dict | None:
    """Read the bot status file. Returns None if unreadable or stale."""
    try:
        with open(STATUS_FILE) as f:
            data = json.load(f)
        # Check staleness
        updated = datetime.fromisoformat(data["updated_at"])
        age = (datetime.now(timezone.utc) - updated).total_seconds()
        if age > STATUS_STALE_THRESHOLD:
            log.warning("Status file stale: %.0fs old", age)
            return None
        return data
    except (FileNotFoundError, json.JSONDecodeError, KeyError, OSError):
        return None


def read_version() -> dict:
    """Read the VERSION file written by deploy.sh."""
    try:
        with open(VERSION_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"tag": "unknown", "sha": "unknown", "deployed_at": "unknown"}


# ---------------------------------------------------------------------------
# Deploy execution
# ---------------------------------------------------------------------------


def run_deploy(tag: str, sha: str) -> tuple[bool, str]:
    """Execute deploy.sh and return (success, output)."""
    try:
        result = subprocess.run(
            [DEPLOY_SCRIPT, tag, sha],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output[-500:] if len(output) > 500 else output
    except subprocess.TimeoutExpired:
        return False, "Deploy script timed out after 5 minutes"
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Deploy state machine
# ---------------------------------------------------------------------------


class DeployManager:
    """Manages pending deploy state and position-wait logic."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending_tag: str | None = None
        self._pending_sha: str | None = None
        self._pending_message: str | None = None
        self._waiting_since: datetime | None = None
        self._deploying = False
        self._cancel_event = threading.Event()
        self._deploy_thread: threading.Thread | None = None
        self._last_deploy_time: datetime | None = None
        self._last_deploy_result: str | None = None

    @property
    def is_idle(self) -> bool:
        return self._pending_tag is None and not self._deploying

    def trigger_deploy(self, tag: str, sha: str, message: str) -> None:
        """Queue a new deploy. Cancels any pending deploy."""
        with self._lock:
            if self._pending_tag or self._deploying:
                old = self._pending_tag or "current"
                log.info("Cancelling pending deploy %s for new %s", old, tag)
                self._cancel_event.set()
                send_message(
                    f"⚠️ Superseding pending deploy {old} with {tag}"
                )
            self._pending_tag = tag
            self._pending_sha = sha
            self._pending_message = message
            self._waiting_since = None
            self._cancel_event = threading.Event()

        send_message(
            f"🔄 Deploy {tag} received. Checking positions..."
        )
        self._start_deploy_thread()

    def force_deploy(self) -> None:
        """Force deploy immediately, skip position check."""
        with self._lock:
            if self._pending_tag:
                tag, sha = self._pending_tag, self._pending_sha
                self._cancel_event.set()
                self._cancel_event = threading.Event()
            else:
                ver = read_version()
                tag = ver.get("tag", "latest")
                sha = ver.get("sha", "unknown")
                self._pending_tag = tag
                self._pending_sha = sha
                self._pending_message = "Force deploy"

        send_message(f"⚡ Force deploying {tag}...")
        self._execute_deploy(tag, sha)

    def cancel(self) -> str:
        """Cancel a pending deploy."""
        with self._lock:
            if self._pending_tag and not self._deploying:
                tag = self._pending_tag
                self._cancel_event.set()
                self._pending_tag = None
                self._pending_sha = None
                self._waiting_since = None
                return f"🚫 Cancelled pending deploy {tag}"
            if self._deploying:
                return "⚠️ Deploy is already in progress, cannot cancel"
            return "ℹ️ No pending deploy to cancel"

    def get_status_text(self) -> str:
        """Get human-readable deploy status."""
        with self._lock:
            if self._deploying:
                return f"🔧 Deploying {self._pending_tag}..."
            if self._pending_tag and self._waiting_since:
                status = read_status()
                n = status["position_count"] if status else "?"
                wait_min = int(
                    (datetime.now(timezone.utc) - self._waiting_since).total_seconds()
                    / 60
                )
                return (
                    f"⏳ Waiting for positions to close\n"
                    f"  Tag: {self._pending_tag}\n"
                    f"  Open positions: {n}\n"
                    f"  Waiting: {wait_min}m"
                )
            if self._last_deploy_time:
                return (
                    f"✅ Idle\n"
                    f"  Last deploy: {self._last_deploy_time:%Y-%m-%d %H:%M}\n"
                    f"  Result: {self._last_deploy_result}"
                )
            return "✅ Idle — no deploys yet"

    def _start_deploy_thread(self) -> None:
        t = threading.Thread(target=self._wait_and_deploy, daemon=True)
        t.start()
        self._deploy_thread = t

    def _wait_and_deploy(self) -> None:
        """Wait for positions to close, then deploy."""
        cancel = self._cancel_event
        tag = self._pending_tag
        sha = self._pending_sha

        # Check positions
        status = read_status()
        if status and status.get("position_count", 0) > 0:
            count = status["position_count"]
            send_message(
                f"⏳ Waiting for {count} position(s) to close before deploying {tag}..."
            )
            with self._lock:
                self._waiting_since = datetime.now(timezone.utc)

            while not cancel.is_set():
                cancel.wait(timeout=POSITION_CHECK_INTERVAL)
                if cancel.is_set():
                    log.info("Deploy %s cancelled during position wait", tag)
                    return
                status = read_status()
                if status is None:
                    send_message(
                        f"⚠️ Bot status file stale/missing. "
                        f"Bot may be down. Not proceeding with deploy {tag}."
                    )
                    with self._lock:
                        self._pending_tag = None
                    return
                if status.get("position_count", 0) == 0:
                    break
        elif status is None:
            send_message(
                f"⚠️ Bot status file not found. Proceeding with deploy {tag} anyway."
            )

        if cancel.is_set():
            return

        self._execute_deploy(tag, sha)

    def _execute_deploy(self, tag: str, sha: str) -> None:
        """Run the deploy script and report results."""
        with self._lock:
            self._deploying = True

        send_message(f"🚀 Starting deploy {tag} ({sha})...")

        success, output = run_deploy(tag, sha)
        now = datetime.now(timezone.utc)

        with self._lock:
            self._deploying = False
            self._pending_tag = None
            self._pending_sha = None
            self._waiting_since = None
            self._last_deploy_time = now

        if success:
            self._last_deploy_result = "success"
            send_message(f"✅ {tag} deployed successfully")
            log.info("Deploy %s succeeded", tag)
        else:
            self._last_deploy_result = f"FAILED: {output[:200]}"
            send_message(
                f"❌ Deploy {tag} FAILED:\n{output[:300]}"
            )
            log.error("Deploy %s failed: %s", tag, output[:200])


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def handle_bot_version() -> str:
    """Build /bot_version response."""
    ver = read_version()
    status = read_status()

    lines = [
        f"📦 Version: {ver.get('tag', '?')}",
        f"🔑 SHA: {ver.get('sha', '?')}",
        f"📅 Deployed: {ver.get('deployed_at', '?')}",
    ]

    if status:
        lines.extend([
            f"⏱ Uptime: {status.get('uptime_seconds', 0) // 60}m",
            f"📊 Positions: {status.get('position_count', 0)}",
            f"💓 Status: {status.get('status', '?')}",
        ])
    else:
        lines.append("⚠️ Bot status file not available")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def main() -> None:
    log.info("Deploy listener starting. Chat ID: %s", CHAT_ID)
    send_message("🟢 Deploy listener started")

    manager = DeployManager()
    offset = 0

    while True:
        updates = get_updates(offset)

        for update in updates:
            offset = update["update_id"] + 1
            msg = update.get("message", {})
            chat = msg.get("chat", {}).get("id")
            text = (msg.get("text") or "").strip()

            if chat != CHAT_ID:
                continue

            # Deploy trigger from CI
            match = DEPLOY_MSG_PATTERN.match(text)
            if match:
                tag, sha, message = match.groups()
                if TAG_PATTERN.match(tag):
                    log.info("Deploy trigger: %s %s", tag, sha)
                    manager.trigger_deploy(tag, sha, message)
                else:
                    log.warning("Invalid tag format: %s", tag)
                continue

            # User commands
            if text == "/force_deploy":
                manager.force_deploy()
            elif text == "/bot_version":
                send_message(handle_bot_version())
            elif text == "/deploy_status":
                send_message(manager.get_status_text())
            elif text == "/cancel_deploy":
                send_message(manager.cancel())


if __name__ == "__main__":
    main()
