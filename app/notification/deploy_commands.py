"""
Telegram command handlers for deploy operations.

These are registered alongside the trading commands in TelegramNotifier.
They communicate with the deploy system via flag files and state files —
no subprocess calls, no sudo, no imports from deploy/.

Commands:
  /force_deploy   — Write flag file to trigger immediate deploy
  /deploy_status  — Read deploy state file and report
  /cancel_deploy  — Write flag file to cancel pending deploy
  /bot_version    — Read VERSION file and status file
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from app.core.constants import (
    CANCEL_DEPLOY_FLAG,
    DEPLOY_STATE_PATH,
    FORCE_DEPLOY_FLAG,
    STATUS_FILE_PATH,
)
from app.notification.formatting import mono, row

logger = structlog.get_logger(__name__)
_VERSION_FILE = Path(__file__).resolve().parent.parent.parent / "VERSION"

# Stale threshold for status file (seconds)
_STALE_THRESHOLD = 300

# Type alias for the send function signature
SendFn = Callable[..., Any]


def _read_json(path: str | Path) -> dict | None:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def handle_force_deploy(send_fn: SendFn, chat_id: str) -> None:
    """Write flag file to trigger force deploy on next timer tick."""
    try:
        with open(FORCE_DEPLOY_FLAG, "w") as f:
            f.write(datetime.now(UTC).isoformat())
        send_fn(
            mono("⚡ FORCE DEPLOY\n\nFlag written. Deploy will start within 1 minute."),
            chat_id=chat_id,
        )
        logger.info("force_deploy_flag_written")
    except OSError:
        logger.exception("force_deploy_flag_write_failed")
        send_fn(
            mono("❌ Failed to write force deploy flag."),
            chat_id=chat_id,
        )


def handle_deploy_status(send_fn: SendFn, chat_id: str) -> None:
    """Read deploy state file and report current status."""
    state = _read_json(DEPLOY_STATE_PATH)

    if not state:
        send_fn(mono("📦 DEPLOY STATUS\n\nNo deploy state found. System idle."), chat_id=chat_id)
        return

    current = state.get("state", "unknown")
    tag = state.get("tag", "?")

    lines = ["📦 DEPLOY STATUS", ""]
    lines.append(row("State:", current))

    if tag:
        lines.append(row("Tag:", tag))

    if current == "waiting":
        since = state.get("waiting_since", "")
        if since:
            try:
                dt = datetime.fromisoformat(since)
                mins = int((datetime.now(UTC) - dt).total_seconds() / 60)
                lines.append(row("Waiting:", f"{mins}m"))
            except ValueError:
                pass

        bot_status = _read_json(STATUS_FILE_PATH)
        if bot_status:
            lines.append(row("Positions:", str(bot_status.get("position_count", "?"))))

        error = state.get("last_error", "")
        if error:
            lines.append(row("Note:", error))

    last_deploy = state.get("last_deploy", "")
    last_result = state.get("last_result", "")
    if last_deploy:
        lines.extend(["", row("Last deploy:", last_deploy[:19]), row("Result:", last_result)])

    send_fn(mono("\n".join(lines)), chat_id=chat_id)


def handle_cancel_deploy(send_fn: SendFn, chat_id: str) -> None:
    """Write cancel flag to stop a pending (waiting) deploy."""
    state = _read_json(DEPLOY_STATE_PATH)
    current = state.get("state", "idle") if state else "idle"

    if current == "deploying":
        send_fn(
            mono("⚠️ Deploy is already in progress, cannot cancel."),
            chat_id=chat_id,
        )
        return

    if current != "waiting":
        send_fn(mono("ℹ️ No pending deploy to cancel."), chat_id=chat_id)
        return

    try:
        with open(CANCEL_DEPLOY_FLAG, "w") as f:
            f.write(datetime.now(UTC).isoformat())
        tag = state.get("tag", "?") if state else "?"
        send_fn(
            mono(f"🚫 Cancel requested for {tag}.\nWill take effect within 1 minute."),
            chat_id=chat_id,
        )
        logger.info("cancel_deploy_flag_written", tag=tag)
    except OSError:
        logger.exception("cancel_deploy_flag_write_failed")
        send_fn(mono("❌ Failed to write cancel flag."), chat_id=chat_id)


def handle_bot_version(send_fn: SendFn, chat_id: str) -> None:
    """Show deployed version, uptime, and position count."""
    ver = _read_json(_VERSION_FILE) or {}
    status = _read_json(STATUS_FILE_PATH)

    lines = [
        "📦 BOT VERSION",
        "",
        row("Version:", ver.get("tag", "dev")),
        row("SHA:", ver.get("sha", "unknown")),
        row("Deployed:", ver.get("deployed_at", "unknown")[:19]),
    ]

    if status:
        uptime_min = status.get("uptime_seconds", 0) // 60
        lines.extend([
            "",
            row("Status:", status.get("status", "?")),
            row("Uptime:", f"{uptime_min}m"),
            row("Positions:", str(status.get("position_count", 0))),
            row("PID:", str(status.get("pid", "?"))),
        ])

        try:
            updated = datetime.fromisoformat(status["updated_at"])
            age = (datetime.now(UTC) - updated).total_seconds()
            if age > _STALE_THRESHOLD:
                lines.append(f"\n⚠️ Status file stale ({int(age)}s old)")
        except (KeyError, ValueError):
            pass
    else:
        lines.append("\n⚠️ Bot status file not available")

    send_fn(mono("\n".join(lines)), chat_id=chat_id)
