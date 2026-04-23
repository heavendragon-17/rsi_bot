"""Tests for app/signal/strategy_config.py — the signal-mode config resolver."""

from decimal import Decimal

import pytest

from app.core.config import RiskConfig
from app.signal.strategy_config import (
    StrategyInstanceConfig,
    resolve_strategy_configs,
)


def _base_raw(**overrides):
    """Build a minimally valid signal-mode config dict."""
    raw = {
        "bot": {"mode": "signal"},
        "telegram": {"group_id": -100, "debug_topic_id": 99},
        "timeframe": "15m",
        "symbols": ["BTC/USDT", "ETH/USDT"],
        "risk": {
            "risk_per_trade_pct": 0.002,
            "max_position_size_pct": 0.99,
            "leverage": 10,
            "tp1_close_pct": 1,
            "tp2_close_pct": 0,
            "min_sl_distance_pct": 0.003,
        },
        "strategies": [
            {"name": "rsi_no_retest", "active": True, "telegram_topic_id": 42},
        ],
    }
    raw.update(overrides)
    return raw


class TestHappyPath:
    def test_resolves_single_active_strategy(self):
        out = resolve_strategy_configs(_base_raw())
        assert len(out) == 1
        cfg = out[0]
        assert isinstance(cfg, StrategyInstanceConfig)
        assert cfg.name == "rsi_no_retest"
        assert cfg.telegram_topic_id == 42
        assert cfg.symbols == ("BTC/USDT", "ETH/USDT")
        assert cfg.timeframe == "15m"
        assert isinstance(cfg.risk, RiskConfig)
        assert cfg.risk.risk_per_trade_pct == Decimal("0.002")

    def test_inactive_strategies_skipped(self):
        raw = _base_raw()
        raw["strategies"] = [
            {"name": "rsi_no_retest", "active": False, "telegram_topic_id": 42},
            {"name": "rsi_wma_retest", "active": True, "telegram_topic_id": 43},
        ]
        out = resolve_strategy_configs(raw)
        assert [c.name for c in out] == ["rsi_wma_retest"]

    def test_missing_active_key_defaults_to_true(self):
        raw = _base_raw()
        raw["strategies"] = [
            {"name": "rsi_no_retest", "telegram_topic_id": 42},
        ]
        out = resolve_strategy_configs(raw)
        assert len(out) == 1

    def test_no_active_strategies_returns_empty_list(self):
        raw = _base_raw()
        raw["strategies"] = [
            {"name": "rsi_no_retest", "active": False, "telegram_topic_id": 42},
        ]
        assert resolve_strategy_configs(raw) == []

    def test_empty_strategies_list_returns_empty(self):
        raw = _base_raw()
        raw["strategies"] = []
        assert resolve_strategy_configs(raw) == []


class TestOverrides:
    def test_strategy_overrides_symbols(self):
        raw = _base_raw()
        raw["strategies"] = [
            {"name": "rsi_no_retest", "telegram_topic_id": 42, "symbols": ["SOL/USDT"]},
        ]
        out = resolve_strategy_configs(raw)
        assert out[0].symbols == ("SOL/USDT",)

    def test_strategy_overrides_timeframe(self):
        raw = _base_raw()
        raw["strategies"] = [
            {"name": "rsi_no_retest", "telegram_topic_id": 42, "timeframe": "1h"},
        ]
        out = resolve_strategy_configs(raw)
        assert out[0].timeframe == "1h"

    def test_risk_partial_override_preserves_other_fields(self):
        raw = _base_raw()
        raw["strategies"] = [
            {
                "name": "rsi_no_retest",
                "telegram_topic_id": 42,
                "risk": {"tp1_close_pct": 0.5},
            },
        ]
        out = resolve_strategy_configs(raw)
        # Overridden
        assert out[0].risk.tp1_close_pct == Decimal("0.5")
        # Preserved from global
        assert out[0].risk.risk_per_trade_pct == Decimal("0.002")
        assert out[0].risk.leverage == 10

    def test_risk_absent_uses_global(self):
        raw = _base_raw()
        raw["strategies"] = [
            {"name": "rsi_no_retest", "telegram_topic_id": 42},
        ]
        out = resolve_strategy_configs(raw)
        assert out[0].risk.tp1_close_pct == Decimal("1")

    def test_stray_risk_keys_ignored(self):
        raw = _base_raw()
        raw["strategies"] = [
            {
                "name": "rsi_no_retest",
                "telegram_topic_id": 42,
                "risk": {"not_a_field": 9, "tp1_close_pct": 0.2},
            },
        ]
        out = resolve_strategy_configs(raw)
        assert out[0].risk.tp1_close_pct == Decimal("0.2")

    def test_stray_risk_key_warn_logs(self):
        import structlog.testing
        raw = _base_raw()
        raw["strategies"] = [
            {
                "name": "rsi_no_retest",
                "telegram_topic_id": 42,
                "risk": {"max_pos_size": 99},  # typo of max_position_size_pct
            },
        ]
        with structlog.testing.capture_logs() as captured:
            resolve_strategy_configs(raw)
        warnings = [c for c in captured if c.get("log_level") == "warning"]
        assert any(
            c.get("event") == "strategy_config_unknown_risk_key"
            and c.get("key") == "max_pos_size"
            for c in warnings
        )

    def test_symbols_are_tuple_not_list(self):
        out = resolve_strategy_configs(_base_raw())
        assert isinstance(out[0].symbols, tuple)


class TestValidation:
    def test_unknown_strategy_name_raises(self):
        raw = _base_raw()
        raw["strategies"] = [
            {"name": "ghost_strategy", "telegram_topic_id": 42},
        ]
        with pytest.raises(ValueError, match="unknown strategy"):
            resolve_strategy_configs(raw)

    def test_missing_strategy_name_raises(self):
        raw = _base_raw()
        raw["strategies"] = [
            {"telegram_topic_id": 42},
        ]
        with pytest.raises(ValueError, match="must declare `name`"):
            resolve_strategy_configs(raw)

    def test_missing_telegram_topic_id_raises(self):
        raw = _base_raw()
        raw["strategies"] = [
            {"name": "rsi_no_retest"},
        ]
        with pytest.raises(ValueError, match="telegram_topic_id"):
            resolve_strategy_configs(raw)

    def test_duplicate_telegram_topic_id_raises(self):
        raw = _base_raw()
        raw["strategies"] = [
            {"name": "rsi_no_retest", "telegram_topic_id": 42},
            {"name": "rsi_wma_retest", "telegram_topic_id": 42},
        ]
        with pytest.raises(ValueError, match="already used"):
            resolve_strategy_configs(raw)

    def test_topic_id_equals_debug_raises(self):
        raw = _base_raw()
        raw["telegram"]["debug_topic_id"] = 42
        raw["strategies"] = [
            {"name": "rsi_no_retest", "telegram_topic_id": 42},
        ]
        with pytest.raises(ValueError, match="collides with debug_topic_id"):
            resolve_strategy_configs(raw)

    def test_missing_group_id_raises(self):
        raw = _base_raw()
        raw["telegram"] = {"debug_topic_id": 99}
        with pytest.raises(ValueError, match="group_id"):
            resolve_strategy_configs(raw)

    def test_missing_debug_topic_id_raises(self):
        raw = _base_raw()
        raw["telegram"] = {"group_id": -100}
        with pytest.raises(ValueError, match="debug_topic_id"):
            resolve_strategy_configs(raw)

    def test_missing_telegram_block_raises(self):
        raw = _base_raw()
        del raw["telegram"]
        with pytest.raises(ValueError, match="group_id"):
            resolve_strategy_configs(raw)

    def test_missing_timeframe_raises(self):
        raw = _base_raw()
        del raw["timeframe"]
        with pytest.raises(ValueError, match="timeframe"):
            resolve_strategy_configs(raw)

    def test_no_symbols_anywhere_raises(self):
        raw = _base_raw()
        raw["symbols"] = []
        raw["strategies"] = [
            {"name": "rsi_no_retest", "telegram_topic_id": 42},
        ]
        with pytest.raises(ValueError, match="no symbols"):
            resolve_strategy_configs(raw)

    def test_non_list_strategies_raises(self):
        raw = _base_raw()
        raw["strategies"] = {"not": "a list"}
        with pytest.raises(ValueError, match="must be a list"):
            resolve_strategy_configs(raw)

    def test_non_dict_strategy_entry_raises(self):
        raw = _base_raw()
        raw["strategies"] = ["bare-string"]
        with pytest.raises(ValueError, match="must be a mapping"):
            resolve_strategy_configs(raw)


class TestApiSurface:
    def test_targets_cross_products_symbols_and_timeframe(self):
        out = resolve_strategy_configs(_base_raw())
        assert out[0].targets == frozenset(
            {("BTC/USDT", "15m"), ("ETH/USDT", "15m")}
        )

    def test_as_legacy_dict_has_expected_keys(self):
        out = resolve_strategy_configs(_base_raw())
        legacy = out[0].as_legacy_dict()
        assert legacy["strategy"] == "rsi_no_retest"
        assert legacy["symbols"] == ["BTC/USDT", "ETH/USDT"]
        assert legacy["timeframe"] == "15m"
        assert legacy["risk"]["leverage"] == 10
        assert legacy["risk"]["tp1_close_pct"] == 1.0
        assert legacy["strategy_params"] == {}

    def test_as_legacy_dict_symbols_is_list_not_tuple(self):
        # Existing strategies mutate / iterate as list.
        out = resolve_strategy_configs(_base_raw())
        legacy = out[0].as_legacy_dict()
        assert isinstance(legacy["symbols"], list)

    def test_frozen_dataclass_cannot_be_mutated(self):
        out = resolve_strategy_configs(_base_raw())
        with pytest.raises(dataclasses_frozen_error()):
            out[0].timeframe = "5m"  # type: ignore[misc]


def dataclasses_frozen_error():
    """Python 3.11+ raises FrozenInstanceError; older raises AttributeError."""
    try:
        from dataclasses import FrozenInstanceError
        return FrozenInstanceError
    except ImportError:
        return AttributeError
