"""Core V2.1 thin adapter onto the shared portfolio backtest engine.

Backtest-only :class:`IStrategy` that reuses the locked Core V2.1 evaluator,
indicators, anchor, and state machine without copying their logic.  It runs
inside the existing :class:`PortfolioEngine` / :class:`MockExchange` /
:class:`PortfolioManager` stack:

* signals come from :func:`evaluate_core_v2_1` over point-in-time contexts
  built with :func:`build_point_in_time_context` from the locked replay
  frames (no recomputation, no drift);
* entries and close-based stop exits are deferred one candle so fills happen
  at the next M15 open with explicit open/close timestamps;
* partial take-profits are resting limit orders placed by the shared
  ``SLTPManager``; no hard disaster stop is placed (the advisory reference
  stop is the sizing basis only);
* the per-symbol ``CoreState`` is owned by this instance (mirrored into the
  engine context for observability) because the engine resets its context on
  full closes while Core re-arm semantics must survive positions.

Documented Core rules and research assumptions are flagged in
``engine_backtest.PROTOCOL``; this module implements mechanics only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import structlog

from app.backtest.core_v2_1.data import build_point_in_time_context
from app.backtest.core_v2_1.replay import ReplayFrames
from app.backtest.core_v2_1.replay import _readiness_reasons
from app.backtest.core_v2_1.replay import _to_core_evaluation_input
from app.core.actions import SIDE_BUY, ClosePosition, DoNothing, OpenPosition
from app.core.analysis_result import AnalysisResult
from app.core.snapshots import ContextSnapshot
from app.trading.strategy.base import BaseStrategy
from app.trading.strategy.core_v2_1 import CoreState, evaluate_core_v2_1
from app.trading.strategy.core_v2_1.models import DecisionKind

logger = structlog.get_logger()

ENTRY_EVENT_KINDS = frozenset({DecisionKind.A_PLUS_LONG, DecisionKind.PULLBACK_LONG})

# TP close fractions: one third of the original quantity at each level.  TP3
# takes the exact remainder so partials always sum to the original quantity.
# The percentages themselves are ASSUMPTION_NOT_A_DECISION (see PROTOCOL).
TP1_FRACTION = Decimal(1) / Decimal(3)
TP2_OF_REMAINDER = Decimal("0.5")

STOP_EXIT_REASON = "CORE_V2_1_STOP_M15_CLOSE_BELOW_EMA21"


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _iso(value: Any) -> str:
    ts = value.isoformat() if hasattr(value, "isoformat") else str(value)
    return ts


@dataclass
class _SymbolState:
    """Authoritative per-symbol Core execution state (instance-owned)."""

    core: CoreState = field(default_factory=CoreState.initial)
    pending_entry: dict[str, Any] | None = None
    pending_stop: dict[str, Any] | None = None
    pending_fire: dict[str, Any] | None = None
    evaluated: int = 0
    not_ready: int = 0


class CoreV21EngineStrategy(BaseStrategy):
    """Thin Core V2.1 adapter for the shared portfolio backtest engine.

    Frames must be bound once per process via :meth:`bind_frames` before the
    engine constructs the strategy.  ``config`` carries only the shared
    ``config.yaml`` risk/backtest blocks (inherited settings, no V2-only
    block).
    """

    STRATEGY_VERSION = "2.1"

    # Bounded-extension hook honored by PortfolioEngine: Core V2.1 has no
    # approved breakeven/lock-profit move, so the engine default "move SL to
    # entry after TP1" must stay off here.  Default False elsewhere, so
    # existing strategies are unaffected.
    DISABLE_TP1_BREAKEVEN_MOVE = True

    _BOUND_FRAMES: ReplayFrames | None = None

    @classmethod
    def bind_frames(cls, frames: ReplayFrames) -> None:
        cls._BOUND_FRAMES = frames

    @classmethod
    def unbind_frames(cls) -> None:
        cls._BOUND_FRAMES = None

    def __init__(self, config: dict):
        super().__init__(config)
        if type(self)._BOUND_FRAMES is None:
            raise ValueError("CoreV21EngineStrategy requires bind_frames() before construction")
        self._frames: ReplayFrames = type(self)._BOUND_FRAMES
        self._states: dict[str, _SymbolState] = {}
        self.ledger: list[dict[str, Any]] = []
        self._seq = 0
        # NOTE: no ``self.indicators`` on purpose.  Frames arrive fully
        # indicator-enriched from the locked builders; recomputing on a
        # truncated window would break the anchor/seed contract.  Any code
        # path needing ``strategy.indicators`` fails closed here.

    # ------------------------------------------------------------------
    # IStrategy
    # ------------------------------------------------------------------

    def analyze(
        self,
        symbol: str,
        df_view,
        position=None,
        context: ContextSnapshot | None = None,
    ) -> AnalysisResult:
        if symbol not in self._frames.alt_m15:
            raise ValueError(f"{symbol!r} is not a bound Core V2.1 frame")
        state = self._states.get(symbol)
        if state is None:
            state = _SymbolState()
            self._states[symbol] = state

        frame = self._frames.alt_m15[symbol]
        abs_idx = len(df_view) - 1
        if abs_idx < 0 or abs_idx >= len(frame):
            raise ValueError(f"engine view out of range for {symbol}: idx={abs_idx}")
        as_of = frame.index[abs_idx]
        candle_open = _decimal(frame["open"].iloc[abs_idx])
        has_position = bool(position is not None and position.has_position)

        fired_entry_this_candle = False
        if state.pending_entry is not None:
            if not has_position:
                fired_entry_this_candle = True
                self._fire_entry(symbol, state, candle_open, as_of)
                has_position = True  # position opens when the action applies
                # An entry candle that also closes below EMA21 arms the stop
                # for the next open (reference: stop evaluated at/after the
                # entry candle; TPs only start on the NEXT candle because the
                # resting limits are placed after this candle's fill check).
                frame_row = frame.iloc[abs_idx]
                if _decimal(frame_row["close"]) < _decimal(frame_row["ema21"]):
                    state.pending_stop = {"trigger_close": _iso(as_of)}
                    self._record(
                        {"type": "stop_triggered", "symbol": symbol, "trigger_close": _iso(as_of)}
                    )
            else:  # defensive: engine opened a position out of band
                self._record(
                    {"type": "entry_collision", "symbol": symbol, "closed_at": _iso(as_of)}
                )
                state.pending_entry = None

        if state.pending_stop is not None:
            if has_position and not fired_entry_this_candle:
                trigger_close = state.pending_stop["trigger_close"]
                state.pending_stop = None
                self._record(
                    {
                        "type": "stop_fired",
                        "symbol": symbol,
                        "trigger_close": trigger_close,
                        # fill_time is the exit candle's close; the fill price
                        # is that candle's OPEN (next open after the trigger).
                        "fill_time": _iso(as_of),
                        "exit_open": str(candle_open),
                    }
                )
                stop_action: ClosePosition | None = ClosePosition(
                    symbol=symbol,
                    reason=f"{STOP_EXIT_REASON}_trig={trigger_close}",
                    price=candle_open,
                )
            elif not has_position and not fired_entry_this_candle:
                # Resting TPs already closed the position; nothing to stop.
                self._record(
                    {
                        "type": "stop_redundant_tp_closed",
                        "symbol": symbol,
                        "trigger_close": state.pending_stop["trigger_close"],
                        "closed_at": _iso(as_of),
                    }
                )
                state.pending_stop = None
                stop_action = None
            else:
                stop_action = None
        else:
            stop_action = None

        # The Core signal state machine advances on EVERY candle — including
        # exit-firing candles — independent of any open position, so re-arm
        # stays deterministic and the exact-15m cadence is never broken.
        self._evaluate_core(symbol, state, as_of, has_position or fired_entry_this_candle)

        # Close-based strategy stop: fully closed M15 Close < current EMA21
        # (strict; wicks never trigger).  Detection here, exit at next open.
        if (
            has_position
            and not fired_entry_this_candle
            and stop_action is None
            and state.pending_stop is None
        ):
            row = frame.iloc[abs_idx]
            if _decimal(row["close"]) < _decimal(row["ema21"]):
                state.pending_stop = {"trigger_close": _iso(as_of)}
                self._record(
                    {"type": "stop_triggered", "symbol": symbol, "trigger_close": _iso(as_of)}
                )

        if stop_action is not None:
            return self._analysis_result(symbol, state, [stop_action])
        return self._analysis_result(symbol, state, [DoNothing()])

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _fire_entry(
        self, symbol: str, state: _SymbolState, candle_open: Decimal, as_of
    ) -> None:
        pending = state.pending_entry
        assert pending is not None
        state.pending_entry = None
        levels = pending["levels"]
        self._record(
            {
                "type": "entry_fired",
                "symbol": symbol,
                "event_type": pending["event_type"],
                "sequence": pending["sequence"],
                "signal_close": pending["signal_close"],
                # fill_time is the entry candle's close; the fill price is
                # that candle's OPEN (next open after the signal close).
                "fill_time": _iso(as_of),
                "entry_open": str(candle_open),
                "reference_entry": levels["reference_entry"],
                "reference_stop": levels["reference_stop"],
                "tp1": levels["tp1"],
                "tp2": levels["tp2"],
                "tp3": levels["tp3"],
            }
        )
        state.pending_fire = {
            "symbol": symbol,
            "pending": pending,
            "open": candle_open,
            "as_of": as_of,
        }

    def _evaluate_core(
        self, symbol: str, state: _SymbolState, as_of, position_open: bool
    ) -> None:
        try:
            context = build_point_in_time_context(
                symbol=symbol,
                as_of=as_of,
                m15=self._frames.alt_m15[symbol],
                alt_h1=self._frames.alt_h1[symbol],
                btc_h1=self._frames.btc_h1,
                btc_h4=self._frames.btc_h4,
            )
        except ValueError as exc:  # ambiguous/gapped data fails closed
            raise ValueError(f"Core V2.1 point-in-time failure at {as_of}: {exc}") from exc
        if context is None:  # warm-up/readiness incomplete: state unchanged
            state.not_ready += 1
            return
        # Locked readiness gate (same function the audit replay uses): NaN or
        # missing indicator/context rows are NOT_READY warm-up, never evaluated.
        if _readiness_reasons(context):
            state.not_ready += 1
            return
        try:
            evaluation_input = _to_core_evaluation_input(context)
        except Exception as exc:  # corrupt post-readiness data fails closed
            raise ValueError(
                f"Core V2.1 evaluation input invalid at {as_of}: {exc}"
            ) from exc
        result = evaluate_core_v2_1(evaluation_input, state.core)
        state.core = result.next_state
        state.evaluated += 1
        decision = result.decision
        if decision.event is None:
            return
        self._seq += 1
        event = decision.event
        record: dict[str, Any] = {
            "type": "signal",
            "sequence": self._seq,
            "symbol": symbol,
            "closed_at": _iso(event.closed_at),
            "kind": decision.kind.value,
            "event_type": event.event_type.value,
        }
        if event.trade_levels is not None:
            levels = event.trade_levels
            record["levels"] = {
                "reference_entry": str(levels.reference_entry),
                "reference_stop": str(levels.reference_stop),
                "risk_1r": str(levels.risk_1r),
                "tp1": str(levels.tp1),
                "tp2": str(levels.tp2),
                "tp3": str(levels.tp3),
            }
        self._record(record)
        if decision.kind in ENTRY_EVENT_KINDS:
            assert event.trade_levels is not None
            if position_open or state.pending_entry is not None:
                self._record(
                    {
                        "type": "overlap_skipped",
                        "symbol": symbol,
                        "sequence": self._seq,
                        "event_type": event.event_type.value,
                        "trigger_close": _iso(event.closed_at),
                    }
                )
            else:
                levels = event.trade_levels
                state.pending_entry = {
                    "sequence": self._seq,
                    "event_type": event.event_type.value,
                    "signal_close": _iso(event.closed_at),
                    "levels": {
                        "reference_entry": str(levels.reference_entry),
                        "reference_stop": str(levels.reference_stop),
                        "risk_1r": str(levels.risk_1r),
                        "tp1": str(levels.tp1),
                        "tp2": str(levels.tp2),
                        "tp3": str(levels.tp3),
                    },
                }

    def _pending_open_action(self, symbol: str, state: _SymbolState):
        fire = state.pending_fire
        if fire is None:
            return None
        state.pending_fire = None
        pending = fire["pending"]
        levels = pending["levels"]
        return OpenPosition(
            symbol=symbol,
            side=SIDE_BUY,
            entry_price=fire["open"],
            sl_price=None,  # no hard disaster stop (unresolved by design)
            soft_sl_price=_decimal(levels["reference_stop"]),
            tp_prices=[
                _decimal(levels["tp1"]),
                _decimal(levels["tp2"]),
                _decimal(levels["tp3"]),
            ],
            tp_allocations={"TP1": TP1_FRACTION, "TP2": TP2_OF_REMAINDER},
            lock_profit_price=None,
            signal_class=2,  # unused by backtest accounting; presentation default
            reason=(
                f"CORE_V2_1_{pending['event_type']}_"
                f"sig={pending['signal_close']}_seq={pending['sequence']}"
            ),
        )

    def _analysis_result(self, symbol: str, state: _SymbolState, actions) -> AnalysisResult:
        # A fired entry must be returned as the candle's action, not DoNothing.
        if state.pending_fire is not None:
            action = self._pending_open_action(symbol, state)
            assert action is not None
            return AnalysisResult(
                actions=[action], new_context=self._mirror_context(symbol, state)
            )
        return AnalysisResult(actions=actions, new_context=self._mirror_context(symbol, state))

    def _mirror_context(self, symbol: str, state: _SymbolState) -> ContextSnapshot:
        # Observability mirror only; _SymbolState on the instance is
        # authoritative because the engine resets contexts on full closes.
        return ContextSnapshot(
            state="SCANNING",
            meta={
                "core_v2_1": True,
                "core_state": state.core.to_dict(),
                "pending_entry": state.pending_entry,
                "pending_stop": state.pending_stop,
            },
        )

    def _record(self, record: dict[str, Any]) -> None:
        self.ledger.append(record)

    def finalize(self, last_closes: dict[str, str]) -> None:
        """Mark entries that never saw a next open as explicit NO_FILL_CANDLE."""
        for symbol, state in self._states.items():
            if state.pending_entry is not None:
                pending = state.pending_entry
                state.pending_entry = None
                self._record(
                    {
                        "type": "no_fill_candle",
                        "reason": "NO_FILL_CANDLE",
                        "symbol": symbol,
                        "sequence": pending["sequence"],
                        "event_type": pending["event_type"],
                        "trigger_close": pending["signal_close"],
                        "last_close": last_closes.get(symbol),
                    }
                )

    def not_ready_counts(self) -> dict[str, int]:
        return {symbol: st.not_ready for symbol, st in self._states.items() if st.not_ready}
