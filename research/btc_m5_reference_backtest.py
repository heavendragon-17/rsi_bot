"""Frozen offline M5 signal populations; execution is the corrected M15 engine.

A reuses the existing M5 state evaluator, never the M15 crossover. B uses only
native M5/H1/H4 price EMA21 readiness and strict price gates, without RSI
readiness or conditions. Both cooldowns start independently at window start.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta

import numpy as np

from app.backtest import btc_research_phase1 as phase1
from app.backtest.signal_replay_data import events_for_frame
from app.backtest.signal_replay_indicators import PRICE_EMA_PERIOD, _build_context
from app.trading.strategy.btc_rsi_cross_alert.m5_checker import evaluate_m5_cross
from research import btc_m15_reference_backtest as shared

VERSION = "btc-m5-reference-backtest-v1"


def frozen_protocol() -> dict:
    """Reuse the reference trade contract without reusing its M15 signal rule."""
    protocol = deepcopy(shared.PROTOCOL)
    protocol.pop("supersedes", None)  # This is a new M5 experiment, not a replacement M15 packet.
    protocol.update({
        "protocol_version": VERSION,
        "accounting_engine_version": shared.VERSION,
        "signal_timeframe": "5m",
        "policies": {
            "A_emitted_alerts": {
                "evaluator": "evaluate_m5_cross",
                "rule": "Unchanged emitted M5 state alerts; RSI21 > EMA9(RSI) > WMA45(RSI), RSI21 < 60, EMA-WMA >= 2, WMA > 45, plus M5/H1/H4 close > EMA21(price). No fresh-cross condition.",
                "cooldown": "Independent 60 minutes from last emitted close; initialized at window start",
            },
            "B_gate_cooldown": {
                "rule": "Only strict M5/H1/H4 native close > EMA21(price)",
                "rsi_conditions": False,
                "readiness": "21 contiguous native price candles on each timeframe, no RSI readiness requirement; exact fully closed H1/H4 boundaries",
                "cooldown": "Own independent 60 minutes from last accepted close; initialized at window start",
            },
            "signal_generation_independent_of_positions": True,
        },
    })
    protocol["evaluation_window"]["signal_semantics"] = "M5 trigger-close timestamps inside the window, inclusive"
    protocol["evaluation_window"]["note"] = "Same four-year requested window as the frozen M15 account."
    protocol["execution"]["while_open"] = "Cooldown-separated signals cannot overlap under the exact 60-minute hold; a missing exit blocks later entries. No deferred entries are permitted in this experiment."
    return protocol


def verify_parity(expected: list[datetime], actual: list[datetime]) -> dict:
    """Refuse performance calculation unless the entire ordered population matches."""
    if expected != actual or len(set(expected)) != len(expected):
        raise ValueError("M5 emitted signal parity mismatch; performance run refused")
    return {"matches": True, "emitted_count": len(expected), "reconstructed_count": len(actual),
            "method": "Every M5 bar prepared and evaluated with existing state evaluator, then independent 60-minute cooldown; exact ordered timestamp equality"}


def reconstruct_alerts(inputs: phase1.ValidatedInputs, start: datetime, end: datetime) -> tuple[list[datetime], dict]:
    """Independently evaluate every M5 bar using the unchanged state evaluator."""
    cache = phase1._cache_for(inputs)
    events = events_for_frame(inputs.frames["5m"], "5m", start, end)
    raw = []
    exclusions: Counter[str] = Counter()
    decisions: Counter[str] = Counter()
    for event in events:
        preparation = cache.prepare(event, symbol=phase1.SYMBOL)
        if preparation.input is None:
            exclusions[preparation.reason] += 1
            continue
        decision = evaluate_m5_cross(preparation.input)
        decisions[decision.reason] += 1
        if decision.should_alert:
            raw.append(event.close_time)
    return shared.apply_cooldown(raw, shared.SIGNAL_COOLDOWN), {
        "candidate_bars": len(events),
        "preparation_exclusions": dict(sorted(exclusions.items())),
        "decisions": dict(sorted(decisions.items())),
        "state_alert_bars_before_cooldown": len(raw),
    }


def price_gate_times(
    inputs: phase1.ValidatedInputs, start: datetime, end: datetime
) -> tuple[list[datetime], dict]:
    """Price-only readiness, exact closed HTF boundaries and no RSI dependency."""
    contexts = {
        tf: _build_context(inputs.frames[tf], timedelta(minutes=minutes), include_rsi=False)
        for tf, minutes in (("5m", 5), ("1h", 60), ("4h", 240))
    }
    trigger = contexts["5m"]
    indices = np.flatnonzero((trigger.close_index >= start) & (trigger.close_index <= end))
    joins = {
        tf: context.close_index.get_indexer(trigger.close_index.floor(tf))
        for tf, context in contexts.items() if tf != "5m"
    }
    # Prefix counts let a non-finite historical close invalidate its segment
    # without scanning the entire growing segment on every M5 decision.
    bad_prefix = {
        tf: np.r_[0, np.cumsum(~np.isfinite(context.close_values) | (context.close_values <= 0))]
        for tf, context in contexts.items()
    }
    accepted = []
    exclusions: Counter[str] = Counter()
    ready_count = 0
    for index in indices:
        gate = True
        for tf, context in contexts.items():
            position = int(index if tf == "5m" else joins[tf][index])
            if position < 0:
                exclusions[f"{tf}_EXPECTED_CLOSE_MISSING"] += 1
                break
            if not context.has_contiguous_history(position, PRICE_EMA_PERIOD):
                exclusions[f"{tf}_INSUFFICIENT_PRICE_HISTORY"] += 1
                break
            segment = int(context.segment_starts[position])
            if (bad_prefix[tf][position + 1] != bad_prefix[tf][segment]
                    or not np.isfinite(context.price_ema21[position])):
                exclusions[f"{tf}_NON_FINITE_PRICE"] += 1
                break
            gate = gate and bool(context.close_values[position] > context.price_ema21[position])
        else:
            ready_count += 1
            if gate:
                accepted.append(trigger.close_times[index])
    return accepted, {
        "candidate_bars": len(indices),
        "price_ready_bars": ready_count,
        "price_gated_bars": len(accepted),
        "excluded_bars": sum(exclusions.values()),
        "exclusion_reasons": dict(sorted(exclusions.items())),
        "readiness": "21 contiguous native price candles per timeframe; no RSI readiness or conditions",
    }
