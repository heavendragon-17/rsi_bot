from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.trading.strategy.core_v2_1 import (
    AltH1Snapshot,
    BtcH1Snapshot,
    BtcH4Snapshot,
    CoreState,
    CyclePhase,
    DecisionKind,
    EvaluationInput,
    EventType,
    M15Snapshot,
    M15TrendSnapshot,
    ReasonCode,
    Venue,
    evaluate_core_v2_1,
)

D = Decimal
BASE_TIME = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


def _m15(closed_at: datetime, **updates) -> M15Snapshot:
    values = {
        "closed_at": closed_at,
        "is_closed": True,
        "open": D("100"),
        "high": D("103"),
        "low": D("100"),
        "close": D("102"),
        "ema21": D("101"),
        "ema200": D("90"),
        "atr14": D("2"),
        "rsi21": D("60"),
        "rsi_ema9": D("55"),
        "rsi_wma45": D("54"),
    }
    values.update(updates)
    return M15Snapshot(**values)


def _input(
    closed_at: datetime = BASE_TIME,
    *,
    current: dict | None = None,
    previous: dict | None = None,
    slope_ema21: Decimal = D("100"),
    alt_h1: dict | None = None,
    btc_h1: dict | None = None,
    btc_h4: dict | None = None,
    symbol: str = "ETHUSDT",
    venue: Venue = Venue.BINANCE_FUTURES,
) -> EvaluationInput:
    h1_closed_at = closed_at.replace(minute=0, second=0, microsecond=0)
    h4_closed_at = h1_closed_at.replace(hour=(h1_closed_at.hour // 4) * 4)
    previous_values = {"rsi_ema9": D("53"), "rsi_wma45": D("54")}
    previous_values.update(previous or {})
    alt_values = {
        "closed_at": h1_closed_at,
        "is_closed": True,
        "rsi21": D("55"),
        "rsi_ema9": D("50"),
        "rsi_wma45": D("50"),
    }
    alt_values.update(alt_h1 or {})
    btc_h1_values = {
        "closed_at": h1_closed_at,
        "is_closed": True,
        "close": D("101"),
        "ema21": D("100"),
        "rsi21": D("55"),
        "rsi_ema9": D("50"),
        "rsi_wma45": D("50"),
    }
    btc_h1_values.update(btc_h1 or {})
    btc_h4_values = {
        "closed_at": h4_closed_at,
        "is_closed": True,
        "rsi21": D("60"),
        "rsi_ema9": D("55"),
        "rsi_wma45": D("50"),
    }
    btc_h4_values.update(btc_h4 or {})
    return EvaluationInput(
        symbol=symbol,
        venue=venue,
        current_m15=_m15(closed_at, **(current or {})),
        previous_m15=_m15(closed_at - timedelta(minutes=15), **previous_values),
        m15_three_bars_ago=M15TrendSnapshot(
            closed_at=closed_at - timedelta(minutes=45),
            is_closed=True,
            ema21=slope_ema21,
        ),
        alt_h1=AltH1Snapshot(**alt_values),
        btc_h1=BtcH1Snapshot(**btc_h1_values),
        btc_h4=BtcH4Snapshot(**btc_h4_values),
    )


def _start_wait(closed_at: datetime = BASE_TIME):
    data = _input(
        closed_at,
        current={
            "open": D("102"),
            "high": D("104"),
            "low": D("101"),
            "close": D("103.2"),
        },
    )
    result = evaluate_core_v2_1(data, CoreState.initial())
    assert result.decision.kind is DecisionKind.WAIT_FOR_PULLBACK
    return result


def _no_touch(closed_at: datetime) -> EvaluationInput:
    return _input(
        closed_at,
        current={
            "open": D("102.5"),
            "high": D("103.5"),
            "low": D("102.1"),
            "close": D("103"),
        },
    )


def _touch(closed_at: datetime, **updates) -> EvaluationInput:
    current = {
        "open": D("102"),
        "high": D("102.5"),
        "low": D("101.4"),
        "close": D("102"),
    }
    current.update(updates)
    return _input(closed_at, current=current)


def test_no_fresh_cross_is_quiet_and_remains_armed() -> None:
    data = _input(previous={"rsi_ema9": D("55"), "rsi_wma45": D("54")})
    result = evaluate_core_v2_1(data, CoreState.initial())
    assert result.decision.kind is DecisionKind.QUIET
    assert result.decision.event is None
    assert result.next_state.phase is CyclePhase.ARMED
    assert result.next_state.last_processed_at == BASE_TIME


def test_fresh_cross_accepts_previous_equality_but_requires_current_strictness() -> None:
    data = _input(previous={"rsi_ema9": D("54"), "rsi_wma45": D("54")})
    result = evaluate_core_v2_1(data, CoreState.initial())
    assert result.decision.kind is DecisionKind.A_PLUS_LONG

    no_cross = _input(current={"rsi_ema9": D("54"), "rsi_wma45": D("54")})
    result = evaluate_core_v2_1(no_cross, CoreState.initial())
    assert result.decision.kind is DecisionKind.QUIET


def test_a_plus_event_and_reference_levels_are_exact() -> None:
    result = evaluate_core_v2_1(_input(), CoreState.initial())
    assert result.decision.kind is DecisionKind.A_PLUS_LONG
    assert result.decision.metrics.distance_atr == D("0.5")
    assert result.decision.metrics.signal_range_atr == D("1.5")
    event = result.decision.event
    assert event is not None
    assert event.event_type is EventType.A_PLUS_LONG
    assert event.symbol == "ETHUSDT"
    assert event.venue is Venue.BINANCE_FUTURES
    assert event.closed_at == BASE_TIME
    assert event.trade_levels is not None
    assert event.trade_levels.reference_entry == D("102")
    assert event.trade_levels.reference_stop == D("99.50")
    assert event.trade_levels.risk_1r == D("2.50")
    assert event.trade_levels.tp1 == D("104.50")
    assert event.trade_levels.tp2 == D("107.00")
    assert event.trade_levels.tp3 == D("109.50")
    assert result.next_state.phase is CyclePhase.DISARMED


def test_extreme_atr_preserves_exact_negative_advisory_stop_without_crashing() -> None:
    data = _input(
        current={
            "open": D("2"),
            "high": D("11"),
            "low": D("1"),
            "close": D("10"),
            "ema21": D("9"),
            "ema200": D("8"),
            "atr14": D("100"),
        },
        slope_ema21=D("8"),
    )

    result = evaluate_core_v2_1(data, CoreState.initial())

    assert result.decision.kind is DecisionKind.A_PLUS_LONG
    assert result.decision.event is not None
    assert result.decision.event.trade_levels is not None
    assert result.decision.event.trade_levels.reference_stop == D("-24")
    assert result.decision.event.trade_levels.risk_1r == D("34")


@pytest.mark.parametrize(
    ("target", "updates", "reason"),
    [
        ("m15", {"close": D("101")}, ReasonCode.M15_CLOSE_NOT_ABOVE_EMA21),
        ("m15", {"ema21": D("90")}, ReasonCode.M15_EMA21_NOT_ABOVE_EMA200),
        ("slope", {"slope_ema21": D("101")}, ReasonCode.M15_EMA21_NOT_RISING),
        ("m15", {"rsi21": D("50")}, ReasonCode.M15_RSI_NOT_ABOVE_50),
        ("m15", {"rsi21": D("55")}, ReasonCode.M15_RSI_NOT_ABOVE_EMA9),
        ("m15", {"rsi21": D("54")}, ReasonCode.M15_RSI_NOT_ABOVE_WMA45),
        ("alt", {"rsi21": D("50")}, ReasonCode.ALT_H1_RSI_NOT_ABOVE_50),
        ("alt", {"rsi_ema9": D("49")}, ReasonCode.ALT_H1_EMA9_BELOW_WMA45),
        ("btc_h1", {"close": D("100")}, ReasonCode.BTC_H1_CLOSE_NOT_ABOVE_EMA21),
        ("btc_h1", {"rsi21": D("50")}, ReasonCode.BTC_H1_RSI_NOT_ABOVE_50),
        ("btc_h1", {"rsi_ema9": D("49")}, ReasonCode.BTC_H1_EMA9_BELOW_WMA45),
        ("btc_h4", {"rsi21": D("55")}, ReasonCode.BTC_H4_RSI_NOT_ABOVE_EMA9),
        ("btc_h4", {"rsi_ema9": D("50")}, ReasonCode.BTC_H4_EMA9_NOT_ABOVE_WMA45),
    ],
)
def test_every_mandatory_filter_failure_rejects_and_consumes_cycle(
    target: str,
    updates: dict,
    reason: ReasonCode,
) -> None:
    kwargs: dict = {}
    if target == "m15":
        kwargs["current"] = updates
    elif target == "slope":
        kwargs.update(updates)
    elif target == "alt":
        kwargs["alt_h1"] = updates
    else:
        kwargs[target] = updates
    result = evaluate_core_v2_1(_input(**kwargs), CoreState.initial())
    assert result.decision.kind is DecisionKind.REJECTED
    assert reason in result.decision.reasons
    assert result.decision.event is None
    assert result.next_state.phase is CyclePhase.DISARMED


def test_h1_equality_is_bullish_while_btc_h4_equality_is_not() -> None:
    h1_equal = _input(
        alt_h1={"rsi_ema9": D("50"), "rsi_wma45": D("50")},
        btc_h1={"rsi_ema9": D("50"), "rsi_wma45": D("50")},
    )
    assert evaluate_core_v2_1(h1_equal, CoreState.initial()).decision.kind is DecisionKind.A_PLUS_LONG

    h4_equal = _input(btc_h4={"rsi_ema9": D("50"), "rsi_wma45": D("50")})
    assert evaluate_core_v2_1(h4_equal, CoreState.initial()).decision.kind is DecisionKind.REJECTED


def test_anti_chase_threshold_equality_passes() -> None:
    data = _input(
        current={
            "open": D("102"),
            "high": D("104"),
            "low": D("101"),
            "close": D("103"),
        }
    )
    result = evaluate_core_v2_1(data, CoreState.initial())
    assert result.decision.metrics.distance_atr == D("1")
    assert result.decision.metrics.signal_range_atr == D("1.5")
    assert result.decision.kind is DecisionKind.A_PLUS_LONG


@pytest.mark.parametrize(
    ("current", "expected_reasons"),
    [
        (
            {"open": D("102"), "high": D("103.2"), "low": D("101"), "close": D("103.2")},
            (ReasonCode.PRICE_EXTENDED_FROM_EMA21,),
        ),
        (
            {"open": D("102"), "high": D("104"), "low": D("100.8"), "close": D("102")},
            (ReasonCode.SIGNAL_CANDLE_TOO_LARGE,),
        ),
        (
            {"open": D("102"), "high": D("105"), "low": D("100"), "close": D("104")},
            (
                ReasonCode.PRICE_EXTENDED_FROM_EMA21,
                ReasonCode.SIGNAL_CANDLE_TOO_LARGE,
            ),
        ),
    ],
)
def test_anti_chase_failure_creates_wait_with_specific_reasons(
    current: dict,
    expected_reasons: tuple[ReasonCode, ...],
) -> None:
    result = evaluate_core_v2_1(_input(current=current), CoreState.initial())
    assert result.decision.kind is DecisionKind.WAIT_FOR_PULLBACK
    assert result.decision.reasons == expected_reasons
    assert result.decision.event is not None
    assert result.decision.event.event_type is EventType.WAIT_FOR_PULLBACK
    assert result.decision.event.trade_levels is None
    assert result.decision.event.wait_bars_elapsed == 0
    assert result.decision.preferred_entry_zone.lower == D("101")
    assert result.decision.preferred_entry_zone.upper == D("101.50")
    assert result.next_state.phase is CyclePhase.WAITING
    assert result.next_state.wait_bars_elapsed == 0


@pytest.mark.parametrize("confirmation_number", [1, 2, 3, 4])
def test_pullback_may_confirm_on_each_of_exactly_four_wait_candles(
    confirmation_number: int,
) -> None:
    state = _start_wait().next_state
    for wait_number in range(1, confirmation_number + 1):
        closed_at = BASE_TIME + timedelta(minutes=15 * wait_number)
        data = _touch(closed_at) if wait_number == confirmation_number else _no_touch(closed_at)
        result = evaluate_core_v2_1(data, state)
        state = result.next_state
        if wait_number < confirmation_number:
            assert result.decision.kind is DecisionKind.WAIT_CONTINUES
    assert result.decision.kind is DecisionKind.PULLBACK_LONG
    assert result.decision.event is not None
    assert result.decision.event.event_type is EventType.PULLBACK_LONG
    assert result.decision.event.wait_bars_elapsed == confirmation_number
    assert result.next_state.phase is CyclePhase.DISARMED


def test_wait_expires_on_fourth_subsequent_candle_not_fifth() -> None:
    state = _start_wait().next_state
    for wait_number in range(1, 5):
        result = evaluate_core_v2_1(
            _no_touch(BASE_TIME + timedelta(minutes=15 * wait_number)),
            state,
        )
        state = result.next_state
        if wait_number < 4:
            assert result.decision.kind is DecisionKind.WAIT_CONTINUES
            assert state.wait_bars_elapsed == wait_number
    assert result.decision.kind is DecisionKind.WAIT_EXPIRED
    assert result.decision.event is not None
    assert result.decision.event.wait_bars_elapsed == 4
    assert state.phase is CyclePhase.DISARMED


def test_confirmation_has_priority_over_expiry_on_wait_four() -> None:
    state = _start_wait().next_state
    for wait_number in range(1, 4):
        result = evaluate_core_v2_1(
            _no_touch(BASE_TIME + timedelta(minutes=15 * wait_number)),
            state,
        )
        state = result.next_state
    result = evaluate_core_v2_1(_touch(BASE_TIME + timedelta(hours=1)), state)
    assert result.decision.kind is DecisionKind.PULLBACK_LONG
    assert result.decision.event.wait_bars_elapsed == 4


@pytest.mark.parametrize(
    ("target", "updates", "reason"),
    [
        ("m15", {"close": D("100.9"), "open": D("101"), "low": D("100"), "high": D("102")}, ReasonCode.CANCEL_M15_CLOSE_BELOW_EMA21),
        ("m15", {"rsi21": D("49")}, ReasonCode.CANCEL_M15_RSI_BELOW_50),
        ("m15", {"rsi_ema9": D("54")}, ReasonCode.CANCEL_M15_EMA9_NOT_ABOVE_WMA45),
        ("btc_h1", {"close": D("100")}, ReasonCode.CANCEL_BTC_H1_CLOSE_NOT_ABOVE_EMA21),
        ("btc_h1", {"rsi21": D("50")}, ReasonCode.CANCEL_BTC_H1_RSI_NOT_ABOVE_50),
        ("btc_h1", {"rsi_ema9": D("49")}, ReasonCode.CANCEL_BTC_H1_EMA9_BELOW_WMA45),
        ("btc_h4", {"rsi21": D("55")}, ReasonCode.CANCEL_BTC_H4_RSI_NOT_ABOVE_EMA9),
        ("btc_h4", {"rsi_ema9": D("50")}, ReasonCode.CANCEL_BTC_H4_EMA9_NOT_ABOVE_WMA45),
    ],
)
def test_every_wait_invalidation_cancels_immediately(
    target: str,
    updates: dict,
    reason: ReasonCode,
) -> None:
    state = _start_wait().next_state
    kwargs: dict = {
        "closed_at": BASE_TIME + timedelta(minutes=15),
        "current": {
            "open": D("102"),
            "high": D("102.5"),
            "low": D("101.4"),
            "close": D("102"),
        },
    }
    if target == "m15":
        kwargs["current"].update(updates)
    else:
        kwargs[target] = updates
    result = evaluate_core_v2_1(_input(**kwargs), state)
    assert result.decision.kind is DecisionKind.WAIT_CANCELLED
    assert reason in result.decision.reasons
    assert result.decision.event is not None
    assert result.decision.event.wait_bars_elapsed == 1
    assert result.next_state.phase is CyclePhase.DISARMED


def test_cancellation_precedes_pullback_and_expiry() -> None:
    state = _start_wait().next_state
    for wait_number in range(1, 4):
        result = evaluate_core_v2_1(
            _no_touch(BASE_TIME + timedelta(minutes=15 * wait_number)),
            state,
        )
        state = result.next_state
    data = _touch(
        BASE_TIME + timedelta(hours=1),
        rsi_ema9=D("54"),
        rsi_wma45=D("54"),
    )
    result = evaluate_core_v2_1(data, state)
    assert result.decision.kind is DecisionKind.WAIT_CANCELLED
    assert result.decision.event.wait_bars_elapsed == 4
    assert ReasonCode.CANCEL_M15_EMA9_NOT_ABOVE_WMA45 in result.decision.reasons


def test_alt_h1_loss_does_not_cancel_wait_but_blocks_confirmation() -> None:
    state = _start_wait().next_state
    data = _input(
        BASE_TIME + timedelta(minutes=15),
        current={
            "open": D("102"),
            "high": D("102.5"),
            "low": D("101.4"),
            "close": D("102"),
        },
        alt_h1={"rsi21": D("49")},
    )
    result = evaluate_core_v2_1(data, state)
    assert result.decision.kind is DecisionKind.WAIT_CONTINUES
    assert result.next_state.wait_bars_elapsed == 1


def test_pullback_uses_dynamic_zone_and_does_not_recheck_slope_or_anti_chase() -> None:
    state = _start_wait().next_state
    data = _input(
        BASE_TIME + timedelta(minutes=15),
        current={
            "open": D("106"),
            "high": D("110"),
            "low": D("102.9"),
            "close": D("108"),
            "ema21": D("102"),
            "ema200": D("100"),
            "atr14": D("4"),
        },
        slope_ema21=D("105"),
    )
    # Current dynamic threshold is 102 + .25*4 = 103, so low=102.9 touches.
    # Distance is 1.5 ATR, range is 1.775 ATR, and EMA slope is down; none is
    # re-required by the locked pullback confirmation rule.
    result = evaluate_core_v2_1(data, state)
    assert result.decision.kind is DecisionKind.PULLBACK_LONG
    assert result.decision.event.trade_levels.reference_entry == D("108")


def test_wait_continuation_exposes_current_dynamic_zone() -> None:
    state = _start_wait().next_state
    data = _input(
        BASE_TIME + timedelta(minutes=15),
        current={
            "open": D("104"),
            "high": D("105"),
            "low": D("103.1"),
            "close": D("104"),
            "ema21": D("102"),
            "atr14": D("4"),
        },
    )
    result = evaluate_core_v2_1(data, state)
    assert result.decision.kind is DecisionKind.WAIT_CONTINUES
    assert result.decision.preferred_entry_zone.lower == D("102")
    assert result.decision.preferred_entry_zone.upper == D("103.00")


def test_terminal_cancellation_candle_cannot_simultaneously_rearm() -> None:
    state = _start_wait().next_state
    cancellation = _input(
        BASE_TIME + timedelta(minutes=15),
        current={"rsi_ema9": D("54"), "rsi_wma45": D("54")},
    )
    cancelled = evaluate_core_v2_1(cancellation, state)
    assert cancelled.decision.kind is DecisionKind.WAIT_CANCELLED
    assert cancelled.next_state.phase is CyclePhase.DISARMED

    subsequent_reset = _input(
        BASE_TIME + timedelta(minutes=30),
        current={"rsi_ema9": D("53"), "rsi_wma45": D("54")},
    )
    rearmed = evaluate_core_v2_1(subsequent_reset, cancelled.next_state)
    assert rearmed.decision.kind is DecisionKind.REARMED
    assert rearmed.next_state.phase is CyclePhase.ARMED


def test_rejected_cycle_is_not_reused_until_reset_then_new_cross() -> None:
    rejected = evaluate_core_v2_1(
        _input(current={"close": D("101")}),
        CoreState.initial(),
    )
    assert rejected.decision.kind is DecisionKind.REJECTED

    still_above = evaluate_core_v2_1(
        _input(BASE_TIME + timedelta(minutes=15)),
        rejected.next_state,
    )
    assert still_above.decision.kind is DecisionKind.QUIET
    assert still_above.next_state.phase is CyclePhase.DISARMED

    reset = evaluate_core_v2_1(
        _input(
            BASE_TIME + timedelta(minutes=30),
            current={"rsi_ema9": D("53"), "rsi_wma45": D("54")},
        ),
        still_above.next_state,
    )
    assert reset.decision.kind is DecisionKind.REARMED

    new_cross = evaluate_core_v2_1(
        _input(BASE_TIME + timedelta(minutes=45)),
        reset.next_state,
    )
    assert new_cross.decision.kind is DecisionKind.A_PLUS_LONG


def test_evaluator_is_pure_for_identical_input_and_state() -> None:
    data = _input()
    state = CoreState.initial()
    first = evaluate_core_v2_1(data, state)
    second = evaluate_core_v2_1(data, state)
    assert first == second
    assert state == CoreState.initial()
    assert data.current_m15.close == D("102")


def test_evaluator_rejects_duplicate_backward_and_gapped_calls() -> None:
    first = evaluate_core_v2_1(_input(), CoreState.initial())
    with pytest.raises(ValueError, match="exact 15-minute cadence"):
        evaluate_core_v2_1(_input(), first.next_state)
    with pytest.raises(ValueError, match="exact 15-minute cadence"):
        evaluate_core_v2_1(
            _input(BASE_TIME + timedelta(minutes=30)),
            first.next_state,
        )


def test_hyperliquid_pump_event_preserves_venue_identity() -> None:
    result = evaluate_core_v2_1(
        _input(symbol="PUMP", venue=Venue.HYPERLIQUID_PERP),
        CoreState.initial(),
    )
    assert result.decision.kind is DecisionKind.A_PLUS_LONG
    assert result.decision.event.symbol == "PUMP"
    assert result.decision.event.venue is Venue.HYPERLIQUID_PERP
