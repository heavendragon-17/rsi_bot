"""UI metadata for the RSI WMA Retest strategy."""

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
