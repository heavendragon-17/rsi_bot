"""Simple scripted baseline for the hour-seasonality estimand (comparison only).

Ten-line vectorized pandas reproduction over the same candles and 60-minute
horizon: forward returns for every contiguous bar, grouped into 13-16 UTC
versus all other hours. Used only to compare quality, reproducibility, wall
time and observed usage against research/experiments/m5/hour_seasonality.py.
No trading, publication or alpha claim follows.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd


def main() -> int:
    candles_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    started = time.monotonic()
    # Independent vectorized oracle for hour_seasonality.py (loop audit).
    # Same frozen window, horizon and hour split; see hour_seasonality.py.
    frame = pd.read_csv(candles_path, keep_default_na=False, encoding="utf-8-sig")
    opens = pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], utc=True, format="mixed"))
    closes = frame["close"].to_numpy(dtype=float)
    close_times = opens + pd.Timedelta(minutes=5)
    steps = 12
    breaks = np.zeros(len(opens), dtype=np.int64)
    breaks[1:] = np.asarray(opens[1:] - opens[:-1]) != np.timedelta64(5, "m")
    prefix = breaks.cumsum()
    in_window = (close_times[:-steps] >= pd.Timestamp("2022-08-28T00:00:00Z")) & \
                (close_times[:-steps] < pd.Timestamp("2026-08-28T00:00:00Z"))
    eligible = (prefix[steps:] == prefix[:-steps]) & in_window
    returns = (closes[steps:] / closes[:-steps] - 1) * 100
    hours = close_times[:-steps].hour
    mask = eligible
    cand = returns[mask & np.isin(hours, [13, 14, 15, 16])]
    base = returns[mask & ~np.isin(hours, [13, 14, 15, 16])]
    result = {"candidate_n": int(len(cand)), "baseline_n": int(len(base)),
              "candidate_mean": float(np.mean(cand)), "baseline_mean": float(np.mean(base)),
              "difference_pp": float(np.mean(cand) - np.mean(base)),
              "wall_seconds": time.monotonic() - started}
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
