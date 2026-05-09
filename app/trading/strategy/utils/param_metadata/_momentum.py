"""UI metadata for the RSI Momentum strategy."""

from app.trading.strategy.utils.param_metadata._groups import INDICATOR_GROUPS

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
