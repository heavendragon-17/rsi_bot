"""
Seed data for the backtest database.

Called by init_db() on startup — idempotent (skips if row already exists).
"""
from app.repository.backtest.models import Strategy

# Default config from docs/DATABASE.md
RSI_NO_RETEST_CONFIG = {
    "rsi_period": 21,
    "rsi_ema_length": 9,
    "rsi_wma_length": 45,
    "price_ema_fast": 21,
    "price_ema_slow": 200,
    "nr_lookback": 30,
    "nr_max_above_ema21": 1,
    "nr_rsi_spread_min": 1.5,
    "nr_sl_mode": "lowest_close",
    "sl_buffer_pct": 0.0,
    "disaster_sl_multiplier": 3.0,
    "nr_tp1_rr": 1.0,
    "nr_tp2_rr": 2.0,
    "nr_tp3_rr": 3.0,
    "tp1_close_pct": 0.50,
    "tp2_close_pct": 0.50,
    "nr_move_sl_rr": 0.5,
    "nr_lock_profit_rr": 0.2,
}


def seed_strategies(session) -> None:
    """Insert default strategies if they don't already exist."""
    if session.query(Strategy).filter_by(name="rsi_no_retest").first() is None:
        session.add(
            Strategy(
                name="rsi_no_retest",
                description="RSI strategy without retest confirmation",
                default_config=RSI_NO_RETEST_CONFIG,
            )
        )
        session.commit()
