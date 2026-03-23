"""
Tests for AppConfig typed configuration (replaces validators.py tests).
"""

import os
import sys
from decimal import Decimal

import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import AppConfig, ExchangeConfig, RiskConfig

# ---------------------------------------------------------------------------
# AppConfig.from_yaml (integration test using actual config.yaml)
# ---------------------------------------------------------------------------


def test_from_yaml_loads_actual_config():
    """AppConfig.from_yaml() must load the real config.yaml without error."""
    cfg = AppConfig.from_yaml("config.yaml")
    assert cfg.exchange.name == "binanceusdm"
    assert cfg.exchange.mode in {"mock", "sim", "paper", "testnet", "live"}
    assert len(cfg.symbols) > 0
    assert cfg.timeframe


# ---------------------------------------------------------------------------
# ExchangeConfig validation
# ---------------------------------------------------------------------------


def test_valid_exchange_config():
    cfg = ExchangeConfig(name="binanceusdm", mode="paper", leverage=10)
    assert cfg.name == "binanceusdm"
    assert cfg.mode == "paper"


def test_invalid_mode_raises():
    with pytest.raises(ValueError, match="Invalid mode"):
        ExchangeConfig(name="binanceusdm", mode="invalid_mode")


def test_invalid_exchange_raises():
    with pytest.raises(ValueError, match="Invalid exchange"):
        ExchangeConfig(name="unsupported_exchange", mode="paper")


def test_all_valid_modes():
    for mode in ("mock", "sim", "paper", "testnet", "live"):
        cfg = ExchangeConfig(name="binanceusdm", mode=mode)
        assert cfg.mode == mode


def test_all_valid_exchanges():
    for exchange in ("binanceusdm", "binance", "hyperliquid", "lighter"):
        cfg = ExchangeConfig(name=exchange, mode="mock")
        assert cfg.name == exchange


# ---------------------------------------------------------------------------
# RiskConfig validation
# ---------------------------------------------------------------------------


def test_valid_risk_config():
    cfg = RiskConfig(risk_per_trade_pct=Decimal("0.02"), leverage=10)
    assert cfg.risk_per_trade_pct == Decimal("0.02")


def test_risk_pct_too_high_raises():
    with pytest.raises(ValueError, match="risk_per_trade_pct"):
        RiskConfig(risk_per_trade_pct=Decimal("0.5"))  # 50% — above 10% max


def test_risk_pct_zero_raises():
    with pytest.raises(ValueError, match="risk_per_trade_pct"):
        RiskConfig(risk_per_trade_pct=Decimal("0"))


def test_leverage_out_of_range_raises():
    with pytest.raises(ValueError, match="leverage"):
        RiskConfig(leverage=200)


# ---------------------------------------------------------------------------
# AppConfig to_legacy_dict roundtrip
# ---------------------------------------------------------------------------


def test_to_legacy_dict_structure():
    cfg = AppConfig.from_yaml("config.yaml")
    d = cfg.to_legacy_dict()

    assert "bot" in d
    assert "exchange" in d
    assert "risk" in d
    assert "symbols" in d
    assert "strategy" in d
    assert "timeframe" in d
    assert "backtest" in d
    assert "sim" in d


def test_to_legacy_dict_mode_preserved():
    cfg = AppConfig.from_yaml("config.yaml")
    d = cfg.to_legacy_dict()
    assert d["bot"]["mode"] == cfg.exchange.mode


def test_to_legacy_dict_symbols_preserved():
    cfg = AppConfig.from_yaml("config.yaml")
    d = cfg.to_legacy_dict()
    assert d["symbols"] == list(cfg.symbols)


def test_to_legacy_dict_risk_keys():
    cfg = AppConfig.from_yaml("config.yaml")
    d = cfg.to_legacy_dict()
    risk = d["risk"]
    assert "risk_per_trade_pct" in risk
    assert "leverage" in risk
    assert "max_position_size_pct" in risk
