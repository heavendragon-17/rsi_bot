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


def _build_defaults(cls) -> dict:
    """Extract field defaults from a strategy's CONFIG_CLASS (or DEFAULT_CONFIG)."""
    config_cls = getattr(cls, "CONFIG_CLASS", None)
    if config_cls:
        return {
            f.name: f.default
            for f in dataclasses.fields(config_cls)
            if f.default is not dataclasses.MISSING
            and f.name not in ("METADATA", "UI_GROUPS")
        }
    return dict(getattr(cls, "DEFAULT_CONFIG", {}))


def seed_strategies(session) -> None:
    """Insert default strategies if they don't already exist.

    For existing rows, backfill any new dataclass fields into ``default_config``
    so freshly added params (e.g. ``max_holding_bars``) appear in the UI without
    requiring a DB wipe. Existing user values are preserved.
    """
    from app.trading.strategy.loader import STRATEGY_MAP

    for name, cls in STRATEGY_MAP.items():
        defaults = _build_defaults(cls)
        existing = session.query(Strategy).filter_by(name=name).first()

        if existing is None:
            session.add(
                Strategy(
                    name=name,
                    description=STRATEGY_DESCRIPTIONS.get(name, name),
                    default_config=defaults,
                )
            )
            session.commit()
            continue

        current = dict(existing.default_config) if existing.default_config else {}
        missing = {k: v for k, v in defaults.items() if k not in current}
        if missing:
            current.update(missing)
            existing.default_config = current
            session.commit()
