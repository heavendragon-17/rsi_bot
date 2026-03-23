"""Lightweight CLI progress bar for backtest runners (no external deps)."""

from __future__ import annotations

import shutil
import sys
import time


class CliProgressBar:
    """Reusable terminal progress bar.

    Accepts the same ``{"pct": int, ...}`` dicts that engines emit,
    or plain int/float percentages.

    Usage::

        bar = CliProgressBar("Portfolio backtest")
        runner.run(progress_cb=bar.update)
        bar.finish()
    """

    def __init__(self, label: str = "Progress", bar_width: int | None = None):
        self.label = label
        self._bar_width = bar_width
        self._last_pct = -1
        self._start = time.monotonic()

    def _cols(self) -> int:
        return self._bar_width or max(shutil.get_terminal_size().columns, 40)

    def update(self, value: dict | int | float) -> None:
        """Accept engine progress callback or raw percentage."""
        if isinstance(value, dict):
            pct = int(value.get("pct", 0))
        else:
            pct = int(value)
        pct = max(0, min(pct, 100))
        if pct == self._last_pct:
            return
        self._last_pct = pct
        self._render(pct)

    def _render(self, pct: int) -> None:
        elapsed = time.monotonic() - self._start
        elapsed_str = _fmt_time(elapsed)
        if pct > 0:
            eta = elapsed / pct * (100 - pct)
            eta_str = _fmt_time(eta)
        else:
            eta_str = "--:--"

        cols = self._cols()
        # Layout:  Label  [####····]  42%  0:12/0:30
        suffix = f" {pct:3d}%  {elapsed_str}/{eta_str}"
        prefix = f"\r{self.label}  "
        bar_space = cols - len(prefix) - len(suffix) - 2  # 2 for []
        if bar_space < 5:
            bar_space = 5
        filled = int(bar_space * pct / 100)
        bar = "#" * filled + "·" * (bar_space - filled)
        sys.stderr.write(f"{prefix}[{bar}]{suffix}")
        sys.stderr.flush()

    def finish(self, extra: str = "") -> None:
        """Complete the progress bar and move to next line."""
        if self._last_pct < 100:
            self.update(100)
        elapsed = _fmt_time(time.monotonic() - self._start)
        msg = f"  done in {elapsed}"
        if extra:
            msg += f"  {extra}"
        sys.stderr.write(msg + "\n")
        sys.stderr.flush()


def _fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
