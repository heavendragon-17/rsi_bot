from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.trading.strategy.core_v2_1 import (
    BENCHMARK_SYMBOL,
    BINANCE_TRADE_CANDIDATES,
    BTC_BENCHMARK,
    CONFIG_VERSION,
    HYPERLIQUID_TRADE_CANDIDATES,
    INSTRUMENTS,
    LOCKED_CONFIG,
    STRATEGY_VERSION,
    TRADE_CANDIDATES,
    VENUE_BY_SYMBOL,
    AltH1Snapshot,
    BtcH1Snapshot,
    BtcH4Snapshot,
    CoreState,
    CoreV21Config,
    CyclePhase,
    EvaluationInput,
    M15Snapshot,
    M15TrendSnapshot,
    Venue,
    instrument_for_symbol,
)

D = Decimal
NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


def _m15(closed_at: datetime = NOW, *, is_closed: bool = True) -> M15Snapshot:
    return M15Snapshot(
        closed_at=closed_at,
        is_closed=is_closed,
        open=D("100"),
        high=D("103"),
        low=D("100"),
        close=D("102"),
        ema21=D("101"),
        ema200=D("90"),
        atr14=D("2"),
        rsi21=D("60"),
        rsi_ema9=D("55"),
        rsi_wma45=D("54"),
    )


def _evaluation_input(**overrides) -> EvaluationInput:
    values = {
        "symbol": "ETHUSDT",
        "venue": Venue.BINANCE_FUTURES,
        "current_m15": _m15(),
        "previous_m15": _m15(NOW - timedelta(minutes=15)),
        "m15_three_bars_ago": M15TrendSnapshot(
            closed_at=NOW - timedelta(minutes=45),
            is_closed=True,
            ema21=D("100"),
        ),
        "alt_h1": AltH1Snapshot(NOW, True, D("55"), D("50"), D("50")),
        "btc_h1": BtcH1Snapshot(
            NOW,
            True,
            D("101"),
            D("100"),
            D("55"),
            D("50"),
            D("50"),
        ),
        "btc_h4": BtcH4Snapshot(NOW, True, D("60"), D("55"), D("50")),
    }
    values.update(overrides)
    return EvaluationInput(**values)


def test_locked_universe_is_exact_and_ordered() -> None:
    assert TRADE_CANDIDATES == (
        "ETHUSDT",
        "SOLUSDT",
        "BNBUSDT",
        "XRPUSDT",
        "DOGEUSDT",
        "ADAUSDT",
        "LINKUSDT",
        "AVAXUSDT",
        "SUIUSDT",
        "HYPEUSDT",
        "ZECUSDT",
        "LITUSDT",
        "PUMP",
        "AAVEUSDT",
        "NEARUSDT",
        "XMRUSDT",
        "TAOUSDT",
        "ENAUSDT",
        "WLDUSDT",
        "FARTCOINUSDT",
        "JTOUSDT",
        "INJUSDT",
        "UNIUSDT",
        "ONDOUSDT",
        "GRASSUSDT",
    )
    assert len(TRADE_CANDIDATES) == len(set(TRADE_CANDIDATES)) == 25
    assert BENCHMARK_SYMBOL == "BTCUSDT"
    assert BENCHMARK_SYMBOL not in TRADE_CANDIDATES


def test_venue_mapping_keeps_strategy_and_exchange_symbols_separate() -> None:
    assert HYPERLIQUID_TRADE_CANDIDATES == ("PUMP",)
    assert len(BINANCE_TRADE_CANDIDATES) == 24
    assert VENUE_BY_SYMBOL["PUMP"] is Venue.HYPERLIQUID_PERP
    assert INSTRUMENTS["PUMP"].venue_symbol == "PUMP/USDC:USDC"
    assert instrument_for_symbol("ETHUSDT").venue_symbol == "ETH/USDT:USDT"
    assert BTC_BENCHMARK.strategy_symbol == "BTCUSDT"
    assert BTC_BENCHMARK.venue is Venue.BINANCE_FUTURES
    with pytest.raises(ValueError, match="not a Core V2.1 trade candidate"):
        instrument_for_symbol("BTCUSDT")


def test_mapping_and_locked_config_are_immutable() -> None:
    with pytest.raises(TypeError):
        INSTRUMENTS["ETHUSDT"] = INSTRUMENTS["PUMP"]  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        LOCKED_CONFIG.wait_candles = 5  # type: ignore[misc]
    with pytest.raises(TypeError):
        CoreV21Config(wait_candles=5)  # type: ignore[call-arg]
    assert STRATEGY_VERSION == "2.1"
    assert CONFIG_VERSION == "core-v2.1-locked-2026-08-20"


def test_locked_config_values_match_packet() -> None:
    assert LOCKED_CONFIG.signal_timeframe == "15m"
    assert LOCKED_CONFIG.alt_confirmation_timeframe == "1h"
    assert LOCKED_CONFIG.btc_regime_timeframe == "1h"
    assert LOCKED_CONFIG.btc_alignment_timeframe == "4h"
    assert LOCKED_CONFIG.rsi_period == 21
    assert LOCKED_CONFIG.rsi_fast_ema_period == 9
    assert LOCKED_CONFIG.rsi_slow_wma_period == 45
    assert LOCKED_CONFIG.price_ema_period == 21
    assert LOCKED_CONFIG.trend_ema_period == 200
    assert LOCKED_CONFIG.atr_period == 14
    assert LOCKED_CONFIG.ema_slope_lookback == 3
    assert LOCKED_CONFIG.wait_candles == 4
    assert LOCKED_CONFIG.maximum_distance_atr == D("1.0")
    assert LOCKED_CONFIG.maximum_signal_range_atr == D("1.5")
    assert LOCKED_CONFIG.pullback_atr_fraction == D("0.25")
    assert LOCKED_CONFIG.stop_atr_fraction == D("0.25")
    assert LOCKED_CONFIG.take_profit_r_multiples == (D("1"), D("2"), D("3"))


def test_models_are_frozen_and_prices_require_decimal() -> None:
    candle = _m15()
    with pytest.raises(FrozenInstanceError):
        candle.close = D("999")  # type: ignore[misc]
    with pytest.raises(TypeError, match="must be Decimal"):
        M15TrendSnapshot(NOW, True, 100.0)  # type: ignore[arg-type]


def test_timestamps_are_normalized_to_utc() -> None:
    plus_seven = timezone(timedelta(hours=7))
    local_time = datetime(2026, 8, 20, 19, 0, tzinfo=plus_seven)
    candle = _m15(local_time)
    assert candle.closed_at == NOW
    assert candle.closed_at.tzinfo is UTC

    state = CoreState(
        phase=CyclePhase.DISARMED,
        last_processed_at=local_time,
    )
    assert state.last_processed_at == NOW
    assert state.to_dict()["last_processed_at"] == "2026-08-20T12:00:00+00:00"


def test_naive_timestamp_and_non_bool_closed_flag_are_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _m15(NOW.replace(tzinfo=None))
    with pytest.raises(TypeError, match="must be bool"):
        _m15(is_closed=1)  # type: ignore[arg-type]


def test_input_rejects_unclosed_snapshot() -> None:
    with pytest.raises(ValueError, match="fully closed candles only: alt_h1"):
        _evaluation_input(
            alt_h1=AltH1Snapshot(NOW, False, D("55"), D("50"), D("50"))
        )


def test_input_rejects_wrong_venue_and_reference_symbol() -> None:
    with pytest.raises(ValueError, match="belongs to BINANCE_FUTURES"):
        _evaluation_input(venue=Venue.HYPERLIQUID_PERP)
    with pytest.raises(ValueError, match="not a Core V2.1 trade candidate"):
        _evaluation_input(symbol="BTCUSDT")


def test_input_requires_exact_m15_cadence_and_slope_source() -> None:
    with pytest.raises(ValueError, match="exactly 15 minutes"):
        _evaluation_input(previous_m15=_m15(NOW - timedelta(minutes=30)))
    with pytest.raises(ValueError, match="exactly 45 minutes"):
        _evaluation_input(
            m15_three_bars_ago=M15TrendSnapshot(
                NOW - timedelta(minutes=30), True, D("100")
            )
        )


def test_input_rejects_point_in_time_lookahead() -> None:
    with pytest.raises(ValueError, match="point-in-time context"):
        _evaluation_input(
            btc_h4=BtcH4Snapshot(
                NOW + timedelta(hours=4), True, D("60"), D("55"), D("50")
            )
        )


def test_input_requires_exact_utc_context_boundaries_and_m15_grid() -> None:
    with pytest.raises(ValueError, match="exact expected.*H1"):
        _evaluation_input(
            alt_h1=AltH1Snapshot(
                NOW - timedelta(hours=1), True, D("55"), D("50"), D("50")
            )
        )
    with pytest.raises(ValueError, match="exact expected.*H4"):
        _evaluation_input(
            btc_h4=BtcH4Snapshot(
                NOW - timedelta(hours=4), True, D("60"), D("55"), D("50")
            )
        )

    off_grid = NOW + timedelta(minutes=7)
    with pytest.raises(ValueError, match="UTC 15-minute grid"):
        _evaluation_input(
            current_m15=_m15(off_grid),
            previous_m15=_m15(off_grid - timedelta(minutes=15)),
            m15_three_bars_ago=M15TrendSnapshot(
                off_grid - timedelta(minutes=45), True, D("100")
            ),
        )


def test_state_json_roundtrip_is_strict_and_utc_canonical() -> None:
    state = CoreState(
        phase=CyclePhase.WAITING,
        wait_bars_elapsed=2,
        cycle_started_at=NOW - timedelta(minutes=30),
        last_processed_at=NOW,
    )
    assert CoreState.from_dict(state.to_dict()) == state
    with pytest.raises(ValueError, match="unknown"):
        CoreState.from_dict({**state.to_dict(), "extra": 1})
    with pytest.raises(ValueError, match="unknown CoreState phase"):
        CoreState.from_dict({**state.to_dict(), "phase": "BROKEN"})


def test_state_invariants_reject_wait_fields_on_wrong_phase() -> None:
    with pytest.raises(ValueError, match="non-WAITING"):
        CoreState(
            phase=CyclePhase.ARMED,
            wait_bars_elapsed=1,
            cycle_started_at=NOW,
            last_processed_at=NOW,
        )
    with pytest.raises(ValueError, match="between 0 and 3"):
        CoreState(
            phase=CyclePhase.WAITING,
            wait_bars_elapsed=4,
            cycle_started_at=NOW,
            last_processed_at=NOW,
        )
