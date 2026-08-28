"""Tests for the BTC RSI cross alert strict configuration resolver."""

from __future__ import annotations

import pytest

from app.signal.btc_rsi_cross_alert.config import (
    COMPONENT_NAME,
    BtcRsiCrossAlertConfig,
    resolve_btc_rsi_cross_alert_config,
)
from app.signal.strategy_config import (
    resolve_signal_runtime_config,
    resolve_strategy_configs,
)

DEBUG_TOPIC = 99


def _locked_entry(**overrides) -> dict:
    entry = {
        "name": COMPONENT_NAME,
        "active": True,
        "telegram_topic_id": 1007,
        "m15_telegram_topic_id": 1008,
        "symbol": "BTC/USDT",
        "trigger_timeframes": ["5m", "15m"],
        "confirmation_timeframe": "1h",
        "trend_timeframe": "4h",
        "rsi_period": 21,
        "rsi_ema_period": 9,
        "rsi_wma_period": 45,
        "context_settle_seconds": 5,
    }
    entry.update(overrides)
    return entry


def _raw(entry: dict, *, extra_strategies: list[dict] | None = None) -> dict:
    return {
        "bot": {"mode": "signal"},
        "telegram": {"group_id": -100, "debug_topic_id": DEBUG_TOPIC},
        "timeframe": "15m",
        "symbols": ["ETH/USDT"],
        "risk": {},
        "strategies": [entry] + (extra_strategies or []),
    }


class TestLockedConfigAccepted:
    def test_accepts_exact_locked_config(self):
        cfg = resolve_btc_rsi_cross_alert_config(
            [_locked_entry()], debug_topic_id=DEBUG_TOPIC, seen_topics={}
        )
        assert isinstance(cfg, BtcRsiCrossAlertConfig)
        assert cfg.name == COMPONENT_NAME
        assert cfg.telegram_topic_id == 1007
        assert cfg.m15_telegram_topic_id == 1008
        assert cfg.telegram_topic_ids == {"5m": 1007, "15m": 1008}
        assert cfg.topic_id_for("5m") == 1007
        assert cfg.topic_id_for("15m") == 1008
        assert cfg.symbol == "BTC/USDT"
        assert cfg.trigger_timeframes == ("5m", "15m")
        assert cfg.confirmation_timeframe == "1h"
        assert cfg.trend_timeframe == "4h"
        assert (cfg.rsi_period, cfg.rsi_ema_period, cfg.rsi_wma_period) == (21, 9, 45)
        assert cfg.context_settle_seconds == 5

    def test_canonical_target_set(self):
        cfg = resolve_btc_rsi_cross_alert_config(
            [_locked_entry()], debug_topic_id=DEBUG_TOPIC, seen_topics={}
        )
        assert cfg.targets == frozenset(
            {
                ("BTC/USDT", "5m"),
                ("BTC/USDT", "15m"),
                ("BTC/USDT", "1h"),
                ("BTC/USDT", "4h"),
            }
        )

    def test_aggregate_includes_component_targets(self):
        aggregate = resolve_signal_runtime_config(_raw(_locked_entry()))
        assert aggregate.btc_rsi_cross_alert is not None
        assert aggregate.strategies == ()
        assert aggregate.targets == frozenset(
            {("BTC/USDT", tf) for tf in ("5m", "15m", "1h", "4h")}
        )


class TestLockedValueRejections:
    @pytest.mark.parametrize(
        "override, match",
        [
            ({"symbol": "ETH/USDT"}, "only supports symbol"),
            ({"trigger_timeframes": ["5m"]}, "exactly"),
            ({"trigger_timeframes": ["5m", "15m", "1h"]}, "exactly"),
            ({"trigger_timeframes": ["5m", "5m"]}, "duplicates"),
            ({"trigger_timeframes": []}, "requires trigger_timeframes"),
            ({"trigger_timeframes": None}, "requires trigger_timeframes"),
            ({"trend_timeframe": "1h"}, "trend_timeframe must be"),
            ({"confirmation_timeframe": "4h"}, "confirmation_timeframe must be"),
            ({"rsi_period": 14}, "locked to 21"),
            ({"rsi_ema_period": 12}, "locked to 9"),
            ({"rsi_wma_period": 45.5}, "exact integer"),
            ({"rsi_wma_period": "45"}, "exact integer"),
            ({"context_settle_seconds": -1}, "integer in"),
            ({"context_settle_seconds": 31}, "integer in"),
            ({"context_settle_seconds": 2.5}, "must be an integer"),
            ({"context_settle_seconds": True}, "must be an integer"),
            ({"telegram_topic_id": None}, "must declare telegram_topic_id"),
            ({"telegram_topic_id": "abc"}, "integer-coercible"),
            ({"m15_telegram_topic_id": None}, "must declare m15_telegram_topic_id"),
            ({"m15_telegram_topic_id": "abc"}, "integer-coercible"),
            ({"name": "something_else"}, "component name must be"),
        ],
    )
    def test_rejects_invalid_locked_values(self, override, match):
        entry = _locked_entry(**override)
        if override.get("trigger_timeframes", "_present_") is None:
            entry.pop("trigger_timeframes", None)
        if override.get("telegram_topic_id") is None and "telegram_topic_id" in override:
            entry.pop("telegram_topic_id")
        if (
            override.get("m15_telegram_topic_id") is None
            and "m15_telegram_topic_id" in override
        ):
            entry.pop("m15_telegram_topic_id")
        with pytest.raises(ValueError, match=match):
            resolve_btc_rsi_cross_alert_config(
                [entry], debug_topic_id=DEBUG_TOPIC, seen_topics={}
            )

    def test_settle_bounds_are_inclusive(self):
        for settle in (0, 30):
            cfg = resolve_btc_rsi_cross_alert_config(
                [_locked_entry(context_settle_seconds=settle)],
                debug_topic_id=DEBUG_TOPIC,
                seen_topics={},
            )
            assert cfg.context_settle_seconds == settle


class TestTopicCollisions:
    def test_debug_topic_collision_rejected(self):
        with pytest.raises(ValueError, match="collides with debug_topic_id"):
            resolve_btc_rsi_cross_alert_config(
                [_locked_entry(telegram_topic_id=DEBUG_TOPIC)],
                debug_topic_id=DEBUG_TOPIC,
                seen_topics={},
            )

    def test_m15_debug_topic_collision_rejected(self):
        with pytest.raises(ValueError, match="collides with debug_topic_id"):
            resolve_btc_rsi_cross_alert_config(
                [_locked_entry(m15_telegram_topic_id=DEBUG_TOPIC)],
                debug_topic_id=DEBUG_TOPIC,
                seen_topics={},
            )

    def test_m5_and_m15_topics_must_be_distinct(self):
        with pytest.raises(ValueError, match="must be different"):
            resolve_btc_rsi_cross_alert_config(
                [_locked_entry(m15_telegram_topic_id=1007)],
                debug_topic_id=DEBUG_TOPIC,
                seen_topics={},
            )

    def test_ordinary_strategy_topic_collision_rejected(self):
        raw = _raw(
            _locked_entry(telegram_topic_id=42),
            extra_strategies=[
                {"name": "rsi_no_retest", "active": True, "telegram_topic_id": 42}
            ],
        )
        with pytest.raises(ValueError, match="already used by"):
            resolve_signal_runtime_config(raw)

    def test_ordinary_strategy_m15_topic_collision_rejected(self):
        raw = _raw(
            _locked_entry(m15_telegram_topic_id=42),
            extra_strategies=[
                {"name": "rsi_no_retest", "active": True, "telegram_topic_id": 42}
            ],
        )
        with pytest.raises(ValueError, match="already used by"):
            resolve_signal_runtime_config(raw)

    def test_duplicate_active_components_rejected(self):
        with pytest.raises(ValueError, match="at most one active"):
            resolve_btc_rsi_cross_alert_config(
                [_locked_entry(), _locked_entry(telegram_topic_id=1009)],
                debug_topic_id=DEBUG_TOPIC,
                seen_topics={},
            )

    def test_disabled_ordinary_entry_may_share_topic_shape(self):
        """A disabled ordinary entry reserves nothing; BTC may use that id."""
        raw = _raw(
            _locked_entry(telegram_topic_id=42),
            extra_strategies=[
                {"name": "rsi_no_retest", "active": False, "telegram_topic_id": 42}
            ],
        )
        aggregate = resolve_signal_runtime_config(raw)
        assert aggregate.btc_rsi_cross_alert.telegram_topic_id == 42


class TestDisabledComponent:
    def test_disabled_component_ignored_without_reserving_topic(self):
        cfg = resolve_btc_rsi_cross_alert_config(
            [_locked_entry(active=False)],
            debug_topic_id=DEBUG_TOPIC,
            seen_topics={},
        )
        assert cfg is None

    def test_disabled_component_topic_not_reserved_in_aggregate(self):
        raw = _raw(
            _locked_entry(active=False),
            extra_strategies=[
                # Same topic as the disabled component → no collision.
                {"name": "rsi_no_retest", "active": True, "telegram_topic_id": 1007}
            ],
        )
        aggregate = resolve_signal_runtime_config(raw)
        assert aggregate.btc_rsi_cross_alert is None
        assert len(aggregate.strategies) == 1

    def test_disabled_component_with_invalid_values_is_not_validated(self):
        """Fail-closed validation only applies to active entries."""
        broken = _locked_entry(active=False, symbol="DOGE/USDT")
        cfg = resolve_btc_rsi_cross_alert_config(
            [broken], debug_topic_id=DEBUG_TOPIC, seen_topics={}
        )
        assert cfg is None


class TestAlertOnlyRuntime:
    def test_alert_only_aggregate_resolves(self):
        raw = _raw(_locked_entry())
        raw["timeframe"] = None  # alert-only needs no global timeframe
        aggregate = resolve_signal_runtime_config(raw)
        assert aggregate.strategies == ()
        assert aggregate.btc_rsi_cross_alert is not None
        assert aggregate.debug_topic_id == DEBUG_TOPIC
        assert not aggregate.is_empty

    def test_backward_compatible_resolver_returns_only_ordinary(self):
        raw = _raw(
            _locked_entry(),
            extra_strategies=[
                {"name": "rsi_no_retest", "active": True, "telegram_topic_id": 42}
            ],
        )
        ordinary = resolve_strategy_configs(raw)
        assert [c.name for c in ordinary] == ["rsi_no_retest"]

    def test_all_disabled_is_empty_aggregate(self):
        raw = _raw(_locked_entry(active=False))
        aggregate = resolve_signal_runtime_config(raw)
        assert aggregate.is_empty
        assert resolve_strategy_configs(raw) == []
