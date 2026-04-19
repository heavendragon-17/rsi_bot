"""
Seed data for the backtest database.

Called by init_db() on startup — idempotent (skips if row already exists).
"""

import dataclasses

from app.repository.backtest.models import Strategy

# Descriptions for DB display (keyed by strategy name)
STRATEGY_DESCRIPTIONS = {
    "rsi_no_retest": "RSI strategy without retest confirmation",
    "rsi_wma_retest": "RSI strategy requiring WMA45 retest",
    "rsi_momentum": "RSI momentum strategy (short entries only)",
}


def seed_strategies(session) -> None:
    """Insert default strategies if they don't already exist."""
    from app.trading.strategy.loader import STRATEGY_MAP

    for name, cls in STRATEGY_MAP.items():
        if session.query(Strategy).filter_by(name=name).first() is None:
            config_cls = getattr(cls, "CONFIG_CLASS", None)
            if config_cls:
                defaults = {
                    f.name: f.default
                    for f in dataclasses.fields(config_cls)
                    if f.default is not dataclasses.MISSING
                    and f.name not in ("METADATA", "UI_GROUPS")
                }
            else:
                defaults = getattr(cls, "DEFAULT_CONFIG", {})

            session.add(
                Strategy(
                    name=name,
                    description=STRATEGY_DESCRIPTIONS.get(name, name),
                    default_config=defaults,
                )
            )
            session.commit()
