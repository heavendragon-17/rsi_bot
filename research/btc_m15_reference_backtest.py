"""Frozen offline reference backtest for the BTC M15 alert policies (engine).

Research-only, deterministic, and offline. This module does not touch live
strategy rules, configuration, execution, Telegram, or the network. It reuses
the verified signal research in :mod:`research.btc_m15_signal_diagnostic` and
:mod:`app.backtest.btc_research_phase1` for signal generation and exact native
candle arithmetic, and the repository's trade-statistics helper for reporting.
Drawdown is computed by a research-local helper in this module (the shared
``app`` helper is not used here) so a new equity peak always resets pointwise
drawdown to zero. Charts, packet writing, and the CLI live in
:mod:`research.btc_m15_reference_reporting`.

Two policies are traded on one frozen protocol:

``A_emitted_alerts``
    The M15 alerts the existing replay already emits, unchanged: fresh RSI21
    EMA9/WMA45 bullish cross plus the M15/H1/H4 close-above-EMA21 gates, with
    the replay's one-hour per-timeframe cooldown.

``B_gate_cooldown``
    The same three price-above-EMA21 gates **without** the RSI crossover, with
    its **own independent** one-hour signal cooldown. This is deliberately not
    the descriptive ``gate_ready_no_cross`` population from the M15 diagnostic,
    which had no cooldown at all and therefore contained thousands of
    overlapping bars.

Execution is a delayed candle-price proxy, not a fill model: entry is the open
of the native M5 candle whose open time is the first 5-minute boundary strictly
after the signal-close timestamp, and exit is exactly 60 minutes later at that
candle's open. The scheduled entry boundary is derived arithmetically from the
signal time alone; if that exact native M5 candle is absent from the input, the
signal is recorded as ``MISSING_ENTRY_CANDLE`` and no later candle is
substituted. There is no stop-loss, take-profit, trailing rule, or alternative
horizon. Every number produced here is historical development evidence on an
already-examined window.

Version history
---------------
``btc-m15-reference-backtest-v1``
    Initial frozen protocol. Its wording said "first existing native M5 candle
    strictly after the signal close" while the missing-data section said "no
    later candle is substituted". Those two sentences contradict each other when
    the exact scheduled candle is missing but a later candle exists: the first
    sentence can be read as "jump forward", the second as "skip explicitly".
    Version 1 implemented the jump-forward reading, reused the shared drawdown
    helper positionally through a timestamp-only map, and marked open equity as
    ``cash + full market value`` while ``cash`` still contained the reserved
    principal.
``btc-m15-reference-backtest-v2`` (this module)
    Research-only accounting and reporting correction. No strategy, indicator,
    horizon, cost, sizing-constant, cooldown, or production change. The
    corrected contract is: the scheduled entry is the arithmetic
    ``floor(signal, 5m) + 5m`` boundary; a missing exact entry candle is an
    explicit skip; a deferred entry is priced at its actual deferred timestamp;
    open equity is ``wallet cash + unrealized P&L``; drawdown is research-local
    and positional; unresolved positions retain paid fees and exposure and are
    never presented as flat. A separately labelled full-opportunity-set
    diagnostic (same signals, rules, and costs, no cash admission, no equity
    compounding) is reported alongside the unchanged capital-constrained
    account.
"""

from __future__ import annotations

import bisect
import heapq
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.backtest import btc_research_phase1 as phase1
from app.backtest.statistics.metrics import compute_core_metrics
from app.core.constants import DEFAULT_MAKER_FEE, DEFAULT_TAKER_FEE
from app.trading.strategy.btc_rsi_cross_alert.models import PREPARATION_READY
from research import btc_m15_signal_diagnostic as diagnostic

VERSION = "btc-m15-reference-backtest-v2"
PREVIOUS_VERSION = "btc-m15-reference-backtest-v1"
TIMEFRAME = diagnostic.TIMEFRAME
EXECUTION_TIMEFRAME = "5m"
M5_MINUTES = 5
POLICIES = ("A_emitted_alerts", "B_gate_cooldown")
WINDOW_START = datetime(2022, 8, 28, tzinfo=UTC)
WINDOW_END = datetime(2026, 8, 27, 23, 59, 59, 999999, tzinfo=UTC)
WINDOW_SECONDS = (WINDOW_END - WINDOW_START).total_seconds()
SIGNAL_COOLDOWN = timedelta(hours=1)
SCHEDULED_HOLD = timedelta(minutes=60)
INITIAL_EQUITY_USDT = 10_000.0
ENTRY_NOTIONAL_USDT = 1_000.0
FEE_RATES = (0.0, DEFAULT_MAKER_FEE, DEFAULT_TAKER_FEE)
SLIPPAGE_RATES = (0.0, 0.0001, 0.0005)
HEADLINE_FEE_RATE = DEFAULT_TAKER_FEE
HEADLINE_SLIPPAGE_RATE = 0.0001
FUNDING_STATUS = "EXCLUDED_BY_DESIGN"
#: Required label for every cost-adjusted number produced by this experiment.
COST_ADJUSTED_LABEL = "After assumed trading fees and slippage, before funding."
TRADE_OK = "CLOSED_AT_SCHEDULED_EXIT"
TRADE_UNRESOLVED_EXIT = "UNRESOLVED_MISSING_EXIT_CANDLE"
TRADE_OPEN_AT_END = "OPEN_AT_EVALUATION_END"
SKIP_REASONS = (
    "MISSING_ENTRY_CANDLE",
    "ENTRY_AFTER_EVALUATION_END",
    "POSITION_OPEN_AND_DEFERRAL_SLOT_OCCUPIED",
    "INSUFFICIENT_FREE_CASH",
    "DEFERRED_ENTRY_NOT_REALIZED",
)
ACTION_FIELDS = (
    "policy",
    "sequence",
    "kind",
    "signal_close_at",
    "scheduled_at",
    "actual_at",
    "price",
    "quantity",
    "reason",
    "trade_id",
)
TRADE_FIELDS = (
    "policy",
    "trade_id",
    "sequence",
    "signal_close_at",
    "entry_at",
    "exit_at",
    "hold_minutes",
    "entry_open_price",
    "exit_open_price",
    "entry_fill_price",
    "exit_fill_price",
    "quantity",
    "entry_notional",
    "exit_notional",
    "entry_fee_usdt",
    "exit_fee_usdt",
    "gross_pnl",
    "friction_pnl",
    "fee_pnl",
    "net_pnl",
    "net_return_pct",
    "status",
)
EQUITY_FIELDS = (
    "policy",
    "timestamp",
    "state",
    "mark_price",
    "quantity",
    "cash",
    "reserved",
    "unrealized_pnl",
    "equity",
    "drawdown_pct",
)

PROTOCOL: dict[str, Any] = {
    "protocol_version": VERSION,
    "frozen_before_performance": True,
    "alpha_assessment": "NOT_ASSESSED",
    "evidence_role": "HISTORICAL_DEVELOPMENT_EVIDENCE",
    "evaluation_window": {
        "start_utc": phase1._utc_iso(WINDOW_START),
        "end_utc": phase1._utc_iso(WINDOW_END),
        "signal_semantics": "M15 trigger-close timestamps inside the window, inclusive",
        "entry_bounded_by_window_end": True,
        "exit_may_complete_past_window_end": True,
        "note": (
            "Same documented Phase 1 requested window, and wider than the M15 diagnostic's matched "
            "descriptive window so both policies face an identical opportunity set."
        ),
    },
    "policies": {
        "A_emitted_alerts": "Emitted replay M15 alerts, unchanged; the replay's one-hour per-timeframe cooldown is already applied.",
        "B_gate_cooldown": (
            "Preparation-ready M15 bars with M15, H1 and H4 closes all strictly above native EMA21, no RSI "
            "crossover requirement, with an independent one-hour signal cooldown initialised at the window start."
        ),
        "cooldown_rule": "A bar is accepted when its close is at least 60 minutes after the previously accepted close; identical to the replay's suppression rule.",
        "difference_from_diagnostic_population": (
            "The M15 diagnostic's gate_ready_no_cross population had NO cooldown and is not "
            "policy B. It counted 38,292 bars over the diagnostic's earlier matched window "
            "(2022-08-30T04:15:00Z to 2026-08-27T15:00:00Z, 140,012 candidate bars), whereas "
            "the same cooldown-free gate rule yields 38,335 bars over this experiment's wider "
            "evaluation window (2022-08-28T00:00:00Z to 2026-08-27T23:59:59.999999Z, 140,256 "
            "candidate bars). Policy B applies the one-hour cooldown, so it is a much smaller "
            "signal set whose accepted bars are at least 60 minutes apart."
        ),
        "signal_generation_independent_of_positions": True,
    },
    "execution": {
        "entry": (
            "Open of the native M5 candle whose open time is the first 5-minute boundary strictly after the "
            "signal-close timestamp (floor(signal, 5m) + 5m), derived arithmetically from the signal time alone. "
            "If that exact candle is absent, the signal is skipped as MISSING_ENTRY_CANDLE; no later candle is substituted."
        ),
        "entry_correction_note": (
            "Version 1 said 'first existing native M5 candle strictly after the signal close', which contradicts "
            "'no later candle is substituted' when the exact scheduled candle is missing but a later candle exists. "
            "Version 1 implemented the jump-forward reading. Version 2 implements the skip-explicitly reading and "
            "supersedes the version-1 wording."
        ),
        "exit": "Open of the native M5 candle whose open time equals the entry open time plus exactly 60 minutes.",
        "deferred_pricing_correction_note": (
            "Version 1 reused the originally scheduled candle index when a deferred entry filled at the open "
            "position's exit time. Version 2 resolves the fill from the actual deferred timestamp's candle and "
            "never reuses the original index."
        ),
        "proxies": "Delayed candle-price proxies, not guaranteed fills.",
        "no_stop_loss_take_profit_trailing_or_alternative_horizon": True,
        "one_active_position_per_policy": True,
        "pyramiding": False,
        "same_timestamp_ordering": "Scheduled exits are processed before scheduled entries.",
        "while_open": "A signal arriving while a position is open queues at most one deferred entry at that position's scheduled exit time; further signals are skipped.",
        "overlapping_exposure": "Never permitted (capital-constrained account view only; the separate full-opportunity diagnostic evaluates each signal independently and permits overlapping hypothetical exposure).",
    },
    "accounting": {
        "initial_equity_usdt": INITIAL_EQUITY_USDT,
        "fixed_entry_notional_usdt": ENTRY_NOTIONAL_USDT,
        "simulation_constants_note": "Research constants, not live sizing recommendations.",
        "convention": (
            "Wallet balance plus unrealized P&L. The ledger's cash field is the wallet balance after already-paid "
            "entry fees (it still contains the reserved principal as part of the wallet); reserved is a memo of "
            "deployed cost (quantity * entry_fill_price); unrealized is (mark - entry_fill) * quantity using the "
            "available native M5 close as the mark; equity is cash + unrealized. Equivalently, available cash + "
            "reserved + unrealized. The two wordings are the same number; they are never mixed with "
            "cash + full market value. Opening or closing a flat-price, zero-cost position leaves equity unchanged. "
            "Already-paid fees enter wallet accounting exactly once."
        ),
        "accounting_correction_note": (
            "Version 1 marked open equity as cash + quantity * mark while cash still contained the reserved "
            "principal, overstating open equity by one fixed entry notional (1,000 USDT at zero costs). "
            "Version 2 marks open equity as cash + unrealized and supersedes the version-1 curve."
        ),
        "unresolved": (
            "An unresolved position retains its paid entry fee in cash and its known exposure in reserved, "
            "reports unrealized as unknown (no price is substituted), and reports equity as the fee-adjusted cash "
            "floor (cash only, unrealized excluded). Its state is UNRESOLVED, never FLAT, and it is excluded from "
            "realized P&L. The floor is not comparable to a flat equity point."
        ),
        "capital_reservation": "At entry, reserved = quantity * entry_fill_price; cash must cover reserved plus the entry fee. Reserved returns to cash at exit.",
        "insufficient_capital": (
            "Entry is skipped with reason INSUFFICIENT_FREE_CASH when the wallet cannot afford the next fixed-size "
            "entry (reserved plus entry fee). This is inability to afford the next entry, not necessarily bankruptcy: "
            "the wallet can remain positive but below the fixed entry threshold. The signal is never silently dropped."
        ),
        "pnl_components": (
            "gross_pnl uses zero-cost open prices; friction_pnl is the slippage-only difference between fill "
            "and open prices; fee_pnl is the negative sum of both sides' fees; net_pnl is their sum. The three "
            "components are disjoint and never double counted."
        ),
        "quantity": "quantity = ENTRY_NOTIONAL_USDT / entry_fill_price, so deployed entry notional is the fixed research constant.",
        "marking": (
            "Equity is marked at every available native M5 close while a position is open (close prices, the "
            "available price at that mark), and at every exit at the exit open. Marks never look ahead of their timestamp."
        ),
        "drawdown": (
            "Research-local pointwise drawdown over the equity rows in deterministic order: running peak starts at "
            "initial equity, peak updates on a new high, and drawdown is (peak - equity) / peak * 100 with a new peak "
            "always yielding zero. Rows sharing a timestamp keep their individual identities in order; they are never "
            "collapsed through a timestamp-only map. Timestamps are monotonic: exits may complete past the evaluation "
            "window end and no window-end row is appended behind them."
        ),
    },
    "comparison": {
        "account_view": (
            "Capital-constrained, single-position, non-compounding account with INSUFFICIENT_FREE_CASH admission. "
            "This is the executable-proxy view and the only view compounded into an account-equity curve."
        ),
        "full_opportunity_diagnostic": (
            "Separately labelled hypothetical diagnostic over the same frozen signals, entry/exit rules, and cost "
            "scenarios, without cash-based admission and without position-overlap blocking. Each signal is evaluated "
            "independently; hypothetical P&L components are summed without compounding into an account-equity curve. "
            "This diagnostic is not an executable account, not a tradable history, and not like-for-like with the account."
        ),
        "per_trade_note": (
            "Dividing account totals by executed trades does not make results capital-independent or automatically "
            "like-for-like. The capital stop truncates the account's trade set (only early affordable entries are "
            "realized), so per-trade averages are conditional on affordability and timing, not a full-opportunity average."
        ),
    },
    "costs": {
        "fee_rates_per_side": list(FEE_RATES),
        "slippage_rates_per_side": list(SLIPPAGE_RATES),
        "grid_size": len(FEE_RATES) * len(SLIPPAGE_RATES),
        "headline_scenario": {"fee_rate_per_side": HEADLINE_FEE_RATE, "slippage_rate_per_side": HEADLINE_SLIPPAGE_RATE},
        "fee_basis": "Binance USD-M defaults from app/core/constants.py; illustrative research assumptions, not verified account fees.",
        "frozen_note": "The full grid was frozen before any performance number was computed, and every scenario is reported.",
    },
    "missing_data": {
        "missing_entry_candle": "Skipped with reason MISSING_ENTRY_CANDLE; no later candle is substituted.",
        "missing_exit_candle": "Reported as UNRESOLVED_MISSING_EXIT_CANDLE; no price is substituted and the position stays open, blocking new exposure.",
        "unresolved_trades": "Excluded from realized P&L and reported separately with an explicit count.",
        "evaluation_end": "A position still open at the window end is labelled OPEN_AT_EVALUATION_END, marked but not force-closed, and excluded from realized P&L.",
        "no_future_information": "Accepting a trade never depends on any data after its scheduled execution time.",
    },
    "funding": {
        "status": FUNDING_STATUS,
        "cost_adjusted_label": COST_ADJUSTED_LABEL,
        "decision": "Perpetual funding is deliberately excluded from this offline reference backtest; no funding data was downloaded and no funding accounting was implemented.",
        "not_zero": "Excluded funding must never be read as observed zero funding. Real funding could have been a cost or a credit, and it is not measured here.",
        "entry_exit_unchanged": "Entry and exit rules were not adjusted to dodge or capture funding settlements.",
        "consequence": "Every cost-adjusted result is 'After assumed trading fees and slippage, before funding.' and is not fully net profit.",
    },
}


# ---------------------------------------------------------------------------
# Reused signal research
# ---------------------------------------------------------------------------
def load_signal_inputs(baseline_run: Path) -> tuple[dict[str, Any], dict[str, Any], phase1.ValidatedInputs]:
    """Parent packet, its summary plus M15 rows, and hash-checked native frames."""

    parent, summary, rows = diagnostic.load_parent(baseline_run)
    inputs = diagnostic.source_inputs(parent)
    return parent, {**summary, "m15_rows": rows}, inputs


def policy_a_signals(parent_rows: pd.DataFrame) -> list[datetime]:
    """Emitted replay M15 alerts inside the frozen window, unchanged."""

    times = [
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        for value in diagnostic.signal_close_times(parent_rows)
    ]
    return [value for value in times if WINDOW_START <= value <= WINDOW_END]


def gate_bar_times(scan: pd.DataFrame) -> list[datetime]:
    """Preparation-ready M15 bars passing all three price gates, before cooldown."""

    eligible = scan.loc[scan.preparation_reason.eq(PREPARATION_READY)]
    gated = eligible.loc[eligible.price_gates_pass.fillna(False).astype(bool)]
    return pd.to_datetime(gated.trigger_close_at, utc=True).dt.to_pydatetime().tolist()


def cross_and_gate_bar_times(scan: pd.DataFrame) -> list[datetime]:
    """Gate-passing M15 bars that also show the fresh RSI crossover."""

    eligible = scan.loc[scan.preparation_reason.eq(PREPARATION_READY)]
    crossed = eligible.fresh_bullish_cross.fillna(False).astype(bool)
    gated = eligible.price_gates_pass.fillna(False).astype(bool)
    both = eligible.loc[crossed & gated]
    return pd.to_datetime(both.trigger_close_at, utc=True).dt.to_pydatetime().tolist()


def policy_b_signals(scan: pd.DataFrame) -> list[datetime]:
    """Gate-passing M15 bars under an independent one-hour signal cooldown."""

    return apply_cooldown(gate_bar_times(scan), SIGNAL_COOLDOWN)


def apply_cooldown(close_times: Iterable[datetime], cooldown: timedelta) -> list[datetime]:
    """Accept a close only when it is at least ``cooldown`` after the last accepted one."""

    accepted: list[datetime] = []
    previous: datetime | None = None
    for close_time in sorted(close_times):
        if previous is None or close_time >= previous + cooldown:
            accepted.append(close_time)
            previous = close_time
    return accepted


def reconstruct_policy_a(scan: pd.DataFrame, emitted: Sequence[datetime]) -> dict[str, Any]:
    """Check that an independent cooldown over cross-and-gate bars reproduces the replay.

    Policy A is the crossover rule, not the bare gate rule, so the reconstruction
    must start from bars that show both the fresh RSI crossover and the gates.
    """

    rebuilt = set(apply_cooldown(cross_and_gate_bar_times(scan), SIGNAL_COOLDOWN))
    expected = set(emitted)
    return {
        "matches": rebuilt == expected,
        "emitted_count": len(expected),
        "reconstructed_count": len(rebuilt),
        "cross_and_gate_bars_before_cooldown": len(cross_and_gate_bar_times(scan)),
        "only_emitted": sorted(phase1._utc_iso(value) for value in expected - rebuilt)[:20],
        "only_reconstructed": sorted(phase1._utc_iso(value) for value in rebuilt - expected)[:20],
    }


# ---------------------------------------------------------------------------
# Scheduling and research-local drawdown
# ---------------------------------------------------------------------------
def scheduled_m5_open_after(signal_close_at: datetime) -> datetime:
    """Return the first native M5 boundary strictly after ``signal_close_at``.

    The boundary is derived arithmetically from the signal time alone
    (``floor(signal, 5m) + 5m``) and never depends on which candles happen to be
    present. Native M5 opens sit on exact 5-minute UTC boundaries, so flooring
    the minute field and adding five minutes yields the scheduled entry even
    across hour and day rollovers. Callers must then require that exact candle
    via :meth:`M5Grid.open_index` and record ``MISSING_ENTRY_CANDLE`` when it
    is absent.
    """

    floored = signal_close_at.replace(second=0, microsecond=0)
    floored = floored.replace(minute=(floored.minute // M5_MINUTES) * M5_MINUTES)
    return floored + timedelta(minutes=M5_MINUTES)


def research_drawdown_curve(balances: Sequence[float], initial_balance: float) -> list[float]:
    """Pointwise drawdown percentages in order, with new peaks resetting to zero.

    Research-local correction: unlike the shared ``app`` helper, the running
    peak is applied before the point's own drawdown is computed, so balances
    such as ``[100, 90, 110]`` yield ``[0, 10, 0]``. Rounds to 4 decimals to
    match the packet's committed precision.
    """

    peak = float(initial_balance)
    drawdowns: list[float] = []
    for balance in balances:
        value = float(balance)
        if value > peak:
            peak = value
        if peak <= 0:
            drawdowns.append(0.0)
        elif value >= peak:
            drawdowns.append(0.0)
        else:
            drawdowns.append(round((peak - value) / peak * 100.0, 4))
    return drawdowns


def calculate_research_portfolio_drawdown(
    equity_curve: Sequence[dict[str, Any]], initial_balance: float
) -> dict[str, Any]:
    """Research-local portfolio drawdown over ordered ``{date, balance}`` points.

    Positional (never keyed by timestamp alone) so observations sharing a
    timestamp keep their individual identities in deterministic order.
    """

    points = list(equity_curve)
    if not points:
        return {
            "max_drawdown_pct": 0.0,
            "max_drawdown_value": 0.0,
            "drawdown_curve": [],
            "max_dd_duration": 0,
            "avg_drawdown_pct": 0.0,
        }
    balances = [float(point["balance"]) for point in points]
    curve = research_drawdown_curve(balances, initial_balance)
    peak = float(initial_balance)
    max_dd = 0.0
    max_dd_value = 0.0
    current_duration = 0
    max_duration = 0
    positives: list[float] = []
    dd_curve: list[dict[str, Any]] = []
    for point, dd_pct in zip(points, curve, strict=True):
        value = float(point["balance"])
        if value > peak:
            peak = value
        if dd_pct > 0:
            positives.append(dd_pct)
            current_duration += 1
        else:
            if current_duration > 0:
                max_duration = max(max_duration, current_duration)
            current_duration = 0
        fraction = dd_pct / 100.0
        if fraction > max_dd:
            max_dd = fraction
            max_dd_value = peak - value
        dd_curve.append({"date": point["date"], "drawdown": dd_pct})
    if current_duration > 0:
        max_duration = max(max_duration, current_duration)
    return {
        "max_drawdown_pct": max_dd * 100.0,
        "max_drawdown_value": max_dd_value,
        "drawdown_curve": dd_curve,
        "max_dd_duration": max_duration,
        "avg_drawdown_pct": (sum(positives) / len(positives)) if positives else 0.0,
    }


# ---------------------------------------------------------------------------
# Execution grid
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class M5Grid:
    """Native M5 candle opens used for scheduled execution."""

    open_times: tuple[datetime, ...]
    open_prices: np.ndarray
    close_times: tuple[datetime, ...]
    close_prices: np.ndarray

    @classmethod
    def from_frame(cls, frame: pd.DataFrame) -> M5Grid:
        source = phase1._forward_index(frame, EXECUTION_TIMEFRAME)
        duration = timedelta(minutes=M5_MINUTES)
        return cls(
            open_times=tuple(value.to_pydatetime() - duration for value in source.close_times),
            open_prices=frame["open"].to_numpy(dtype=float),
            close_times=tuple(value.to_pydatetime() for value in source.close_times),
            close_prices=source.closes,
        )

    def first_open_after(self, moment: datetime) -> int | None:
        """Legacy jump-forward lookup kept for compatibility; not used for scheduling.

        Version 1 scheduling used this helper, which silently jumps to a later
        candle when the exact scheduled boundary is missing. Version 2
        scheduling uses :func:`scheduled_m5_open_after` plus :meth:`open_index`
        and records ``MISSING_ENTRY_CANDLE`` instead.
        """

        index = bisect.bisect_right(self.open_times, moment)
        return index if index < len(self.open_times) else None

    def open_index(self, moment: datetime) -> int | None:
        index = bisect.bisect_left(self.open_times, moment)
        if index < len(self.open_times) and self.open_times[index] == moment:
            return index
        return None

    def close_index_at_or_after(self, moment: datetime) -> int | None:
        index = bisect.bisect_left(self.close_times, moment)
        return index if index < len(self.close_times) else None


@dataclass
class _Position:
    trade_id: str
    sequence: int
    signal_close_at: datetime
    entry_at: datetime
    entry_open_index: int
    scheduled_exit_at: datetime
    quantity: float
    entry_fill_price: float
    entry_fee: float


@dataclass
class PolicyRun:
    """One policy's ledger under one cost scenario."""

    policy: str
    fee_rate: float
    slippage_rate: float
    actions: list[dict[str, Any]] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)
    equity: list[dict[str, Any]] = field(default_factory=list)
    unresolved: list[dict[str, Any]] = field(default_factory=list)
    final_cash: float = INITIAL_EQUITY_USDT

    @property
    def executed(self) -> list[dict[str, Any]]:
        return [trade for trade in self.trades if trade["status"] == TRADE_OK]


# ---------------------------------------------------------------------------
# Deterministic execution and accounting
# ---------------------------------------------------------------------------
class _Simulator:
    """One policy's chronological position, cash, and action ledger."""

    def __init__(self, policy: str, grid: M5Grid, *, fee_rate: float, slippage_rate: float) -> None:
        self.run = PolicyRun(policy=policy, fee_rate=fee_rate, slippage_rate=slippage_rate)
        self.grid = grid
        self.fee_rate = fee_rate
        self.slippage_rate = slippage_rate
        self.cash = INITIAL_EQUITY_USDT
        self.reserved = 0.0
        self.position: _Position | None = None
        self.pending: list[tuple[datetime, int, int, Any]] = []
        self._counter = 0

    def _action(self, kind: str, sequence: int, **values: Any) -> None:
        row = {"policy": self.run.policy, "sequence": sequence, "kind": kind}
        row.update({name: values.get(name) for name in ACTION_FIELDS[3:]})
        self.run.actions.append(row)

    def _push(self, moment: datetime, priority: int, payload: Any) -> None:
        self._counter += 1
        heapq.heappush(self.pending, (moment, priority, self._counter, payload))

    def schedule(self, sequence: int, close_time: datetime) -> tuple[datetime, int] | None:
        """Resolve the scheduled entry for one signal, or record an explicit skip.

        The scheduled entry is the arithmetic native M5 boundary strictly after
        the signal close (independent of which candles are present). Only the
        exact candle at that boundary may be used; a missing exact candle is an
        explicit ``MISSING_ENTRY_CANDLE`` skip, never a silent jump forward.
        """

        entry_at = scheduled_m5_open_after(close_time)
        index = self.grid.open_index(entry_at)
        if index is None:
            self._action(
                "ENTRY_SKIPPED",
                sequence,
                signal_close_at=phase1._utc_iso(close_time),
                scheduled_at=phase1._utc_iso(entry_at),
                reason=SKIP_REASONS[0],
            )
            return None
        if entry_at > WINDOW_END:
            self._action(
                "ENTRY_SKIPPED",
                sequence,
                signal_close_at=phase1._utc_iso(close_time),
                scheduled_at=phase1._utc_iso(entry_at),
                reason=SKIP_REASONS[1],
            )
            return None
        return entry_at, index

    def try_enter(self, sequence: int, close_time: datetime, entry_at: datetime, index: int) -> bool:
        open_price = float(self.grid.open_prices[index])
        entry_fill = open_price * (1.0 + self.slippage_rate)
        quantity = ENTRY_NOTIONAL_USDT / entry_fill
        entry_fee = quantity * entry_fill * self.fee_rate
        if self.cash < quantity * entry_fill + entry_fee:
            self._action(
                "ENTRY_SKIPPED",
                sequence,
                signal_close_at=phase1._utc_iso(close_time),
                scheduled_at=phase1._utc_iso(entry_at),
                price=open_price,
                reason=SKIP_REASONS[3],
            )
            return False
        self.cash -= entry_fee
        self.reserved = quantity * entry_fill
        self._counter += 1
        trade_id = f"{self.run.policy}-T{sequence:05d}-{self._counter:05d}"
        scheduled_exit = entry_at + SCHEDULED_HOLD
        self.position = _Position(
            trade_id=trade_id,
            sequence=sequence,
            signal_close_at=close_time,
            entry_at=entry_at,
            entry_open_index=index,
            scheduled_exit_at=scheduled_exit,
            quantity=quantity,
            entry_fill_price=entry_fill,
            entry_fee=entry_fee,
        )
        self._action(
            "ENTRY_FILLED",
            sequence,
            signal_close_at=phase1._utc_iso(close_time),
            scheduled_at=phase1._utc_iso(entry_at),
            actual_at=phase1._utc_iso(entry_at),
            price=entry_fill,
            quantity=quantity,
            trade_id=trade_id,
        )
        if self.grid.open_index(scheduled_exit) is not None:
            self._push(scheduled_exit, 0, trade_id)
        return True

    def mark_unresolved(self, position: _Position, exit_at: datetime, status: str) -> None:
        """Record an explicitly unresolved trade and never substitute a price."""

        self.run.unresolved.append(self._unresolved_row(position, status, exit_at))
        self._action(
            "TRADE_UNRESOLVED",
            position.sequence,
            signal_close_at=phase1._utc_iso(position.signal_close_at),
            scheduled_at=phase1._utc_iso(exit_at),
            reason=status,
            trade_id=position.trade_id,
        )

    def close(self, trade_id: str, exit_at: datetime) -> None:
        position = self.position
        if position is None or position.trade_id != trade_id:
            raise ValueError("exit event does not match the open position")
        exit_index = self.grid.open_index(exit_at)
        if exit_index is None:
            self.mark_unresolved(position, exit_at, TRADE_UNRESOLVED_EXIT)
            return
        quantity = position.quantity
        entry_open = float(self.grid.open_prices[position.entry_open_index])
        exit_open = float(self.grid.open_prices[exit_index])
        exit_fill = exit_open * (1.0 - self.slippage_rate)
        exit_notional = quantity * exit_fill
        exit_fee = exit_notional * self.fee_rate
        gross_pnl = (exit_open - entry_open) * (ENTRY_NOTIONAL_USDT / entry_open)
        realized_price_pnl = (exit_fill - position.entry_fill_price) * quantity
        friction_pnl = realized_price_pnl - gross_pnl
        fee_pnl = -(position.entry_fee + exit_fee)
        net_pnl = gross_pnl + friction_pnl + fee_pnl
        self.cash += realized_price_pnl - exit_fee
        self.reserved = 0.0
        self.run.trades.append(
            {
                "policy": self.run.policy,
                "trade_id": trade_id,
                "sequence": position.sequence,
                "signal_close_at": phase1._utc_iso(position.signal_close_at),
                "entry_at": phase1._utc_iso(position.entry_at),
                "exit_at": phase1._utc_iso(exit_at),
                "hold_minutes": (exit_at - position.entry_at).total_seconds() / 60.0,
                "entry_open_price": entry_open,
                "exit_open_price": exit_open,
                "entry_fill_price": position.entry_fill_price,
                "exit_fill_price": exit_fill,
                "quantity": quantity,
                "entry_notional": quantity * position.entry_fill_price,
                "exit_notional": exit_notional,
                "entry_fee_usdt": position.entry_fee,
                "exit_fee_usdt": exit_fee,
                "gross_pnl": gross_pnl,
                "friction_pnl": friction_pnl,
                "fee_pnl": fee_pnl,
                "net_pnl": net_pnl,
                "net_return_pct": net_pnl / ENTRY_NOTIONAL_USDT * 100.0,
                "status": TRADE_OK,
            }
        )
        self._action(
            "EXIT_FILLED",
            position.sequence,
            signal_close_at=phase1._utc_iso(position.signal_close_at),
            scheduled_at=phase1._utc_iso(exit_at),
            actual_at=phase1._utc_iso(exit_at),
            price=exit_fill,
            quantity=quantity,
            trade_id=trade_id,
        )
        self.position = None

    def _unresolved_row(self, position: _Position, status: str, exit_at: datetime) -> dict[str, Any]:
        return {
            "policy": self.run.policy,
            "trade_id": position.trade_id,
            "sequence": position.sequence,
            "signal_close_at": phase1._utc_iso(position.signal_close_at),
            "entry_at": phase1._utc_iso(position.entry_at),
            "exit_at": phase1._utc_iso(exit_at),
            "status": status,
            "quantity": position.quantity,
            "entry_fill_price": position.entry_fill_price,
            "entry_notional": position.quantity * position.entry_fill_price,
            "entry_fee_usdt": position.entry_fee,
        }


def simulate_policy(
    policy: str,
    signals: Sequence[datetime],
    grid: M5Grid,
    *,
    fee_rate: float,
    slippage_rate: float,
) -> PolicyRun:
    """Run one policy's frozen protocol with a single active position."""

    simulator = _Simulator(policy, grid, fee_rate=fee_rate, slippage_rate=slippage_rate)
    deferred: dict[str, Any] | None = None
    for sequence, close_time in enumerate(signals, start=1):
        # Every signal produces exactly one outcome action: ENTRY_FILLED (possibly
        # after a deferral), or ENTRY_SKIPPED with an explicit reason.
        scheduled = simulator.schedule(sequence, close_time)
        if scheduled is not None:
            simulator._push(scheduled[0], 1, (sequence, close_time, scheduled[1]))

    while simulator.pending:
        moment, priority, _, payload = heapq.heappop(simulator.pending)
        if priority == 0:
            simulator.close(payload, moment)
            if deferred is not None and deferred["target"] == moment and simulator.position is None:
                deferred_index = simulator.grid.open_index(moment)
                if deferred_index is None:
                    simulator._action(
                        "ENTRY_SKIPPED",
                        deferred["sequence"],
                        signal_close_at=phase1._utc_iso(deferred["close_time"]),
                        scheduled_at=phase1._utc_iso(moment),
                        reason=SKIP_REASONS[0],
                    )
                else:
                    simulator.try_enter(deferred["sequence"], deferred["close_time"], moment, deferred_index)
                deferred = None
            continue
        sequence, close_time, index = payload
        if simulator.position is None:
            simulator.try_enter(sequence, close_time, moment, index)
        elif deferred is None and simulator.position.scheduled_exit_at > moment:
            deferred = {
                "target": simulator.position.scheduled_exit_at,
                "sequence": sequence,
                "close_time": close_time,
            }
            simulator._action(
                "ENTRY_DEFERRED",
                sequence,
                signal_close_at=phase1._utc_iso(close_time),
                scheduled_at=phase1._utc_iso(moment),
                actual_at=phase1._utc_iso(simulator.position.scheduled_exit_at),
                reason="DEFERRED_TO_OPEN_POSITION_EXIT",
            )
        else:
            simulator._action(
                "ENTRY_SKIPPED",
                sequence,
                signal_close_at=phase1._utc_iso(close_time),
                scheduled_at=phase1._utc_iso(moment),
                reason=SKIP_REASONS[2],
            )

    if simulator.position is not None:
        position = simulator.position
        end_status = (
            TRADE_OPEN_AT_END
            if position.scheduled_exit_at > WINDOW_END
            else TRADE_UNRESOLVED_EXIT
        )
        simulator.mark_unresolved(position, position.scheduled_exit_at, end_status)
    if deferred is not None:
        simulator._action(
            "ENTRY_SKIPPED",
            deferred["sequence"],
            signal_close_at=phase1._utc_iso(deferred["close_time"]),
            scheduled_at=phase1._utc_iso(deferred["target"]),
            reason=SKIP_REASONS[4],
        )
    simulator.run.final_cash = simulator.cash
    entered = sum(action["kind"] == "ENTRY_FILLED" for action in simulator.run.actions)
    skipped = sum(action["kind"] == "ENTRY_SKIPPED" for action in simulator.run.actions)
    if entered + skipped != len(signals):
        raise ValueError(
            f"{policy}: {len(signals)} signals but {entered + skipped} entry outcomes"
        )
    return simulator.run


# ---------------------------------------------------------------------------
# Equity, exposure, turnover
# ---------------------------------------------------------------------------
def build_equity_curve(run: PolicyRun, grid: M5Grid) -> list[dict[str, Any]]:
    """Mark equity at every available native M5 close while open, plus every exit.

    Accounting convention (documented in ``PROTOCOL["accounting"]``):
    ``cash`` is the wallet balance after already-paid entry fees (it still
    contains the reserved principal as part of the wallet); ``reserved`` is a
    memo of deployed cost; ``unrealized_pnl`` uses the available native M5
    close as the mark; ``equity`` is ``cash + unrealized_pnl``. Opening or
    closing a flat-price, zero-cost position therefore leaves equity unchanged,
    and paid fees enter exactly once. Unresolved rows retain the paid entry fee
    in ``cash`` and the known exposure in ``reserved``, report ``unrealized``
    as unknown, and report ``equity`` as the fee-adjusted cash floor (never as
    ``FLAT``). Drawdown is research-local and positional so same-timestamp
    observations keep their identities in deterministic order, and timestamps
    stay monotonic when exits complete past the evaluation window end.
    """

    rows: list[dict[str, Any]] = [
        {
            "policy": run.policy,
            "timestamp": phase1._utc_iso(WINDOW_START),
            "state": "FLAT",
            "mark_price": None,
            "quantity": 0.0,
            "cash": INITIAL_EQUITY_USDT,
            "reserved": 0.0,
            "unrealized_pnl": 0.0,
            "equity": INITIAL_EQUITY_USDT,
        }
    ]
    cash = INITIAL_EQUITY_USDT
    for trade in run.executed:
        entry_at = datetime.fromisoformat(trade["entry_at"].replace("Z", "+00:00"))
        exit_at = datetime.fromisoformat(trade["exit_at"].replace("Z", "+00:00"))
        quantity = float(trade["quantity"])
        entry_fee = float(trade["entry_fee_usdt"])
        entry_fill = float(trade["entry_fill_price"])
        wallet_after_fee = cash - entry_fee
        start = grid.close_index_at_or_after(entry_at)
        if start is not None:
            for index in range(start, len(grid.close_times)):
                moment = grid.close_times[index]
                if moment >= exit_at:
                    break
                # Available price at the mark: the native M5 close, never the
                # entry open and never a future price.
                mark = float(grid.close_prices[index])
                unrealized = (mark - entry_fill) * quantity
                rows.append(
                    {
                        "policy": run.policy,
                        "timestamp": phase1._utc_iso(moment),
                        "state": "OPEN",
                        "mark_price": mark,
                        "quantity": quantity,
                        "cash": wallet_after_fee,
                        "reserved": float(trade["entry_notional"]),
                        "unrealized_pnl": unrealized,
                        "equity": wallet_after_fee + unrealized,
                    }
                )
        cash += float(trade["net_pnl"])
        rows.append(
            {
                "policy": run.policy,
                "timestamp": phase1._utc_iso(exit_at),
                "state": "FLAT",
                "mark_price": float(trade["exit_open_price"]),
                "quantity": 0.0,
                "cash": cash,
                "reserved": 0.0,
                "unrealized_pnl": 0.0,
                "equity": cash,
            }
        )
    window_end_iso = phase1._utc_iso(WINDOW_END)
    for unresolved in run.unresolved:
        quantity = float(unresolved["quantity"])
        entry_fill = float(unresolved["entry_fill_price"])
        if "entry_fee_usdt" in unresolved and unresolved["entry_fee_usdt"] is not None:
            entry_fee = float(unresolved["entry_fee_usdt"])
        else:  # Backwards compatibility with version-1 unresolved rows.
            entry_fee = quantity * entry_fill * float(run.fee_rate)
        reserved = float(unresolved.get("entry_notional", quantity * entry_fill))
        cash -= entry_fee
        scheduled_exit = datetime.fromisoformat(unresolved["exit_at"].replace("Z", "+00:00"))
        # Mark an open-at-end position at the window end; mark a missing-exit
        # position at its scheduled exit. Either way the timestamp never moves
        # backwards past the rows already appended.
        stamp = window_end_iso if scheduled_exit > WINDOW_END else phase1._utc_iso(scheduled_exit)
        rows.append(
            {
                "policy": run.policy,
                "timestamp": stamp,
                "state": "UNRESOLVED",
                "mark_price": None,
                "quantity": quantity,
                "cash": cash,
                "reserved": reserved,
                "unrealized_pnl": None,
                "equity": cash,
            }
        )
    if run.unresolved:
        # Never present an unresolved position as flat and never append a
        # window-end FLAT behind an exit that completed past the window end.
        pass
    elif rows[-1]["timestamp"] < window_end_iso:
        rows.append(
            {
                "policy": run.policy,
                "timestamp": window_end_iso,
                "state": "FLAT",
                "mark_price": None,
                "quantity": 0.0,
                "cash": run.final_cash,
                "reserved": 0.0,
                "unrealized_pnl": 0.0,
                "equity": run.final_cash,
            }
        )
    # Positional drawdown: same-timestamp observations keep their identities in
    # deterministic row order; no timestamp-only dictionary is used.
    curve = [{"date": row["timestamp"], "balance": row["equity"]} for row in rows]
    drawdown = calculate_research_portfolio_drawdown(curve, INITIAL_EQUITY_USDT)
    for row, point in zip(rows, drawdown["drawdown_curve"], strict=True):
        row["drawdown_pct"] = float(point["drawdown"])
    run.equity = rows
    return rows


def _coverage_iso(times: Sequence[datetime]) -> dict[str, Any]:
    """First/last/count coverage for one timestamp set in packet ISO format."""

    ordered = sorted(times)
    if not ordered:
        return {"count": 0, "first_utc": None, "last_utc": None}
    return {
        "count": len(ordered),
        "first_utc": phase1._utc_iso(ordered[0]),
        "last_utc": phase1._utc_iso(ordered[-1]),
    }


def summarize_run(run: PolicyRun, signals: Sequence[datetime]) -> dict[str, Any]:
    """Frozen per-policy summary for one cost scenario."""

    executed = run.executed
    frame = pd.DataFrame({"pnl": [float(trade["net_pnl"]) for trade in executed]})
    if len(frame):
        frame["pnl_pct"] = frame["pnl"] / ENTRY_NOTIONAL_USDT * 100.0
    core = compute_core_metrics(frame) if len(frame) else {}
    drawdown = calculate_research_portfolio_drawdown(
        [{"date": row["timestamp"], "balance": row["equity"]} for row in run.equity], INITIAL_EQUITY_USDT
    )
    time_in_market = sum(float(trade["hold_minutes"]) * 60.0 for trade in executed)
    total_turnover = sum(float(trade["entry_notional"]) + float(trade["exit_notional"]) for trade in executed)
    notional_seconds = sum(
        float(trade["entry_notional"]) * float(trade["hold_minutes"]) * 60.0 for trade in executed
    )
    gross_pnl = _total(executed, "gross_pnl")
    net_pnl = _total(executed, "net_pnl")
    count = len(executed)
    entry_times = [
        datetime.fromisoformat(trade["entry_at"].replace("Z", "+00:00")) for trade in executed
    ]
    exit_times = [
        datetime.fromisoformat(trade["exit_at"].replace("Z", "+00:00")) for trade in executed
    ]
    return {
        "policy": run.policy,
        "fee_rate_per_side": run.fee_rate,
        "slippage_rate_per_side": run.slippage_rate,
        "signals": len(signals),
        "entered_trades": count,
        "skipped_entries": sum(action["kind"] == "ENTRY_SKIPPED" for action in run.actions),
        "deferred_entries": sum(action["kind"] == "ENTRY_DEFERRED" for action in run.actions),
        "unresolved_trades": len(run.unresolved),
        "skip_reasons": _count_reasons(run.actions),
        "coverage": {
            "signals": _coverage_iso(list(signals)),
            "account_entries": _coverage_iso(entry_times),
            "account_exits": _coverage_iso(exit_times),
            "evaluation_window": {
                "start_utc": phase1._utc_iso(WINDOW_START),
                "end_utc": phase1._utc_iso(WINDOW_END),
            },
        },
        "gross_pnl_usdt": gross_pnl,
        "friction_pnl_usdt": _total(executed, "friction_pnl"),
        "fee_pnl_usdt": _total(executed, "fee_pnl"),
        "net_pnl_usdt": net_pnl,
        "gross_pnl_per_trade_usdt": (gross_pnl / count) if count else None,
        "net_pnl_per_trade_usdt": (net_pnl / count) if count else None,
        "capital_exhausted": bool(_count_reasons(run.actions).get("INSUFFICIENT_FREE_CASH")),
        "capital_stop_note": (
            "INSUFFICIENT_FREE_CASH means the wallet could not afford the next fixed-size entry "
            "(reserved plus entry fee); it is not necessarily bankruptcy and the wallet may remain positive."
            if _count_reasons(run.actions).get("INSUFFICIENT_FREE_CASH")
            else "No capital stop: every scheduled entry was affordable under the frozen constants."
        ),
        "final_equity_usdt": run.final_cash,
        "total_return_pct": (run.final_cash / INITIAL_EQUITY_USDT - 1.0) * 100.0,
        "max_drawdown_pct": drawdown["max_drawdown_pct"],
        "max_drawdown_usdt": drawdown["max_drawdown_value"],
        "time_in_market_fraction": time_in_market / WINDOW_SECONDS,
        "average_deployed_notional_usdt": notional_seconds / WINDOW_SECONDS,
        "total_turnover_usdt": total_turnover,
        "turnover_over_initial_equity": total_turnover / INITIAL_EQUITY_USDT,
        "win_rate_pct": core.get("win_rate"),
        "avg_win_usdt": core.get("avg_win"),
        "avg_loss_usdt": core.get("avg_loss"),
        "profit_factor": _finite(core.get("profit_factor")),
        "expectancy_usdt": core.get("expectancy"),
        "funding_status": FUNDING_STATUS,
        "cost_adjusted_label": COST_ADJUSTED_LABEL,
    }


def evaluate_full_opportunity(
    policy: str,
    signals: Sequence[datetime],
    grid: M5Grid,
    *,
    fee_rate: float,
    slippage_rate: float,
) -> dict[str, Any]:
    """Hypothetical full-opportunity-set diagnostic for one policy and scenario.

    Same frozen signals, entry/exit rules, and cost arithmetic as the account,
    but **without** cash-based admission and **without** position-overlap
    blocking: every signal is evaluated independently. Each hypothetical trade
    uses the arithmetic scheduled entry boundary, requires the exact entry and
    exit candles, holds exactly 60 minutes, and deploys the frozen fixed
    notional. Results are summed without compounding into an account-equity
    curve. This diagnostic is not an executable account and must never be read
    as one.
    """

    hypothetical: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    unresolved_count = 0
    entry_times: list[datetime] = []
    exit_times: list[datetime] = []
    for sequence, close_time in enumerate(sorted(signals), start=1):
        entry_at = scheduled_m5_open_after(close_time)
        entry_index = grid.open_index(entry_at)
        if entry_index is None:
            skipped.append({"sequence": sequence, "reason": SKIP_REASONS[0]})
            continue
        if entry_at > WINDOW_END:
            skipped.append({"sequence": sequence, "reason": SKIP_REASONS[1]})
            continue
        scheduled_exit = entry_at + SCHEDULED_HOLD
        exit_index = grid.open_index(scheduled_exit)
        if exit_index is None:
            unresolved_count += 1
            skipped.append({"sequence": sequence, "reason": TRADE_UNRESOLVED_EXIT})
            continue
        entry_open = float(grid.open_prices[entry_index])
        exit_open = float(grid.open_prices[exit_index])
        entry_fill = entry_open * (1.0 + slippage_rate)
        exit_fill = exit_open * (1.0 - slippage_rate)
        quantity = ENTRY_NOTIONAL_USDT / entry_fill
        entry_fee = quantity * entry_fill * fee_rate
        exit_fee = quantity * exit_fill * fee_rate
        gross_pnl = (exit_open - entry_open) * (ENTRY_NOTIONAL_USDT / entry_open)
        realized = (exit_fill - entry_fill) * quantity
        friction_pnl = realized - gross_pnl
        fee_pnl = -(entry_fee + exit_fee)
        net_pnl = gross_pnl + friction_pnl + fee_pnl
        hypothetical.append(
            {
                "sequence": sequence,
                "signal_close_at": phase1._utc_iso(close_time),
                "entry_at": phase1._utc_iso(entry_at),
                "exit_at": phase1._utc_iso(scheduled_exit),
                "gross_pnl": gross_pnl,
                "friction_pnl": friction_pnl,
                "fee_pnl": fee_pnl,
                "net_pnl": net_pnl,
            }
        )
        entry_times.append(entry_at)
        exit_times.append(scheduled_exit)
    gross = float(sum(item["gross_pnl"] for item in hypothetical))
    friction = float(sum(item["friction_pnl"] for item in hypothetical))
    fees = float(sum(item["fee_pnl"] for item in hypothetical))
    net = float(sum(item["net_pnl"] for item in hypothetical))
    count = len(hypothetical)
    reasons: dict[str, int] = {}
    for item in skipped:
        reasons[item["reason"]] = reasons.get(item["reason"], 0) + 1
    return {
        "policy": policy,
        "label": "FULL_OPPORTUNITY_SET_DIAGNOSTIC_NOT_AN_ACCOUNT",
        "fee_rate_per_side": fee_rate,
        "slippage_rate_per_side": slippage_rate,
        "signals": len(signals),
        "hypothetical_trades": count,
        "skipped_or_unresolved": len(skipped),
        "unresolved_trades": unresolved_count,
        "skip_reasons": dict(sorted(reasons.items())),
        "coverage": {
            "signals": _coverage_iso(list(signals)),
            "hypothetical_entries": _coverage_iso(entry_times),
            "hypothetical_exits": _coverage_iso(exit_times),
            "evaluation_window": {
                "start_utc": phase1._utc_iso(WINDOW_START),
                "end_utc": phase1._utc_iso(WINDOW_END),
            },
        },
        "gross_pnl_usdt": gross,
        "friction_pnl_usdt": friction,
        "fee_pnl_usdt": fees,
        "net_pnl_usdt": net,
        "gross_pnl_per_signal_usdt": (gross / len(signals)) if signals else None,
        "net_pnl_per_signal_usdt": (net / len(signals)) if signals else None,
        "gross_pnl_per_hypothetical_trade_usdt": (gross / count) if count else None,
        "net_pnl_per_hypothetical_trade_usdt": (net / count) if count else None,
        "not_compounded_into_equity": True,
        "funding_status": FUNDING_STATUS,
        "cost_adjusted_label": COST_ADJUSTED_LABEL,
    }


def run_full_opportunity_grid(
    signals_by_policy: dict[str, Sequence[datetime]],
    grid: M5Grid,
) -> dict[str, dict[str, Any]]:
    """Evaluate the full-opportunity diagnostic over every frozen cost scenario."""

    diagnostics: dict[str, dict[str, Any]] = {}
    for fee_rate in FEE_RATES:
        for slippage_rate in SLIPPAGE_RATES:
            key = scenario_key(fee_rate, slippage_rate)
            diagnostics[key] = {
                policy: evaluate_full_opportunity(
                    policy,
                    signals_by_policy[policy],
                    grid,
                    fee_rate=fee_rate,
                    slippage_rate=slippage_rate,
                )
                for policy in POLICIES
            }
    return diagnostics


def run_cost_grid(
    signals_by_policy: dict[str, Sequence[datetime]],
    grid: M5Grid,
) -> dict[str, dict[str, Any]]:
    """Evaluate every frozen fee/slippage scenario for both policies."""

    scenarios: dict[str, dict[str, Any]] = {}
    for fee_rate in FEE_RATES:
        for slippage_rate in SLIPPAGE_RATES:
            key = scenario_key(fee_rate, slippage_rate)
            outcomes: dict[str, Any] = {}
            for policy in POLICIES:
                run = simulate_policy(
                    policy,
                    signals_by_policy[policy],
                    grid,
                    fee_rate=fee_rate,
                    slippage_rate=slippage_rate,
                )
                build_equity_curve(run, grid)
                outcomes[policy] = {"summary": summarize_run(run, signals_by_policy[policy])}
                if (fee_rate, slippage_rate) in ((HEADLINE_FEE_RATE, HEADLINE_SLIPPAGE_RATE), (0.0, 0.0)):
                    outcomes[policy]["run"] = run
            scenarios[key] = outcomes
    return scenarios


def scenario_key(fee_rate: float, slippage_rate: float) -> str:
    return f"fee_{fee_rate:.5f}_slip_{slippage_rate:.5f}"


def _total(trades: Sequence[dict[str, Any]], key: str) -> float:
    return float(sum(float(trade[key]) for trade in trades))


def _count_reasons(actions: Sequence[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for action in actions:
        reason = action.get("reason")
        if action["kind"] in ("ENTRY_SKIPPED", "TRADE_UNRESOLVED") and reason:
            counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))


def _finite(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if np.isfinite(number) else None
