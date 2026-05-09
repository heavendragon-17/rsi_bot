"""
UI metadata for strategy parameter schemas.

Each dict maps field_name -> {title, minimum, maximum, ui_group, ui_order, ...}.
These are merged into the auto-generated JSON Schema by SchemaConfigMixin.
"""

# ──────────────────────────────────────────────────────────
# Shared UI group definitions (reused across strategies)
# ──────────────────────────────────────────────────────────

INDICATOR_GROUPS = {
    "indicators": {"title": "Indicators", "icon": "sliders", "order": 1},
    "entry": {"title": "Entry Conditions", "icon": "activity", "order": 2},
    "exit_sl": {"title": "Stop Loss", "icon": "shield", "order": 3},
    "exit_tp": {"title": "Take Profit", "icon": "target", "order": 4},
    "management": {"title": "Trade Management", "icon": "settings", "order": 5},
}


# ──────────────────────────────────────────────────────────
# RSI No Retest
# ──────────────────────────────────────────────────────────

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


# ──────────────────────────────────────────────────────────
# RSI No Retest SHORT (mirror of RSI No Retest, direction flipped)
# ──────────────────────────────────────────────────────────

RSI_NO_RETEST_SHORT_GROUPS = {**INDICATOR_GROUPS}

# Identical to RSI_NO_RETEST_METADATA except:
# - `nr_max_above_ema21` is replaced with `nr_max_below_ema21`
# - `nr_sl_mode` enum lists SHORT-flavored modes (highest_close / highest_wick)
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


# ──────────────────────────────────────────────────────────
# RSI Momentum
# ──────────────────────────────────────────────────────────

RSI_MOMENTUM_GROUPS = {**INDICATOR_GROUPS}

RSI_MOMENTUM_METADATA = {
    # Indicators
    "rsi_period": {
        "title": "RSI Period",
        "minimum": 2, "maximum": 100,
        "ui_group": "indicators", "ui_order": 1,
    },
    "ema_period": {
        "title": "EMA Period",
        "minimum": 2, "maximum": 50,
        "description": "RSI EMA smoothing period",
        "ui_group": "indicators", "ui_order": 2,
    },
    "wma_period": {
        "title": "WMA Period",
        "minimum": 5, "maximum": 100,
        "description": "RSI WMA slow signal period",
        "ui_group": "indicators", "ui_order": 3,
    },
    # Entry
    "spread_threshold": {
        "title": "Spread Threshold",
        "minimum": 0.0, "maximum": 10.0, "ui_step": 0.1,
        "description": "Min WMA45-EMA9 distance for entry",
        "ui_group": "entry", "ui_order": 1,
    },
    "divergence_lookback": {
        "title": "Divergence Lookback",
        "minimum": 5, "maximum": 100,
        "ui_group": "entry", "ui_order": 2,
    },
    "pivot_strength": {
        "title": "Pivot Strength",
        "minimum": 1, "maximum": 20,
        "description": "N-bar pivot for divergence detection",
        "ui_group": "entry", "ui_order": 3,
    },
    "min_candles": {
        "title": "Min Candles (Warmup)",
        "minimum": 20, "maximum": 200,
        "ui_group": "entry", "ui_order": 4, "ui_hidden": True,
    },
    # Stop Loss
    "sl_lookback": {
        "title": "SL Lookback",
        "minimum": 5, "maximum": 100,
        "description": "Highest-high lookback for soft SL",
        "ui_group": "exit_sl", "ui_order": 1,
    },
    "disaster_sl_multiplier": {
        "title": "Disaster SL Multiplier",
        "minimum": 1.0, "maximum": 10.0, "ui_step": 0.5, "ui_suffix": "x",
        "description": "Hard exchange-stop distance vs. soft SL. Ignored when SL Trigger Mode is 'touch'.",
        "ui_group": "exit_sl", "ui_order": 2,
    },
    "sl_trigger_mode": {
        "title": "SL Trigger Mode",
        "enum": ["candle_close", "touch"],
        "description": "candle_close: wait for candle close through soft SL. touch: exchange stop at soft SL fires on touch.",
        "ui_group": "exit_sl", "ui_order": 3,
    },
    # Take Profit
    "tp1_rr": {
        "title": "TP1 R:R",
        "minimum": 0.1, "maximum": 10.0, "ui_step": 0.1, "ui_suffix": "R",
        "ui_group": "exit_tp", "ui_order": 1,
    },
    "tp2_rr": {
        "title": "TP2 R:R",
        "minimum": 0.1, "maximum": 15.0, "ui_step": 0.1, "ui_suffix": "R",
        "ui_group": "exit_tp", "ui_order": 2,
    },
    "tp3_rr": {
        "title": "TP3 R:R",
        "minimum": 0.1, "maximum": 20.0, "ui_step": 0.1, "ui_suffix": "R",
        "ui_group": "exit_tp", "ui_order": 3,
    },
    "tp_count": {
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
    # Management
    "move_sl_rr": {
        "title": "Move SL at R:R",
        "minimum": 0.0, "maximum": 5.0, "ui_step": 0.1, "ui_suffix": "R",
        "ui_group": "management", "ui_order": 1,
    },
    "lock_profit_rr": {
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
        "ui_group": "management", "ui_order": 5,
    },
    "candle_close_slippage_pct": {
        "title": "Candle Close Slippage",
        "minimum": 0.0, "maximum": 1.0, "ui_step": 0.01, "ui_suffix": "%",
        "ui_group": "management", "ui_order": 6,
    },
    # Fees — hidden from UI (use server defaults)
    "taker_fee": {"ui_hidden": True},
    "maker_fee": {"ui_hidden": True},
}


# ──────────────────────────────────────────────────────────
# RSI WMA Retest
# ──────────────────────────────────────────────────────────

RSI_WMA_RETEST_GROUPS = {
    "indicators": {"title": "Indicators", "icon": "sliders", "order": 1},
    "entry": {"title": "Entry Conditions", "icon": "activity", "order": 2},
    "h1_filter": {"title": "H1 Timeframe Filter", "icon": "filter", "order": 3},
    "exit_tp": {"title": "Take Profit (RSI Levels)", "icon": "target", "order": 4},
    "exit_sl": {"title": "Stop Loss", "icon": "shield", "order": 5},
    "management": {"title": "Trade Management", "icon": "settings", "order": 6},
}

RSI_WMA_RETEST_METADATA = {
    # Indicators
    "rsi_period": {
        "title": "RSI Period",
        "minimum": 2, "maximum": 100,
        "ui_group": "indicators", "ui_order": 1,
    },
    "rsi_ema_length": {
        "title": "RSI EMA Length",
        "minimum": 2, "maximum": 50,
        "ui_group": "indicators", "ui_order": 2,
    },
    "rsi_wma_length": {
        "title": "RSI WMA Length",
        "minimum": 5, "maximum": 100,
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
    "wma_retest_distance": {
        "title": "WMA Retest Distance",
        "minimum": 0.0, "maximum": 5.0, "ui_step": 0.1,
        "description": "Max RSI distance for valid WMA45 retest",
        "ui_group": "entry", "ui_order": 1,
    },
    "rsi_floor": {
        "title": "RSI Floor",
        "minimum": 0, "maximum": 100,
        "description": "No close below this RSI level during retest",
        "ui_group": "entry", "ui_order": 2,
    },
    "wma45_min": {
        "title": "WMA45 Min",
        "minimum": 0, "maximum": 100,
        "description": "Class 1 signal minimum WMA45 value",
        "ui_group": "entry", "ui_order": 3,
    },
    "wma45_max": {
        "title": "WMA45 Max",
        "minimum": 0, "maximum": 100,
        "description": "Class 1 signal maximum WMA45 value",
        "ui_group": "entry", "ui_order": 4,
    },
    # H1 Filter
    "check_h1_wma45": {
        "title": "Enable H1 WMA45 Filter",
        "description": "Require H1 WMA45 above threshold",
        "ui_group": "h1_filter", "ui_order": 1,
    },
    "h1_wma45_min": {
        "title": "H1 WMA45 Min",
        "minimum": 0.0, "maximum": 100.0, "ui_step": 1.0,
        "ui_group": "h1_filter", "ui_order": 2,
    },
    # Take Profit (RSI-based)
    "tp1_rsi": {
        "title": "TP1 RSI Level",
        "minimum": 40, "maximum": 100,
        "description": "Close partial at this RSI",
        "ui_group": "exit_tp", "ui_order": 1,
    },
    "tp2_rsi": {
        "title": "TP2 RSI Level",
        "minimum": 50, "maximum": 100,
        "ui_group": "exit_tp", "ui_order": 2,
    },
    "tp3_rsi": {
        "title": "TP3 RSI Level",
        "minimum": 60, "maximum": 100,
        "description": "Close all remaining at this RSI",
        "ui_group": "exit_tp", "ui_order": 3,
    },
    # Stop Loss
    "sl_buffer_pct": {
        "title": "SL Buffer",
        "minimum": 0.0, "maximum": 1.0, "ui_step": 0.001, "ui_suffix": "%",
        "ui_group": "exit_sl", "ui_order": 1,
    },
    "disaster_sl_multiplier": {
        "title": "Disaster SL Multiplier",
        "minimum": 1.0, "maximum": 10.0, "ui_step": 0.5, "ui_suffix": "x",
        "description": "Hard exchange-stop distance vs. soft SL. Ignored when SL Trigger Mode is 'touch'.",
        "ui_group": "exit_sl", "ui_order": 2,
    },
    "sl_trigger_mode": {
        "title": "SL Trigger Mode",
        "enum": ["candle_close", "touch"],
        "description": "candle_close: wait for candle close through soft SL. touch: exchange stop at soft SL fires on touch.",
        "ui_group": "exit_sl", "ui_order": 3,
    },
    "candle_close_slippage_pct": {
        "title": "Candle Close Slippage",
        "minimum": 0.0, "maximum": 1.0, "ui_step": 0.001, "ui_suffix": "%",
        "ui_group": "exit_sl", "ui_order": 4,
    },
    # Management
    "use_active_trades": {
        "title": "Use Active Trades",
        "ui_group": "management", "ui_order": 1,
    },
}
