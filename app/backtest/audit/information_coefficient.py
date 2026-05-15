"""Information Coefficient (IC) test — does RSI carry usable signal?

Computes the Spearman rank correlation between the indicator (`rsi_14`)
and forward log returns at multiple horizons (`IC_HORIZONS`). Bucket
analysis (decile means) is also returned so callers can inspect the
shape of the signal — a strictly monotonic decile curve is far more
convincing than a single Spearman number, and a non-monotonic curve
with a borderline IC is usually noise.

This module operates on a single `SignalPanel` (one symbol, one
timeframe). For cross-symbol IC analysis, call `run_ic_analysis` once
per symbol and aggregate at the caller. The audit aggregator
(`report.py`) will handle this. We intentionally do NOT push the loop
into this module — keeping it single-panel makes the test composable
and makes parallelism easy at the caller (each symbol is independent).

No-look-ahead: see `signal_panel.py` for the alignment derivation. By
the time this module sees the panel, `(rsi_14[t], fwd_logret_h[t])` is
already correctly paired (today's RSI vs the next h bars' return).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd
import structlog
from scipy import stats

from app.backtest.audit.constants import (
    IC_HORIZONS,
    IC_MIN_ABS,
    MIN_TRADES_FOR_TRADE_LEVEL_IC,
)
from app.backtest.audit.signal_panel import SignalPanel, build_signal_panel
from app.backtest.audit.trade_log import TradeLog
from app.core.actions import SIDE_BUY, SIDE_SELL

logger = structlog.get_logger()

_DECILE_COUNT = 10


@dataclass(frozen=True)
class ICHorizonResult:
    """Per-horizon IC result.

    `decile_means` is always length 10. If `pd.qcut` produced fewer
    than 10 buckets due to RSI ties at decile boundaries, missing
    positions are padded with NaN (rare on real RSI data — a warning
    is logged when this happens).
    """

    horizon: int
    ic: float
    p_value: float
    n_obs: int
    decile_means: list[float]


@dataclass(frozen=True)
class ICResult:
    """Aggregate IC verdict across all tested horizons.

    `passed=True` means at least one horizon shows |IC| >= threshold.
    This is intentionally permissive — a strong signal at any tested
    horizon is evidence of real predictive content. Stricter
    aggregation (e.g., majority of horizons must clear) is a v2 design
    decision.

    `sign_consistency` reports the IC direction at each horizon:
    "positive"/"negative" require |IC| >= threshold, "neutral"
    otherwise. The downstream report aggregator uses this to flag
    direction-vs-strategy mismatches automatically (a strategy
    entering against negative IC will fail downstream even if the IC
    magnitude is large).
    """

    passed: bool
    max_abs_ic: float
    max_abs_horizon: int
    per_horizon: dict[int, ICHorizonResult]
    threshold: float
    n_horizons_significant: int
    sign_consistency: dict[int, str]


def _compute_ic_at_horizon(
    panel_df: pd.DataFrame,
    horizon: int,
) -> ICHorizonResult:
    fwd_col = f"fwd_logret_{horizon}"
    if fwd_col not in panel_df.columns:
        raise KeyError(
            f"SignalPanel is missing column '{fwd_col}'. Expected horizons "
            f"are configured in app.backtest.audit.constants.IC_HORIZONS = "
            f"{IC_HORIZONS}; rebuild the panel via build_signal_panel() so "
            f"the forward-return columns match."
        )

    pair = panel_df[["rsi_14", fwd_col]].dropna()
    rsi = pair["rsi_14"]
    fwd = pair[fwd_col]
    n_obs = int(len(pair))

    ic_raw, p_raw = stats.spearmanr(rsi, fwd)
    ic = float(ic_raw) if not (isinstance(ic_raw, float) and math.isnan(ic_raw)) else float("nan")
    p_value = float(p_raw) if not (isinstance(p_raw, float) and math.isnan(p_raw)) else float("nan")

    decile_labels = pd.qcut(rsi, q=_DECILE_COUNT, labels=False, duplicates="drop")
    decile_groups = fwd.groupby(decile_labels).mean().sort_index()

    decile_means: list[float] = [float("nan")] * _DECILE_COUNT
    for idx, mean_val in decile_groups.items():
        if 0 <= int(idx) < _DECILE_COUNT:
            decile_means[int(idx)] = float(mean_val)

    if len(decile_groups) < _DECILE_COUNT:
        logger.warning(
            "audit_ic_decile_collapse",
            horizon=horizon,
            buckets_produced=int(len(decile_groups)),
            expected=_DECILE_COUNT,
            note="RSI ties at decile boundaries collapsed buckets",
        )

    return ICHorizonResult(
        horizon=horizon,
        ic=ic,
        p_value=p_value,
        n_obs=n_obs,
        decile_means=decile_means,
    )


def run_ic_analysis(
    panel: SignalPanel,
    *,
    horizons: list[int] | None = None,
    threshold: float = IC_MIN_ABS,
) -> ICResult:
    """Run IC analysis on `panel` across `horizons`.

    Returns an `ICResult` with per-horizon detail and an aggregate
    verdict. See `ICResult` for the aggregation semantics.
    """
    horizons = list(horizons) if horizons is not None else list(IC_HORIZONS)

    per_horizon: dict[int, ICHorizonResult] = {}
    for h in horizons:
        per_horizon[h] = _compute_ic_at_horizon(panel.df, h)

    abs_ics = {h: abs(r.ic) for h, r in per_horizon.items() if not math.isnan(r.ic)}
    if abs_ics:
        max_abs_horizon = max(abs_ics, key=abs_ics.__getitem__)
        max_abs_ic = abs_ics[max_abs_horizon]
    else:
        max_abs_horizon = horizons[0]
        max_abs_ic = float("nan")

    n_horizons_significant = sum(1 for v in abs_ics.values() if v >= threshold)
    passed = n_horizons_significant > 0

    sign_consistency: dict[int, str] = {}
    for h, r in per_horizon.items():
        if math.isnan(r.ic) or abs(r.ic) < threshold:
            sign_consistency[h] = "neutral"
        elif r.ic > 0:
            sign_consistency[h] = "positive"
        else:
            sign_consistency[h] = "negative"

    return ICResult(
        passed=passed,
        max_abs_ic=max_abs_ic,
        max_abs_horizon=max_abs_horizon,
        per_horizon=per_horizon,
        threshold=threshold,
        n_horizons_significant=n_horizons_significant,
        sign_consistency=sign_consistency,
    )


# ── Trade-level IC ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TradeLevelICResult:
    """Spearman rank correlation at the strategy's entry bars.

    `sample_type` is either ``"realized"`` (RSI@entry vs ret_pct) or
    ``"fwd"`` (RSI@entry vs fwd_logret_h). `horizon` is None for realized
    and the numeric horizon for fwd.
    """

    symbol: str
    sample_type: str
    ic: float
    p_value: float
    n_trades: int
    horizon: int | None = None


def compute_trade_level_realized_ic(
    *,
    trade_log: TradeLog,
    signal_panel: SignalPanel,
    symbol: str,
    side: str,
) -> TradeLevelICResult | None:
    """Spearman(RSI@entry, ret_pct) on closed trades for ``symbol`` and ``side``.

    For LONG (side=BUY): positive IC means higher RSI at entry produced
    higher realized return — the trigger sorts entries correctly.
    For SHORT (side=SELL): positive IC means higher RSI at entry produced
    higher realized return as SHORT (price fell more from higher-RSI entries).
    In both cases ``ret_pct`` is already direction-aware in the trade log.

    Returns ``None`` when fewer than ``MIN_TRADES_FOR_TRADE_LEVEL_IC``
    trades are available after joining with the signal panel.
    """
    subset = trade_log.df[
        (trade_log.df["symbol"] == symbol) & (trade_log.df["side"] == side)
    ].set_index("entry_time")
    joined = subset.join(signal_panel.df[["rsi_14"]], how="left")
    valid = joined.dropna(subset=["rsi_14", "ret_pct"])

    if len(valid) < MIN_TRADES_FOR_TRADE_LEVEL_IC:
        logger.debug(
            "audit_trade_realized_ic_skipped",
            symbol=symbol, side=side, n_trades=len(valid),
            min_required=MIN_TRADES_FOR_TRADE_LEVEL_IC,
        )
        return None

    ic_raw, p_raw = stats.spearmanr(valid["rsi_14"], valid["ret_pct"])
    return TradeLevelICResult(
        symbol=symbol,
        sample_type="realized",
        ic=float(ic_raw),
        p_value=float(p_raw),
        n_trades=int(len(valid)),
        horizon=None,
    )


def compute_trade_level_fwd_ic(
    *,
    trade_log: TradeLog,
    signal_panel: SignalPanel,
    symbol: str,
    horizon: int = 4,
) -> TradeLevelICResult | None:
    """Spearman(RSI@entry, fwd_logret_h) on the strategy's entry bars.

    Direction-agnostic: measures whether the trigger preserves the bar-level
    IC relationship on the bars it selects, independent of trade outcome.
    All trades for ``symbol`` are included regardless of side.

    Returns ``None`` when fewer than ``MIN_TRADES_FOR_TRADE_LEVEL_IC`` valid
    pairs remain after joining with the signal panel.
    """
    fwd_col = f"fwd_logret_{horizon}"
    subset = trade_log.df[trade_log.df["symbol"] == symbol].set_index("entry_time")
    joined = subset.join(signal_panel.df[["rsi_14", fwd_col]], how="left")
    valid = joined.dropna(subset=["rsi_14", fwd_col])

    if len(valid) < MIN_TRADES_FOR_TRADE_LEVEL_IC:
        logger.debug(
            "audit_trade_fwd_ic_skipped",
            symbol=symbol, horizon=horizon, n_trades=len(valid),
            min_required=MIN_TRADES_FOR_TRADE_LEVEL_IC,
        )
        return None

    ic_raw, p_raw = stats.spearmanr(valid["rsi_14"], valid[fwd_col])
    return TradeLevelICResult(
        symbol=symbol,
        sample_type="fwd",
        ic=float(ic_raw),
        p_value=float(p_raw),
        n_trades=int(len(valid)),
        horizon=horizon,
    )


# ── Multi-symbol runners (called by report.py aggregator) ────────────────────


def run_ic_per_symbol(
    symbols: list[str], timeframe: str
) -> dict[str, ICResult] | None:
    """Build a SignalPanel and run bar-level IC analysis per symbol.

    Skips symbols whose CSV is missing or whose IC run raises. Returns
    ``None`` when no symbol produced a result.
    """
    out: dict[str, ICResult] = {}
    for symbol in symbols:
        try:
            panel = build_signal_panel(symbol, timeframe)
        except FileNotFoundError as exc:
            logger.warning("audit_ic_panel_missing", symbol=symbol, error=str(exc))
            continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("audit_ic_panel_failed", symbol=symbol, error=str(exc))
            continue
        try:
            out[symbol] = run_ic_analysis(panel)
        except Exception as exc:  # noqa: BLE001
            logger.warning("audit_ic_run_failed", symbol=symbol, error=str(exc))
    return out or None


def run_trade_level_ic_per_symbol(
    tl: TradeLog,
    symbols: list[str],
    timeframe: str,
    direction: str,
) -> tuple[dict[str, TradeLevelICResult] | None, dict[str, TradeLevelICResult] | None]:
    """Trade-level realized + fwd IC per symbol.

    ``direction`` is "long" / "short" / "both". Realized IC is skipped for
    "both" (mixing sides is ambiguous). Fwd IC is always computed.
    Returns ``(realized, fwd)``; either dict is ``None`` when empty.
    """
    side = {
        "long": SIDE_BUY,
        "short": SIDE_SELL,
    }.get(direction)  # None for "both" → skip realized IC

    realized_out: dict[str, TradeLevelICResult] = {}
    fwd_out: dict[str, TradeLevelICResult] = {}

    for symbol in symbols:
        try:
            panel = build_signal_panel(symbol, timeframe)
        except FileNotFoundError:
            continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("audit_trade_ic_panel_failed", symbol=symbol, error=str(exc))
            continue

        if side is not None:
            try:
                r = compute_trade_level_realized_ic(
                    trade_log=tl, signal_panel=panel, symbol=symbol, side=side,
                )
                if r is not None:
                    realized_out[symbol] = r
            except Exception as exc:  # noqa: BLE001
                logger.warning("audit_trade_realized_ic_failed", symbol=symbol, error=str(exc))

        try:
            r_fwd = compute_trade_level_fwd_ic(
                trade_log=tl, signal_panel=panel, symbol=symbol,
            )
            if r_fwd is not None:
                fwd_out[symbol] = r_fwd
        except Exception as exc:  # noqa: BLE001
            logger.warning("audit_trade_fwd_ic_failed", symbol=symbol, error=str(exc))

    return (realized_out or None), (fwd_out or None)
