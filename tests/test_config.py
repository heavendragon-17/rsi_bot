"""
Tests for typed AppConfig (app/core/config.py).

Verifies:
- Valid configs construct without errors
- Invalid values raise ValueError at construction time (not silently)
- Frozen dataclasses are immutable
- to_legacy_dict() round-trips the key fields
"""
import pytest
from decimal import Decimal
from app.core.config import AppConfig, ExchangeConfig, RiskConfig


class TestExchangeConfig:
    def test_valid_modes(self):
        for mode in ("mock", "sim", "paper", "testnet", "live"):
            cfg = ExchangeConfig(name="binanceusdm", mode=mode)
            assert cfg.mode == mode

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="Invalid mode"):
            ExchangeConfig(mode="unknown")

    def test_invalid_exchange_name_raises(self):
        with pytest.raises(ValueError, match="Invalid exchange"):
            ExchangeConfig(name="bitfinex", mode="mock")

    def test_frozen(self):
        cfg = ExchangeConfig()
        with pytest.raises(Exception):  # FrozenInstanceError
            cfg.mode = "live"  # type: ignore[misc]


class TestRiskConfig:
    def test_valid_risk_config(self):
        cfg = RiskConfig(risk_per_trade_pct=Decimal("0.02"), leverage=10)
        assert cfg.leverage == 10

    def test_zero_risk_raises(self):
        with pytest.raises(ValueError, match="risk_per_trade_pct"):
            RiskConfig(risk_per_trade_pct=Decimal("0"))

    def test_risk_above_10pct_raises(self):
        with pytest.raises(ValueError, match="risk_per_trade_pct"):
            RiskConfig(risk_per_trade_pct=Decimal("0.11"))

    def test_leverage_out_of_range_raises(self):
        with pytest.raises(ValueError, match="leverage"):
            RiskConfig(leverage=0)
        with pytest.raises(ValueError, match="leverage"):
            RiskConfig(leverage=126)


class TestAppConfig:
    def test_default_construction(self):
        cfg = AppConfig()
        assert cfg.exchange.mode == "mock"
        assert cfg.exchange.name == "binanceusdm"
        assert cfg.risk.risk_per_trade_pct == Decimal("0.02")

    def test_to_legacy_dict_round_trip(self):
        cfg = AppConfig()
        d = cfg.to_legacy_dict()
        assert d["bot"]["mode"] == cfg.exchange.mode
        assert d["exchange"]["name"] == cfg.exchange.name
        assert d["risk"]["leverage"] == cfg.risk.leverage
        assert "risk" in d
        assert "symbols" in d

    def test_custom_symbols(self):
        cfg = AppConfig(symbols=["ETH/USDT", "BTC/USDT"])
        assert "ETH/USDT" in cfg.symbols

    def test_frozen(self):
        cfg = AppConfig()
        with pytest.raises(Exception):
            cfg.strategy_name = "other"  # type: ignore[misc]

    def test_loads_without_legacy_dict(self):
        """AppConfig fields are accessible directly, no to_legacy_dict needed."""
        cfg = AppConfig()
        assert cfg.exchange.mode == "mock"
        assert cfg.risk.risk_per_trade_pct == Decimal("0.02")
        assert isinstance(cfg.symbols, list)
        assert cfg.strategy_name is not None


class TestConstants:
    """Verify constants.py values match expected defaults (M15 coverage)."""

    def test_warmup_value(self):
        from app.core.constants import WARMUP
        assert WARMUP == 220

    def test_fee_defaults(self):
        from app.core.constants import DEFAULT_TAKER_FEE, DEFAULT_MAKER_FEE
        assert DEFAULT_TAKER_FEE == 0.0005
        assert DEFAULT_MAKER_FEE == 0.0002

    def test_decimal_fee_variants(self):
        from app.core.constants import DEFAULT_TAKER_FEE_DECIMAL, DEFAULT_MAKER_FEE_DECIMAL
        assert DEFAULT_TAKER_FEE_DECIMAL == Decimal("0.0005")
        assert DEFAULT_MAKER_FEE_DECIMAL == Decimal("0.0002")

    def test_max_candles_in_ram(self):
        from app.core.constants import MAX_CANDLES_IN_RAM
        assert MAX_CANDLES_IN_RAM == 6000
