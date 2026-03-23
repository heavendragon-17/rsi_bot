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
import os
from datetime import datetime, timezone
from pathlib import Path

import structlog

from app.core.constants import STATUS_FILE_PATH

logger = structlog.get_logger(__name__)

_DEPLOY_STATE_PATH = "/tmp/rsi_bot_deploy_state.json"
_FORCE_DEPLOY_FLAG = "/tmp/rsi_bot_force_deploy"
_CANCEL_DEPLOY_FLAG = "/tmp/rsi_bot_cancel_deploy"
_VERSION_FILE = Path(__file__).resolve().parent.parent.parent / "VERSION"

# Stale threshold for status file (seconds)
_STALE_THRESHOLD = 300


def _read_json(path: str | Path) -> dict | None:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _mono(text: str) -> str:
    return f"<pre>{text}</pre>"


def _row(label: str, value: str, width: int = 14) -> str:
    return f"{label:<{width}} {value}"


def handle_force_deploy(send_fn: callable, chat_id: str) -> None:
    """Write flag file to trigger force deploy on next timer tick."""
    try:
        with open(_FORCE_DEPLOY_FLAG, "w") as f:
            f.write(datetime.now(timezone.utc).isoformat())
        send_fn(
            _mono("⚡ FORCE DEPLOY\n\nFlag written. Deploy will start within 1 minute."),
            chat_id=chat_id,
        )
        logger.info("force_deploy_flag_written")
    except OSError:
        logger.exception("force_deploy_flag_write_failed")
        send_fn(
            _mono("❌ Failed to write force deploy flag."),
            chat_id=chat_id,
        )


def handle_deploy_status(send_fn: callable, chat_id: str) -> None:
    """Read deploy state file and report current status."""
    state = _read_json(_DEPLOY_STATE_PATH)

    if not state:
        send_fn(_mono("📦 DEPLOY STATUS\n\nNo deploy state found. System idle."), chat_id=chat_id)
        return

    current = state.get("state", "unknown")
    tag = state.get("tag", "?")

    lines = ["📦 DEPLOY STATUS", ""]
    lines.append(_row("State:", current))

    if tag:
        lines.append(_row("Tag:", tag))

    if current == "waiting":
        since = state.get("waiting_since", "")
        if since:
            try:
                dt = datetime.fromisoformat(since)
                mins = int((datetime.now(timezone.utc) - dt).total_seconds() / 60)
                lines.append(_row("Waiting:", f"{mins}m"))
            except ValueError:
                pass

        # Read position count from bot status
        bot_status = _read_json(STATUS_FILE_PATH)
        if bot_status:
            lines.append(_row("Positions:", str(bot_status.get("position_count", "?"))))

        error = state.get("last_error", "")
        if error:
            lines.append(_row("Note:", error))

    last_deploy = state.get("last_deploy", "")
    last_result = state.get("last_result", "")
    if last_deploy:
        lines.extend(["", _row("Last deploy:", last_deploy[:19]), _row("Result:", last_result)])

    send_fn(_mono("\n".join(lines)), chat_id=chat_id)


def handle_cancel_deploy(send_fn: callable, chat_id: str) -> None:
    """Write cancel flag to stop a pending (waiting) deploy."""
    state = _read_json(_DEPLOY_STATE_PATH)
    current = state.get("state", "idle") if state else "idle"

    if current == "deploying":
        send_fn(
            _mono("⚠️ Deploy is already in progress, cannot cancel."),
            chat_id=chat_id,
        )
        return

    if current not in ("waiting",):
        send_fn(_mono("ℹ️ No pending deploy to cancel."), chat_id=chat_id)
        return

    try:
        with open(_CANCEL_DEPLOY_FLAG, "w") as f:
            f.write(datetime.now(timezone.utc).isoformat())
        tag = state.get("tag", "?") if state else "?"
        send_fn(
            _mono(f"🚫 Cancel requested for {tag}.\nWill take effect within 1 minute."),
            chat_id=chat_id,
        )
        logger.info("cancel_deploy_flag_written", tag=tag)
    except OSError:
        logger.exception("cancel_deploy_flag_write_failed")
        send_fn(_mono("❌ Failed to write cancel flag."), chat_id=chat_id)


def handle_bot_version(send_fn: callable, chat_id: str) -> None:
    """Show deployed version, uptime, and position count."""
    ver = _read_json(_VERSION_FILE) or {}
    status = _read_json(STATUS_FILE_PATH)

    lines = [
        "📦 BOT VERSION",
        "",
        _row("Version:", ver.get("tag", "dev")),
        _row("SHA:", ver.get("sha", "unknown")),
        _row("Deployed:", ver.get("deployed_at", "unknown")[:19]),
    ]

    if status:
        uptime_min = status.get("uptime_seconds", 0) // 60
        lines.extend([
            "",
            _row("Status:", status.get("status", "?")),
            _row("Uptime:", f"{uptime_min}m"),
            _row("Positions:", str(status.get("position_count", 0))),
            _row("PID:", str(status.get("pid", "?"))),
        ])

        # Check staleness
        try:
            updated = datetime.fromisoformat(status["updated_at"])
            age = (datetime.now(timezone.utc) - updated).total_seconds()
            if age > _STALE_THRESHOLD:
                lines.append(f"\n⚠️ Status file stale ({int(age)}s old)")
        except (KeyError, ValueError):
            pass
    else:
        lines.append("\n⚠️ Bot status file not available")

    send_fn(_mono("\n".join(lines)), chat_id=chat_id)
