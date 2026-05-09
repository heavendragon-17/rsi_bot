"""UI metadata for the RSI No Retest family (parent + SHORT mirror + FADE)."""

from app.trading.strategy.utils.param_metadata._groups import INDICATOR_GROUPS

RSI_NO_RETEST_GROUPS = {**INDICATOR_GROUPS}

RSI_NO_RETEST_METADATA = {
    # Indicators
    "rsi_period": {
        "title": "RSI Period",
        "minimum": 2, "maximum": 100,
        "description": "RSI calculation lookback period",
        "ui_group": "indicators", "ui_order": 1,
    },
    "rsi_ema_length": {
        "title": "RSI EMA Length",
        "minimum": 2, "maximum": 50,
        "description": "EMA smoothing on RSI line",
        "ui_group": "indicators", "ui_order": 2,
    },
    "rsi_wma_length": {
        "title": "RSI WMA Length",
        "minimum": 5, "maximum": 100,
        "description": "WMA smoothing on RSI (slow signal)",
        "ui_group": "indicators", "ui_order": 3,
    },
    "price_ema_fast": {
        "title": "Price EMA Fast",
        "minimum": 5, "maximum": 50,
        "ui_group": "indicators", "ui_order": 4,
    },
    "price_ema_slow": {
        "title": "Price EMA Slow",
        "minimum": 50, "maximum": 500,
        "ui_group": "indicators", "ui_order": 5,
    },
    # Entry
    "nr_lookback": {
        "title": "Lookback Period",
        "minimum": 5, "maximum": 100,
        "ui_group": "entry", "ui_order": 1,
    },
    "nr_max_above_ema21": {
        "title": "Max Candles Above EMA21",
        "minimum": 0, "maximum": 10,
        "ui_group": "entry", "ui_order": 2,
    },
    "nr_rsi_spread_min": {
        "title": "Min RSI Spread",
        "minimum": 0.0, "maximum": 10.0, "ui_step": 0.1,
        "ui_group": "entry", "ui_order": 3,
    },
    # Stop Loss
    "nr_sl_mode": {
        "title": "Stop Loss Mode",
        "enum": ["lowest_close", "rsi_ema9", "lowest_wick"],
        "ui_group": "exit_sl", "ui_order": 1,
    },
    "sl_buffer_pct": {
        "title": "SL Buffer",
        "minimum": 0.0, "maximum": 5.0, "ui_step": 0.1, "ui_suffix": "%",
        "ui_group": "exit_sl", "ui_order": 2,
    },
    "disaster_sl_multiplier": {
        "title": "Disaster SL Multiplier",
        "minimum": 1.0, "maximum": 10.0, "ui_step": 0.5, "ui_suffix": "x",
        "description": "Hard exchange-stop distance vs. soft SL. Ignored when SL Trigger Mode is 'touch'.",
        "ui_group": "exit_sl", "ui_order": 3,
    },
    "sl_trigger_mode": {
        "title": "SL Trigger Mode",
        "enum": ["candle_close", "touch"],
        "description": "candle_close: wait for candle close through soft SL. touch: exchange stop at soft SL fires on touch.",
        "ui_group": "exit_sl", "ui_order": 4,
    },
    "candle_close_slippage_pct": {
        "title": "Candle Close Slippage",
        "minimum": 0.0, "maximum": 1.0, "ui_step": 0.01, "ui_suffix": "%",
        "ui_group": "exit_sl", "ui_order": 5,
    },
    # Take Profit
    "nr_tp1_rr": {
        "title": "TP1 R:R",
        "minimum": 0.1, "maximum": 10.0, "ui_step": 0.1, "ui_suffix": "R",
        "ui_group": "exit_tp", "ui_order": 1,
    },
    "nr_tp2_rr": {
        "title": "TP2 R:R",
        "minimum": 0.1, "maximum": 15.0, "ui_step": 0.1, "ui_suffix": "R",
        "ui_group": "exit_tp", "ui_order": 2,
    },
    "nr_tp3_rr": {
        "title": "TP3 R:R",
        "minimum": 0.1, "maximum": 20.0, "ui_step": 0.1, "ui_suffix": "R",
        "ui_group": "exit_tp", "ui_order": 3,
    },
    "nr_tp_count": {
        "title": "Number of TP Levels",
        "minimum": 1, "maximum": 3,
        "ui_group": "exit_tp", "ui_order": 4,
    },
    "tp1_close_pct": {
        "title": "TP1 Close %",
        "minimum": 0.0, "maximum": 1.0, "ui_step": 0.05, "ui_suffix": "%",
        "ui_group": "exit_tp", "ui_order": 5,
    },
    "tp2_close_pct": {
        "title": "TP2 Close %",
        "minimum": 0.0, "maximum": 1.0, "ui_step": 0.05, "ui_suffix": "%",
        "ui_group": "exit_tp", "ui_order": 6,
    },
    "tp3_close_pct": {
        "title": "TP3 Close %",
        "minimum": 0.0, "maximum": 1.0, "ui_step": 0.05, "ui_suffix": "%",
        "ui_group": "exit_tp", "ui_order": 7,
    },
    # Management
    "nr_move_sl_rr": {
        "title": "Move SL at R:R",
        "minimum": 0.0, "maximum": 5.0, "ui_step": 0.1, "ui_suffix": "R",
        "ui_group": "management", "ui_order": 1,
    },
    "nr_lock_profit_rr": {
        "title": "Lock Profit at R:R",
        "minimum": 0.0, "maximum": 5.0, "ui_step": 0.1, "ui_suffix": "R",
        "ui_group": "management", "ui_order": 2,
    },
    "max_holding_enabled": {
        "title": "Max Holding Enabled",
        "description": "Force-close stale positions after Max Holding Bars candles.",
        "ui_group": "management", "ui_order": 3,
    },
    "max_holding_bars": {
        "title": "Max Holding Bars",
        "minimum": 1, "maximum": 1000, "ui_step": 1,
        "description": "Number of candles after which a stale position is force-closed (when enabled).",
        "ui_group": "management", "ui_order": 4,
    },
    "use_active_trades": {
        "title": "Use Active Trades",
        "description": "Track concurrent open positions",
        "ui_group": "management", "ui_order": 5,
    },
}


# RSI No Retest SHORT — mirror of the LONG parent with direction flipped.
# Identical to RSI_NO_RETEST_METADATA aside from:
# - `nr_max_above_ema21` is replaced with `nr_max_below_ema21`
# - `nr_sl_mode` enum lists SHORT-flavored modes (highest_close / highest_wick)
RSI_NO_RETEST_SHORT_GROUPS = {**INDICATOR_GROUPS}

RSI_NO_RETEST_SHORT_METADATA = {
    **{
        k: v
        for k, v in RSI_NO_RETEST_METADATA.items()
        if k not in {"nr_max_above_ema21", "nr_sl_mode"}
    },
    "nr_max_below_ema21": {
        "title": "Max Candles Below EMA21",
        "minimum": 0, "maximum": 10,
        "description": "Tolerance for noise: max candles closing BELOW EMA21 in the lookback window.",
        "ui_group": "entry", "ui_order": 2,
    },
    "nr_sl_mode": {
        "title": "Stop Loss Mode",
        "enum": ["highest_close", "highest_wick"],
        "description": "SHORT SL placement: highest_close uses the max close of lookback; highest_wick uses the max high.",
        "ui_group": "exit_sl", "ui_order": 1,
    },
}


# RSI No Retest FADE — parent's trigger, opposite direction.
# Identical to RSI_NO_RETEST_METADATA aside from `nr_sl_mode`, whose enum lists
# SHORT-flavored modes (highest_close / highest_wick). The trigger is the
# parent's, so `nr_max_above_ema21` STAYS — DO NOT rename to `nr_max_below_ema21`
# like the SHORT mirror does.
RSI_NO_RETEST_FADE_GROUPS = {**INDICATOR_GROUPS}

RSI_NO_RETEST_FADE_METADATA = {
    **{k: v for k, v in RSI_NO_RETEST_METADATA.items() if k != "nr_sl_mode"},
    "nr_sl_mode": {
        "title": "Stop Loss Mode",
        "enum": ["highest_close", "highest_wick"],
        "description": "FADE is a SHORT — SL placement: highest_close uses max close of lookback; highest_wick uses max high.",
        "ui_group": "exit_sl", "ui_order": 1,
    },
}
