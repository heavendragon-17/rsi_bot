"""Regression tests for the post-trade-review fixes on RsiMomentumStrategy.

Each test targets one of the four issues identified in the April 2026
short-strategy review (see docs/13_runbooks_and_postmortems/
short-strategy-2026-04.md):

  1. EMA200 trend filter  -> block entries while close >= EMA200.
  2. Crossover freshness  -> drop a stale EMA9<WMA45 crossover signal after
     ``max_candles_since_crossover`` candles of no entry.
  3. Stale-trade exit     -> force close after N candles with no TP1 hit.
  4. BE-lock defaults     -> move_sl_rr=1.0 / lock_profit_rr=0.5 (not the
     previous 0.5 / 0.2) to reduce immediate BE sweeps.
"""

from decimal import Decimal

import pandas as pd

from app.core.actions import (
    EXIT_STALE_TRADE,
    ClosePosition,
    DoNothing,
    MoveSL,
    OpenPosition,
)
from app.core.context import SCANNING
from app.core.snapshots import ContextSnapshot, PositionSnapshot
from app.trading.strategy.rsi_momentum import RsiMomentumConfig, RsiMomentumStrategy


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — mostly mirroring tests/test_rsi_momentum.py but with the new
# filters selectively enabled per test.
# ─────────────────────────────────────────────────────────────────────────────


def _make_strategy(**strategy_params) -> RsiMomentumStrategy:
    """Build a strategy with short warm-up and the filters the test wants."""
    base = {"min_candles": 75}
    base.update(strategy_params)
    return RsiMomentumStrategy({"strategy_params": base})


def _bearish_divergence_df(n: int = 80) -> pd.DataFrame:
    """Two-pivot bearish divergence, copied from test_rsi_momentum.py."""
    ts = pd.date_range("2024-01-01", periods=n, freq="15min")
    closes = [100.0] * n
    highs = [100.5] * n
    rsis = [45.0] * n

    N = 5
    pa = n - 25
    highs[pa] = 110.0
    rsis[pa] = 70.0
    for i in range(pa - N, pa):
        highs[i] = 99.0
    for i in range(pa + 1, pa + N + 1):
        highs[i] = 99.0

    pb = n - 12
    highs[pb] = 115.0
    rsis[pb] = 65.0
    for i in range(pb - N, pb):
        highs[i] = 99.0
    for i in range(pb + 1, min(pb + N + 1, n)):
        highs[i] = 99.0

    df = pd.DataFrame(
        {
            "open": closes,
            "high": highs,
            "low": [c * 0.999 for c in closes],
            "close": closes,
            "volume": 1000.0,
            "closed": True,
            "rsi_14": rsis,
            "rsi_ema9": 45.0,
            "rsi_wma45": 50.0,
            "ema200": 100.0,
        },
        index=ts,
    )
    return df


def _short_signal_df(n: int = 80, ema200_level: float | None = None) -> pd.DataFrame:
    """Dataframe where S1-S5 are satisfied. ema200 column is injected so the
    S6 filter can pass (close=100 < ema200_level)."""
    df = _bearish_divergence_df(n=n)
    spread = 5.0
    df["rsi_14"] = 40.0
    df["rsi_ema9"] = 45.0
    df["rsi_wma45"] = 45.0 + spread
    df.iloc[n - 25, df.columns.get_loc("rsi_14")] = 70.0
    df.iloc[n - 12, df.columns.get_loc("rsi_14")] = 65.0
    df.iloc[-2, df.columns.get_loc("rsi_ema9")] = 55.0
    df.iloc[-2, df.columns.get_loc("rsi_wma45")] = 55.0 - spread
    if ema200_level is not None:
        df["ema200"] = ema200_level
    return df


def _analyze(strategy, df, context=None):
    strategy.indicators.compute = lambda d, **kw: df
    return strategy.analyze(
        "BTC/USDT",
        df,
        position=None,
        context=context or ContextSnapshot(state=SCANNING),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. EMA200 trend filter
# ─────────────────────────────────────────────────────────────────────────────


def test_ema200_filter_blocks_short_in_uptrend():
    """close=100 with EMA200=90 (uptrend) → S6 blocks, DoNothing returned."""
    strategy = _make_strategy(ema200_filter=True, max_candles_since_crossover=0)
    df = _short_signal_df(ema200_level=90.0)
    result = _analyze(strategy, df)
    assert isinstance(result.actions[0], DoNothing)


def test_ema200_filter_allows_short_in_downtrend():
    """close=100 with EMA200=110 (downtrend) → S6 passes, OpenPosition SELL."""
    strategy = _make_strategy(ema200_filter=True, max_candles_since_crossover=0)
    df = _short_signal_df(ema200_level=110.0)
    result = _analyze(strategy, df)
    assert isinstance(result.actions[0], OpenPosition)
    assert result.actions[0].side == "SELL"


def test_ema200_filter_off_preserves_legacy_behaviour():
    """With the filter disabled, the entry should fire regardless of EMA200."""
    strategy = _make_strategy(ema200_filter=False, max_candles_since_crossover=0)
    df = _short_signal_df(ema200_level=90.0)  # would block if filter on
    result = _analyze(strategy, df)
    assert isinstance(result.actions[0], OpenPosition)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Crossover freshness cap
# ─────────────────────────────────────────────────────────────────────────────


def test_crossover_expires_after_max_candles():
    """With max=1, a crossover from >1 candle ago must not fire an entry."""
    strategy = _make_strategy(
        ema200_filter=False,
        max_candles_since_crossover=1,
    )
    df = _short_signal_df()
    # No crossover on the final candles (rows -1 and -2 both have the same
    # ema9/wma45 values injected above, so a new crossover will NOT be
    # detected). We fake a stale crossover via the persisted context.
    df.iloc[-2, df.columns.get_loc("rsi_ema9")] = 45.0
    df.iloc[-2, df.columns.get_loc("rsi_wma45")] = 50.0
    ctx = ContextSnapshot(
        state=SCANNING,
        meta={"crossover_detected": True, "candles_since_crossover": 5},
    )
    result = _analyze(strategy, df, context=ctx)
    assert isinstance(result.actions[0], DoNothing)
    # Freshness bookkeeping was reset once the signal was dropped.
    assert result.new_context.meta.get("crossover_detected") is False
    assert result.new_context.meta.get("candles_since_crossover") == 0


def test_crossover_still_valid_inside_window():
    """max=5 and a 2-candle-old crossover → entry still fires."""
    strategy = _make_strategy(
        ema200_filter=False,
        max_candles_since_crossover=5,
    )
    df = _short_signal_df()
    # No *new* crossover on this candle — rely on persistence.
    df.iloc[-2, df.columns.get_loc("rsi_ema9")] = 45.0
    df.iloc[-2, df.columns.get_loc("rsi_wma45")] = 50.0
    ctx = ContextSnapshot(
        state=SCANNING,
        meta={"crossover_detected": True, "candles_since_crossover": 2},
    )
    result = _analyze(strategy, df, context=ctx)
    assert isinstance(result.actions[0], OpenPosition)


def test_crossover_max_zero_disables_cap():
    """max=0 means unlimited persistence (pre-fix behaviour)."""
    strategy = _make_strategy(
        ema200_filter=False,
        max_candles_since_crossover=0,
    )
    df = _short_signal_df()
    df.iloc[-2, df.columns.get_loc("rsi_ema9")] = 45.0
    df.iloc[-2, df.columns.get_loc("rsi_wma45")] = 50.0
    ctx = ContextSnapshot(
        state=SCANNING,
        meta={"crossover_detected": True, "candles_since_crossover": 50},
    )
    result = _analyze(strategy, df, context=ctx)
    assert isinstance(result.actions[0], OpenPosition)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Stale-trade exit
# ─────────────────────────────────────────────────────────────────────────────


def _exit_df(close_price: float, low: float = 99.0, high: float = 101.0, n: int = 80) -> pd.DataFrame:
    ts = pd.date_range("2024-01-01", periods=n, freq="15min")
    df = pd.DataFrame(
        {
            "open": 100.0,
            "high": high,
            "low": low,
            "close": close_price,
            "volume": 1000.0,
            "closed": True,
            "rsi_14": 45.0,
            "rsi_ema9": 45.0,
            "rsi_wma45": 50.0,
            "ema200": 110.0,
        },
        index=ts,
    )
    return df


def _open_position() -> PositionSnapshot:
    return PositionSnapshot(
        has_position=True,
        symbol="BTC/USDT",
        side="SELL",
        entry_price=Decimal("100"),
        current_sl=Decimal("105"),
    )


def _exit_ctx(candles_in_trade: int = 0) -> ContextSnapshot:
    return ContextSnapshot(
        state=SCANNING,
        soft_sl_price=Decimal("105"),
        meta={
            "entry_price": Decimal("100"),
            "sl_price": Decimal("105"),
            "soft_sl_price": Decimal("105"),
            "original_soft_sl": Decimal("105"),
            "moved_sl_to_entry": False,
            "pending_candle_sl": False,
            "candles_in_trade": candles_in_trade,
        },
    )


def test_stale_exit_fires_after_threshold():
    """After stale_exit_candles=3 candles with no TP, emit ClosePosition(STALE_TRADE)."""
    strategy = _make_strategy(stale_exit_candles=3, move_sl_rr=1.0, lock_profit_rr=0.5)
    df = _exit_df(close_price=99.5)  # small adverse/neutral move, no MoveSL trigger
    position = _open_position()
    # 3rd call into manage_exit → candles_in_trade becomes 3 → threshold hit.
    ctx = _exit_ctx(candles_in_trade=2)
    strategy.indicators.compute = lambda d, **kw: df
    result = strategy.analyze("BTC/USDT", df, position=position, context=ctx)
    closes = [a for a in result.actions if isinstance(a, ClosePosition)]
    assert closes, "Expected a ClosePosition action once the trade is stale"
    assert closes[0].reason == EXIT_STALE_TRADE


def test_stale_exit_does_not_fire_before_threshold():
    """candles_in_trade below threshold → no stale close emitted."""
    strategy = _make_strategy(stale_exit_candles=5, move_sl_rr=1.0, lock_profit_rr=0.5)
    df = _exit_df(close_price=99.5)
    position = _open_position()
    ctx = _exit_ctx(candles_in_trade=1)  # will become 2 → still < 5
    strategy.indicators.compute = lambda d, **kw: df
    result = strategy.analyze("BTC/USDT", df, position=position, context=ctx)
    assert not any(isinstance(a, ClosePosition) for a in result.actions)
    # Counter was incremented and persisted.
    assert result.new_context.meta.get("candles_in_trade") == 2


def test_stale_exit_zero_disables_rule():
    """stale_exit_candles=0 means the rule never fires."""
    strategy = _make_strategy(stale_exit_candles=0, move_sl_rr=1.0, lock_profit_rr=0.5)
    df = _exit_df(close_price=99.5)
    position = _open_position()
    ctx = _exit_ctx(candles_in_trade=1000)
    strategy.indicators.compute = lambda d, **kw: df
    result = strategy.analyze("BTC/USDT", df, position=position, context=ctx)
    assert not any(isinstance(a, ClosePosition) for a in result.actions)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Loosened BE-lock defaults
# ─────────────────────────────────────────────────────────────────────────────


def test_default_be_lock_values_loosened():
    """Post-review defaults: trigger at -1R, park SL at -0.5R."""
    cfg = RsiMomentumConfig()
    assert cfg.move_sl_rr == 1.0
    assert cfg.lock_profit_rr == 0.5


def test_default_be_lock_does_not_trigger_at_half_r():
    """With defaults, a -0.5R drop must NOT yet trigger the SL move."""
    strategy = _make_strategy(ema200_filter=False)
    # entry=100, soft_sl=105 → 1R=5. -0.5R ≈ 97.5 (ignoring fees).
    df = _exit_df(close_price=98.0, low=97.5, high=100.5)
    position = _open_position()
    ctx = _exit_ctx()
    strategy.indicators.compute = lambda d, **kw: df
    result = strategy.analyze("BTC/USDT", df, position=position, context=ctx)
    assert not any(isinstance(a, MoveSL) for a in result.actions)


def test_default_be_lock_triggers_at_one_r():
    """With defaults, a -1R drop triggers the SL move to lock-profit."""
    strategy = _make_strategy(ema200_filter=False)
    df = _exit_df(close_price=95.0, low=94.0, high=100.5)
    position = _open_position()
    ctx = _exit_ctx()
    strategy.indicators.compute = lambda d, **kw: df
    result = strategy.analyze("BTC/USDT", df, position=position, context=ctx)
    moves = [a for a in result.actions if isinstance(a, MoveSL)]
    assert moves, "A -1R drop should trigger MoveSL under the new defaults"
