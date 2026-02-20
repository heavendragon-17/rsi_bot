"""
Typed configuration with dataclasses.
Single source of truth for defaults and validation.

Usage:
    from app.core.config import AppConfig
    config = AppConfig.from_yaml("config.yaml")
    legacy = config.to_legacy_dict()  # backward-compat for constructors not yet updated
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from decimal import Decimal
from typing import Any, Dict, List

import yaml


@dataclass(frozen=True)
class ExchangeConfig:
    """Exchange connection settings."""

    name: str = "binanceusdm"
    mode: str = "mock"  # mock | sim | paper | testnet | live
    leverage: int = 10
    margin_type: str = "ISOLATED"

    def __post_init__(self):
        valid_modes = {"mock", "sim", "paper", "testnet", "live"}
        if self.mode not in valid_modes:
            raise ValueError(
                f"Invalid mode '{self.mode}'. Must be one of {sorted(valid_modes)}"
            )
        valid_exchanges = {"binanceusdm", "binance", "hyperliquid", "lighter"}
        if self.name not in valid_exchanges:
            raise ValueError(
                f"Invalid exchange '{self.name}'. Must be one of {sorted(valid_exchanges)}"
            )


@dataclass(frozen=True)
class RiskConfig:
    """Risk management parameters."""

    risk_per_trade_pct: Decimal = Decimal("0.02")
    max_position_size_pct: Decimal = Decimal("0.99")
    leverage: int = 10
    use_initial_capital_for_risk: bool = False
    use_risk_based_sizing: bool = True
    tp1_close_pct: Decimal = Decimal("0.33")
    tp2_close_pct: Decimal = Decimal("0.50")
    min_sl_distance_pct: Decimal = Decimal("0.003")

    def __post_init__(self):
        if not (Decimal("0") < self.risk_per_trade_pct <= Decimal("0.1")):
            raise ValueError(
                f"risk_per_trade_pct must be between 0 and 10%, got {self.risk_per_trade_pct}"
            )
        if self.leverage < 1 or self.leverage > 125:
            raise ValueError(f"leverage must be 1-125, got {self.leverage}")


@dataclass(frozen=True)
class NotificationConfig:
    """Optional service flags + settings."""

    telegram_enabled: bool = True


@dataclass(frozen=True)
class BacktestConfig:
    """Backtest-specific settings."""

    initial_balance: Decimal = Decimal("10000")


@dataclass(frozen=True)
class PaperSimConfig:
    """Local simulation settings (PaperExchange / sim mode)."""

    initial_balance: Decimal = Decimal("10000")
    tick_sample_interval_ms: int = 500


@dataclass(frozen=True)
class AppConfig:
    """
    Top-level application config.
    Loaded once at startup from config.yaml.
    Passed to constructors (not a global singleton).
    """

    exchange: ExchangeConfig = field(default_factory=ExchangeConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    paper_sim: PaperSimConfig = field(default_factory=PaperSimConfig)
    symbols: List[str] = field(default_factory=lambda: ["BTC/USDT"])
    strategy_name: str = "rsi_no_retest"
    strategy_params: Dict[str, Any] = field(default_factory=dict)
    timeframe: str = "5m"
    warmup_candles: int = 200
    debug: bool = False

    @classmethod
    def from_yaml(cls, path: str = "config.yaml") -> "AppConfig":
        """Load config from YAML file. Validates on construction via __post_init__."""
        with open(path) as f:
            raw = yaml.safe_load(f) or {}

        bot = raw.get("bot", {})
        exchange_raw = raw.get("exchange", {})
        risk_raw = raw.get("risk", {})
        backtest_raw = raw.get("backtest", {})
        paper_sim_raw = raw.get("paper_sim", {})

        return cls(
            exchange=ExchangeConfig(
                name=exchange_raw.get("name", "binanceusdm"),
                mode=bot.get("mode", "mock"),
                leverage=int(risk_raw.get("leverage", 10)),
                margin_type=exchange_raw.get("margin_type", "ISOLATED"),
            ),
            risk=RiskConfig(
                risk_per_trade_pct=Decimal(str(risk_raw.get("risk_per_trade_pct", "0.02"))),
                max_position_size_pct=Decimal(str(risk_raw.get("max_position_size_pct", "0.99"))),
                leverage=int(risk_raw.get("leverage", 10)),
                use_initial_capital_for_risk=bool(
                    risk_raw.get("use_initial_capital_for_risk", False)
                ),
                use_risk_based_sizing=bool(risk_raw.get("use_risk_based_sizing", True)),
                tp1_close_pct=Decimal(str(risk_raw.get("tp1_close_pct", "0.33"))),
                tp2_close_pct=Decimal(str(risk_raw.get("tp2_close_pct", "0.50"))),
                min_sl_distance_pct=Decimal(str(risk_raw.get("min_sl_distance_pct", "0.003"))),
            ),
            notification=NotificationConfig(
                telegram_enabled=bool(bot.get("telegram_enabled", True)),
            ),
            backtest=BacktestConfig(
                initial_balance=Decimal(str(backtest_raw.get("initial_balance", "10000"))),
            ),
            paper_sim=PaperSimConfig(
                initial_balance=Decimal(str(paper_sim_raw.get("initial_balance", "10000"))),
                tick_sample_interval_ms=int(
                    paper_sim_raw.get("tick_sample_interval_ms", 500)
                ),
            ),
            symbols=raw.get("symbols", ["BTC/USDT"]),
            strategy_name=raw.get("strategy", "rsi_no_retest"),
            strategy_params=raw.get("strategy_params", {}) or {},
            timeframe=raw.get("timeframe", "5m"),
            warmup_candles=int(raw.get("warmup_candles", 200)),
            debug=bool(bot.get("debug", False)),
        )

    def to_legacy_dict(self) -> dict:
        """
        Convert to the raw dict format expected by existing constructors.
        Allows incremental migration — new code reads AppConfig directly,
        old code receives this dict until updated.
        """
        return {
            "bot": {
                "mode": self.exchange.mode,
                "debug": self.debug,
                "active": True,
            },
            "exchange": {
                "name": self.exchange.name,
                "margin_type": self.exchange.margin_type,
            },
            "risk": {
                "risk_per_trade_pct": float(self.risk.risk_per_trade_pct),
                "max_position_size_pct": float(self.risk.max_position_size_pct),
                "leverage": self.risk.leverage,
                "use_initial_capital_for_risk": self.risk.use_initial_capital_for_risk,
                "use_risk_based_sizing": self.risk.use_risk_based_sizing,
                "tp1_close_pct": float(self.risk.tp1_close_pct),
                "tp2_close_pct": float(self.risk.tp2_close_pct),
                "min_sl_distance_pct": float(self.risk.min_sl_distance_pct),
            },
            "symbols": list(self.symbols),
            "strategy": self.strategy_name,
            "strategy_params": dict(self.strategy_params),
            "timeframe": self.timeframe,
            "warmup_candles": self.warmup_candles,
            "backtest": {
                "initial_balance": float(self.backtest.initial_balance),
            },
            "paper_sim": {
                "initial_balance": float(self.paper_sim.initial_balance),
                "tick_sample_interval_ms": self.paper_sim.tick_sample_interval_ms,
            },
        }
