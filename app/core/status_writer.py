"""
Background thread that writes bot status to a JSON file on disk.

The deploy listener reads this file to check position state before deploying.
Writes atomically (temp file + rename) to prevent partial reads.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from app.core.constants import STATUS_FILE_PATH, STATUS_WRITE_INTERVAL

if TYPE_CHECKING:
    from app.trading.runner import MultiSymbolRunner

logger = structlog.get_logger()

_VERSION_FILE = Path(__file__).resolve().parent.parent.parent / "VERSION"


def _read_version() -> tuple[str, str]:
    """Read version info from VERSION file. Returns (tag, sha)."""
    try:
        with open(_VERSION_FILE) as f:
            data = json.load(f)
        return data.get("tag", "dev"), data.get("sha", "unknown")
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return "dev", "unknown"


def _build_status(runner: MultiSymbolRunner, started_at: datetime) -> dict[str, Any]:
    """Build the status dict from the runner's current state."""
    tag, sha = _read_version()
    now = datetime.now(timezone.utc)

    open_positions: list[dict[str, Any]] = []
    for symbol, portfolio in list(runner.portfolios.items()):
        pos = portfolio.get_position(symbol)
        if pos is not None:
            open_positions.append({
                "symbol": symbol,
                "side": pos.side,
                "size": float(pos.amount),
                "entry_price": float(pos.entry_price),
            })

    return {
        "version": tag,
        "commit_sha": sha,
        "pid": os.getpid(),
        "started_at": started_at.isoformat(),
        "updated_at": now.isoformat(),
        "uptime_seconds": int((now - started_at).total_seconds()),
        "open_positions": open_positions,
        "position_count": len(open_positions),
        "status": "running",
    }


def _write_atomic(path: str, data: dict[str, Any]) -> None:
    """Write JSON atomically via temp file + rename."""
    dir_name = os.path.dirname(path) or "/tmp"
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, path)
    except OSError:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


class StatusWriter:
    """Background daemon thread that periodically writes bot status to disk."""

    def __init__(self, runner: MultiSymbolRunner) -> None:
        self._runner = runner
        self._started_at = datetime.now(timezone.utc)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._loop, name="status-writer", daemon=True
        )

    def start(self) -> None:
        logger.info("status_writer_starting", path=STATUS_FILE_PATH)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                status = _build_status(self._runner, self._started_at)
                _write_atomic(STATUS_FILE_PATH, status)
            except Exception:
                logger.exception("status_write_failed")
            self._stop_event.wait(timeout=STATUS_WRITE_INTERVAL)
