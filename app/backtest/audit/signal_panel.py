"""Per-bar (indicator, forward-return) panel for the Information Coefficient test.

Reads the raw OHLCV CSV the engine already consumed
(`app/backtest/data/{SYMBOL_NO_SLASH}_{timeframe}.csv`), runs the same
`Indicators.compute()` call the live strategies use, and pairs each bar's
indicator values with the forward log returns at horizons
`IC_HORIZONS = [1, 4, 16, 96]`.

Why log returns (not pct):
    Log returns are additive across periods and symmetric (a +5% then -5%
    sequence has zero log return; pct returns asymmetrically lose). The
    rank correlation we compute downstream (Spearman) is invariant to
    monotone transforms but the additive property matters for any
    cross-horizon analysis we layer on top later.

No-look-ahead alignment:
    `rsi_14[t]` is computed from bars `[..., t]` — i.e. the close at bar
    `t` is fully observed by definition. The pairing is::

        fwd_logret_h[t] = log(close[t+h]) - log(close[t])

    so `(rsi_14[t], fwd_logret_h[t])` answers "does today's RSI predict
    the return realized over the next h bars?" This is the no-look-ahead
    framing the IC test requires. Implemented as
    `log_close.shift(-h) - log_close` so index `t` holds bar `t+h` minus
    bar `t`, never the other way around.

Trimming:
    Warmup NaNs (RSI14 needs 14 bars, WMA45 of RSI then needs another
    44, so first ~58 rows are NaN on `rsi_wma45`) and the trailing 96
    bars (no `fwd_logret_96`) are dropped via `.dropna()`. Final panel
    length is roughly `len(csv) - 154`.

Output columns (in order):
    close, rsi_14, rsi_ema9, rsi_wma45,
    fwd_logret_1, fwd_logret_4, fwd_logret_16, fwd_logret_96

Indexed by timestamp.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from app.backtest.audit.constants import IC_HORIZONS
from app.data.indicators import Indicators

_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data"

_CANONICAL_INDICATOR_COLS = ["close", "rsi_14", "rsi_ema9", "rsi_wma45"]
_FWD_RETURN_COLS = [f"fwd_logret_{h}" for h in IC_HORIZONS]


@dataclass(frozen=True)
class SignalPanel:
    """Per-bar (indicator, forward-return) panel for one (symbol, timeframe)."""

    df: pd.DataFrame
    symbol: str
    timeframe: str


def _sanitize_symbol(symbol: str) -> str:
    """'BTC/USDT' -> 'BTCUSDT'.

    TODO(audit-sanitize-symbol): consolidate with the 23 other inline
    `symbol.replace('/', '')` call sites listed in
    `docs/CODE_DUPLICATIONS.md` item 5 once a central helper exists.
    Until then, this local implementation keeps the audit module
    self-contained and avoids importing from places that don't yet
    expose a canonical helper.
    """
    return symbol.upper().replace("/", "")


def _resolve_csv_path(symbol: str, timeframe: str, base_dir: Path | None) -> Path:
    base = base_dir if base_dir is not None else _DEFAULT_DATA_DIR
    return base / f"{_sanitize_symbol(symbol)}_{timeframe}.csv"


def build_signal_panel(
    symbol: str,
    timeframe: str,
    *,
    base_dir: Path | None = None,
) -> SignalPanel:
    """Build the per-bar signal panel for `(symbol, timeframe)`.

    Reads `{base_dir}/{SYMBOL_NO_SLASH}_{timeframe}.csv` (default
    `app/backtest/data/`), computes RSI14 / EMA9 / WMA45 via
    `Indicators.compute()`, attaches forward log returns at
    `IC_HORIZONS`, drops NaN rows, returns a frozen `SignalPanel`.
    """
    csv_path = _resolve_csv_path(symbol, timeframe, base_dir)
    if not csv_path.exists():
        raise FileNotFoundError(f"Signal panel CSV not found: {csv_path}")

    raw = pd.read_csv(csv_path)
    raw["timestamp"] = pd.to_datetime(raw["timestamp"])
    raw = raw.set_index("timestamp").sort_index()

    indicators = Indicators(include_price_emas=False, enable_cache=False)
    enriched = indicators.compute(raw, symbol=symbol, timeframe=timeframe)

    log_close = np.log(enriched["close"])
    panel = enriched[_CANONICAL_INDICATOR_COLS].copy()
    for h in IC_HORIZONS:
        panel[f"fwd_logret_{h}"] = log_close.shift(-h) - log_close

    panel = panel.dropna()
    return SignalPanel(df=panel, symbol=symbol, timeframe=timeframe)
