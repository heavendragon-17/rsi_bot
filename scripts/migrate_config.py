"""
One-time migration: validate old config.yaml against new AppConfig schema.
Usage: python scripts/migrate_config.py [config.yaml]

This script checks that your config.yaml is valid under the new typed config
and prints the canonical AppConfig representation for review.
"""
from __future__ import annotations

import sys
import os

# Allow running from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import AppConfig


def migrate(path: str = "config.yaml") -> None:
    print(f"Validating config: {path}")
    try:
        cfg = AppConfig.from_yaml(path)
    except FileNotFoundError:
        print(f"ERROR: File not found: {path}")
        sys.exit(1)
    except ValueError as e:
        print(f"ERROR: Invalid config — {e}")
        sys.exit(1)

    print("Config loaded successfully.")
    print(f"  exchange.name  = {cfg.exchange.name}")
    print(f"  exchange.mode  = {cfg.exchange.mode}")
    print(f"  exchange.leverage = {cfg.exchange.leverage}x")
    print(f"  symbols        = {cfg.symbols}")
    print(f"  timeframe      = {cfg.timeframe}")
    print(f"  strategy       = {cfg.strategy_name}")
    print(f"  risk_per_trade = {float(cfg.risk.risk_per_trade_pct) * 100:.1f}%")
    print(f"  initial_balance= {cfg.backtest.initial_balance}")

    print("\nLegacy dict (what downstream constructors receive):")
    import json

    legacy = cfg.to_legacy_dict()
    # Convert Decimal values for JSON serialization
    print(json.dumps(legacy, indent=2, default=str))


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    migrate(path)
