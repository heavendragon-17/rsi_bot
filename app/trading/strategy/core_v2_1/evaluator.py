"""Pure, deterministic Core V2.1 signal state machine."""

from __future__ import annotations

from datetime import datetime, timedelta

from .config import LOCKED_CONFIG, CoreV21Config
from .models import (
    BtcH1Snapshot,
    BtcH4Snapshot,
    CoreDecision,
    CoreEvent,
    CoreState,
    CyclePhase,
    DecisionKind,
    EvaluationInput,
    EvaluationResult,
    EventType,
    PreferredEntryZone,
    ReasonCode,
    SignalMetrics,
    TradeLevels,
)


def _fresh_bullish_cross(data: EvaluationInput) -> bool:
    return (
        data.previous_m15.rsi_ema9 <= data.previous_m15.rsi_wma45
        and data.current_m15.rsi_ema9 > data.current_m15.rsi_wma45
    )


def _m15_mandatory_failures(data: EvaluationInput, config: CoreV21Config) -> list[ReasonCode]:
    candle = data.current_m15
    failures: list[ReasonCode] = []
    if candle.close <= candle.ema21:
        failures.append(ReasonCode.M15_CLOSE_NOT_ABOVE_EMA21)
    if candle.ema21 <= candle.ema200:
        failures.append(ReasonCode.M15_EMA21_NOT_ABOVE_EMA200)
    if candle.ema21 <= data.m15_three_bars_ago.ema21:
        failures.append(ReasonCode.M15_EMA21_NOT_RISING)
    if candle.rsi21 <= config.rsi_threshold:
        failures.append(ReasonCode.M15_RSI_NOT_ABOVE_50)
    if candle.rsi21 <= candle.rsi_ema9:
        failures.append(ReasonCode.M15_RSI_NOT_ABOVE_EMA9)
    if candle.rsi21 <= candle.rsi_wma45:
        failures.append(ReasonCode.M15_RSI_NOT_ABOVE_WMA45)
    return failures


def _alt_h1_failures(data: EvaluationInput, config: CoreV21Config) -> list[ReasonCode]:
    failures: list[ReasonCode] = []
    if data.alt_h1.rsi21 <= config.rsi_threshold:
        failures.append(ReasonCode.ALT_H1_RSI_NOT_ABOVE_50)
    if data.alt_h1.rsi_ema9 < data.alt_h1.rsi_wma45:
        failures.append(ReasonCode.ALT_H1_EMA9_BELOW_WMA45)
    return failures


def _btc_h1_failures(btc: BtcH1Snapshot, config: CoreV21Config) -> list[ReasonCode]:
    failures: list[ReasonCode] = []
    if btc.close <= btc.ema21:
        failures.append(ReasonCode.BTC_H1_CLOSE_NOT_ABOVE_EMA21)
    if btc.rsi21 <= config.rsi_threshold:
        failures.append(ReasonCode.BTC_H1_RSI_NOT_ABOVE_50)
    if btc.rsi_ema9 < btc.rsi_wma45:
        failures.append(ReasonCode.BTC_H1_EMA9_BELOW_WMA45)
    return failures


def _btc_h4_failures(btc: BtcH4Snapshot) -> list[ReasonCode]:
    failures: list[ReasonCode] = []
    if btc.rsi21 <= btc.rsi_ema9:
        failures.append(ReasonCode.BTC_H4_RSI_NOT_ABOVE_EMA9)
    if btc.rsi_ema9 <= btc.rsi_wma45:
        failures.append(ReasonCode.BTC_H4_EMA9_NOT_ABOVE_WMA45)
    return failures


def _mandatory_failures(data: EvaluationInput, config: CoreV21Config) -> tuple[ReasonCode, ...]:
    return tuple(
        _m15_mandatory_failures(data, config)
        + _alt_h1_failures(data, config)
        + _btc_h1_failures(data.btc_h1, config)
        + _btc_h4_failures(data.btc_h4)
    )


def _metrics(data: EvaluationInput) -> SignalMetrics:
    candle = data.current_m15
    return SignalMetrics(
        distance_atr=(candle.close - candle.ema21) / candle.atr14,
        signal_range_atr=(candle.high - candle.low) / candle.atr14,
    )


def _anti_chase_failures(
    metrics: SignalMetrics,
    config: CoreV21Config,
) -> tuple[ReasonCode, ...]:
    failures: list[ReasonCode] = []
    if metrics.distance_atr > config.maximum_distance_atr:
        failures.append(ReasonCode.PRICE_EXTENDED_FROM_EMA21)
    if metrics.signal_range_atr > config.maximum_signal_range_atr:
        failures.append(ReasonCode.SIGNAL_CANDLE_TOO_LARGE)
    return tuple(failures)


def _entry_zone(data: EvaluationInput, config: CoreV21Config) -> PreferredEntryZone:
    lower = data.current_m15.ema21
    return PreferredEntryZone(
        lower=lower,
        upper=lower + config.pullback_atr_fraction * data.current_m15.atr14,
    )


def _trade_levels(data: EvaluationInput, config: CoreV21Config) -> TradeLevels:
    candle = data.current_m15
    reference_entry = candle.close
    reference_stop = candle.low - config.stop_atr_fraction * candle.atr14
    risk_1r = reference_entry - reference_stop
    return TradeLevels(
        reference_entry=reference_entry,
        reference_stop=reference_stop,
        risk_1r=risk_1r,
        tp1=reference_entry + config.take_profit_r_multiples[0] * risk_1r,
        tp2=reference_entry + config.take_profit_r_multiples[1] * risk_1r,
        tp3=reference_entry + config.take_profit_r_multiples[2] * risk_1r,
    )


def _wait_cancellation_failures(
    data: EvaluationInput,
    config: CoreV21Config,
) -> tuple[ReasonCode, ...]:
    candle = data.current_m15
    failures: list[ReasonCode] = []
    if candle.close < candle.ema21:
        failures.append(ReasonCode.CANCEL_M15_CLOSE_BELOW_EMA21)
    if candle.rsi21 < config.rsi_threshold:
        failures.append(ReasonCode.CANCEL_M15_RSI_BELOW_50)
    if candle.rsi_ema9 <= candle.rsi_wma45:
        failures.append(ReasonCode.CANCEL_M15_EMA9_NOT_ABOVE_WMA45)
    if data.btc_h1.close <= data.btc_h1.ema21:
        failures.append(ReasonCode.CANCEL_BTC_H1_CLOSE_NOT_ABOVE_EMA21)
    if data.btc_h1.rsi21 <= config.rsi_threshold:
        failures.append(ReasonCode.CANCEL_BTC_H1_RSI_NOT_ABOVE_50)
    if data.btc_h1.rsi_ema9 < data.btc_h1.rsi_wma45:
        failures.append(ReasonCode.CANCEL_BTC_H1_EMA9_BELOW_WMA45)
    if data.btc_h4.rsi21 <= data.btc_h4.rsi_ema9:
        failures.append(ReasonCode.CANCEL_BTC_H4_RSI_NOT_ABOVE_EMA9)
    if data.btc_h4.rsi_ema9 <= data.btc_h4.rsi_wma45:
        failures.append(ReasonCode.CANCEL_BTC_H4_EMA9_NOT_ABOVE_WMA45)
    return tuple(failures)


def _pullback_confirmed(data: EvaluationInput, config: CoreV21Config) -> bool:
    candle = data.current_m15
    touched = candle.low <= candle.ema21 + config.pullback_atr_fraction * candle.atr14
    m15_confirmed = (
        candle.close > candle.ema21
        and candle.ema21 > candle.ema200
        and candle.rsi21 > config.rsi_threshold
        and candle.rsi_ema9 > candle.rsi_wma45
        and candle.rsi21 > candle.rsi_ema9
    )
    return (
        touched
        and m15_confirmed
        and not _alt_h1_failures(data, config)
        and not _btc_h1_failures(data.btc_h1, config)
        and not _btc_h4_failures(data.btc_h4)
    )


def _disarmed_state(closed_at: datetime) -> CoreState:
    return CoreState(phase=CyclePhase.DISARMED, last_processed_at=closed_at)


def _evaluate_wait(
    data: EvaluationInput,
    state: CoreState,
    config: CoreV21Config,
) -> EvaluationResult:
    wait_number = state.wait_bars_elapsed + 1
    cancellation_reasons = _wait_cancellation_failures(data, config)
    if cancellation_reasons:
        event = CoreEvent(
            event_type=EventType.WAIT_CANCELLED,
            symbol=data.symbol,
            venue=data.venue,
            closed_at=data.current_m15.closed_at,
            reasons=cancellation_reasons,
            wait_bars_elapsed=wait_number,
        )
        return EvaluationResult(
            decision=CoreDecision(
                kind=DecisionKind.WAIT_CANCELLED,
                reasons=cancellation_reasons,
                event=event,
            ),
            # A terminal WAIT candle never also re-arms the cycle.  Even when
            # EMA9 <= WMA45 caused cancellation, re-arm requires a subsequent
            # fully closed M15 candle.
            next_state=_disarmed_state(data.current_m15.closed_at),
        )

    if _pullback_confirmed(data, config):
        event = CoreEvent(
            event_type=EventType.PULLBACK_LONG,
            symbol=data.symbol,
            venue=data.venue,
            closed_at=data.current_m15.closed_at,
            trade_levels=_trade_levels(data, config),
            wait_bars_elapsed=wait_number,
        )
        return EvaluationResult(
            decision=CoreDecision(kind=DecisionKind.PULLBACK_LONG, event=event),
            next_state=_disarmed_state(data.current_m15.closed_at),
        )

    if wait_number == config.wait_candles:
        event = CoreEvent(
            event_type=EventType.WAIT_EXPIRED,
            symbol=data.symbol,
            venue=data.venue,
            closed_at=data.current_m15.closed_at,
            wait_bars_elapsed=wait_number,
        )
        return EvaluationResult(
            decision=CoreDecision(kind=DecisionKind.WAIT_EXPIRED, event=event),
            next_state=_disarmed_state(data.current_m15.closed_at),
        )

    zone = _entry_zone(data, config)
    return EvaluationResult(
        decision=CoreDecision(
            kind=DecisionKind.WAIT_CONTINUES,
            preferred_entry_zone=zone,
        ),
        next_state=CoreState(
            phase=CyclePhase.WAITING,
            wait_bars_elapsed=wait_number,
            cycle_started_at=state.cycle_started_at,
            last_processed_at=data.current_m15.closed_at,
        ),
    )


def evaluate_core_v2_1(data: EvaluationInput, state: CoreState) -> EvaluationResult:
    """Evaluate one fully closed M15 candle and return a new immutable state.

    Calls must be made in chronological order for each symbol.  Duplicate or
    backward timestamps are rejected so reconnect/catch-up code cannot silently
    corrupt WAIT counts or reuse a crossover.
    """

    if not isinstance(data, EvaluationInput):
        raise TypeError("data must be EvaluationInput")
    if not isinstance(state, CoreState):
        raise TypeError("state must be CoreState")
    closed_at = data.current_m15.closed_at
    if (
        state.last_processed_at is not None
        and closed_at != state.last_processed_at + timedelta(minutes=15)
    ):
        raise ValueError("M15 candles must be evaluated once at an exact 15-minute cadence")

    config = LOCKED_CONFIG
    if state.phase is CyclePhase.WAITING:
        return _evaluate_wait(data, state, config)

    if state.phase is CyclePhase.DISARMED:
        if data.current_m15.rsi_ema9 <= data.current_m15.rsi_wma45:
            return EvaluationResult(
                decision=CoreDecision(kind=DecisionKind.REARMED),
                next_state=CoreState(
                    phase=CyclePhase.ARMED,
                    last_processed_at=closed_at,
                ),
            )
        return EvaluationResult(
            decision=CoreDecision(kind=DecisionKind.QUIET),
            next_state=_disarmed_state(closed_at),
        )

    if not _fresh_bullish_cross(data):
        return EvaluationResult(
            decision=CoreDecision(kind=DecisionKind.QUIET),
            next_state=CoreState(
                phase=CyclePhase.ARMED,
                last_processed_at=closed_at,
            ),
        )

    mandatory_failures = _mandatory_failures(data, config)
    if mandatory_failures:
        return EvaluationResult(
            decision=CoreDecision(
                kind=DecisionKind.REJECTED,
                reasons=mandatory_failures,
            ),
            next_state=_disarmed_state(closed_at),
        )

    metrics = _metrics(data)
    anti_chase_failures = _anti_chase_failures(metrics, config)
    if anti_chase_failures:
        zone = _entry_zone(data, config)
        event = CoreEvent(
            event_type=EventType.WAIT_FOR_PULLBACK,
            symbol=data.symbol,
            venue=data.venue,
            closed_at=closed_at,
            reasons=anti_chase_failures,
            preferred_entry_zone=zone,
            wait_bars_elapsed=0,
        )
        return EvaluationResult(
            decision=CoreDecision(
                kind=DecisionKind.WAIT_FOR_PULLBACK,
                reasons=anti_chase_failures,
                event=event,
                metrics=metrics,
                preferred_entry_zone=zone,
            ),
            next_state=CoreState(
                phase=CyclePhase.WAITING,
                wait_bars_elapsed=0,
                cycle_started_at=closed_at,
                last_processed_at=closed_at,
            ),
        )

    event = CoreEvent(
        event_type=EventType.A_PLUS_LONG,
        symbol=data.symbol,
        venue=data.venue,
        closed_at=closed_at,
        trade_levels=_trade_levels(data, config),
    )
    return EvaluationResult(
        decision=CoreDecision(
            kind=DecisionKind.A_PLUS_LONG,
            event=event,
            metrics=metrics,
        ),
        next_state=_disarmed_state(closed_at),
    )


class CoreV21Evaluator:
    """Small object facade for dependency injection; it holds no state."""

    @staticmethod
    def evaluate(data: EvaluationInput, state: CoreState) -> EvaluationResult:
        return evaluate_core_v2_1(data, state)
