"""
Seed data for the backtest database.

Called by init_db() on startup — idempotent (skips if row already exists).
"""
from app.repository.backtest.models import Strategy
from app.strategies.loader import STRATEGY_MAP

# Descriptions for DB display (keyed by strategy name)
STRATEGY_DESCRIPTIONS = {
    "rsi_no_retest": "RSI strategy without retest confirmation",
    "rsi_wma_retest": "RSI strategy requiring WMA45 retest",
    "rsi_momentum": "RSI momentum strategy (short entries only)",
}


def seed_strategies(session) -> None:
    """Insert default strategies if they don't already exist."""
    for name, cls in STRATEGY_MAP.items():
        if session.query(Strategy).filter_by(name=name).first() is None:
            default_config = getattr(cls, "DEFAULT_CONFIG", {})
            session.add(
                Strategy(
                    name=name,
                    description=STRATEGY_DESCRIPTIONS.get(name, name),
                    default_config=default_config,
                )
            )
            session.commit()
