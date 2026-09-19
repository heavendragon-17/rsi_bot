"""Core V2.1 reference simulation (research-only).

Runs ONE frozen protocol - ``core-v2.1-reference-backtest-v1`` - on top of
the audited point-in-time signal replay. It reuses the existing replay
engine (:mod:`app.backtest.core_v2_1`) and the existing position-sizing
implementation (:class:`app.trading.portfolio.position_sizer.PositionSizer`);
it does not build another framework.

Scope discipline:

- Only ``A_PLUS_LONG`` (immediate-long) and ``PULLBACK_LONG``
  (pullback-long) events initiate positions; the two entry families are
  reported separately.
- Before any performance number is computed, the protocol is frozen to
  ``protocol.json`` and hashed (SHA-256). Documented rules from
  ``docs/07_trading_strategies/core-v2-1-execution-decisions.md`` are kept
  distinct from choices explicitly flagged ``ASSUMPTION_NOT_A_DECISION``.
- Funding is ``EXCLUDED_BY_DESIGN``. Candle-price fills are labelled
  proxies, not guaranteed obtainable fills. No pooled cross-venue returns
  are computed.

Usage (repo root, project conda env), paths abbreviated::

    python research/core_v2_1_reference_sim.py --freeze-protocol
    python research/core_v2_1_reference_sim.py
        --run-dir research/results/core_v2_1_reference_sim_v1
        --audit-dir research/results/core_v2_1_audit_replay
        --data-dir app/backtest/data
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PROTOCOL_NAME = "core-v2.1-reference-backtest-v1"
# ---------------------------------------------------------------------------
# Frozen protocol.  ``basis`` is one of:
#   DOCUMENTED                  - approved decision / locked contract
#   RESOLVED_CODE               - inherited setting resolved from code + config
#   RESOLVED_EXTERNAL           - verified against an official external source
#   ASSUMPTION_NOT_A_DECISION   - research choice, NOT an approved rule
#   GENUINELY_UNRESOLVED        - cannot be resolved from code/config/docs
# ---------------------------------------------------------------------------
PROTOCOL: dict[str, Any] = {
    "name": PROTOCOL_NAME,
    "signals": {
        "engine": "core_v2_1_point_in_time",
        "strategy_version": "2.1",
        "config_version": "core-v2.1-locked-2026-08-20",
        "anchor_version": "core-v2.1-anchor-2026-06-29T11:15Z-v1",
        "entry_event_types": ["A_PLUS_LONG", "PULLBACK_LONG"],
        "reproduction": (
            "replay is regenerated from the locked anchor and must be "
            "row-identical to the audited historical ledger before any "
            "trade is simulated"
        ),
        "basis": "DOCUMENTED",
    },
    "entry": {
        "fill": "next_M15_open * (1 + slippage_rate)",
        "label": "candle-price proxy, not a guaranteed obtainable fill",
        "basis": "DOCUMENTED (execution decision 3)",
    },
    "take_profits": {
        "levels": "original signal reference TP1/TP2/TP3 (1R/2R/3R of reference entry)",
        "allocation": (
            "one third of the original quantity at each TP; the final third "
            "fills the exact remainder so the three partial quantities sum "
            "to the original"
        ),
        "activation": "limit-fill proxy at TP price when candle high >= level",
        "basis_levels": "DOCUMENTED",
        "basis_allocation": "ASSUMPTION_NOT_A_DECISION",
        "basis_activation": "ASSUMPTION_NOT_A_DECISION",
    },
    "strategy_stop": {
        "trigger": "fully closed M15 Close < current M15 EMA21 (strict; wicks ignored)",
        "exit_fill": "remaining quantity at following M15 open * (1 - slippage_rate)",
        "basis_trigger": "DOCUMENTED (execution decision 2)",
        "basis_exit_fill": "ASSUMPTION_NOT_A_DECISION",
    },
    "disaster_stop": {
        "rule": "none added; advisory reference stop is an R/sizing reference only",
        "basis": "DOCUMENTED boundary (decisions doc: unresolved; task: none added)",
    },
    "max_holding": {
        "rule": "no force-close applied",
        "basis": (
            "GENUINELY_UNRESOLVED: the signal-mode resolver never forwards "
            "strategy_params (app/signal/strategy_config.py as_legacy_dict "
            "returns {}), so the older-strategy max_holding default cannot be "
            "established for Core V2.1 from config"
        ),
    },
    "same_bar_ordering": {
        "rule": (
            "on the entry candle TP checks start on the NEXT candle; "
            "if a candle both closes below EMA21 (stop) and reaches a TP "
            "level (high), the close-based stop wins and TP fills in that "
            "candle are ignored"
        ),
        "basis": "ASSUMPTION_NOT_A_DECISION",
    },    "gap_fills": {
        "rule": (
            "entry and stop exits fill at the candle open regardless of gap; "
            "TP fills at the TP level price only when the candle high reaches it"
        ),
        "basis": "ASSUMPTION_NOT_A_DECISION",
    },
    "overlap": {
        "rule": (
            "one open position per strategy+symbol; entry events arriving "
            "while a position is open are recorded as OVERLAP_SKIPPED; the "
            "signal state machine is unaffected (replay ledger unchanged)"
        ),
        "basis": "DOCUMENTED (execution decision 6)",
    },
    "sizing": {
        "implementation": "app.trading.portfolio.position_sizer.PositionSizer.calculate",
        "config_source": "config.yaml risk + backtest blocks",
        "risk_per_trade_pct": "0.002 (fraction; YAML comment 2% is misleading)",
        "max_position_size_pct": "10 (used as margin fraction 10x; non-binding here)",
        "use_risk_based_sizing": True,
        "use_initial_capital_for_risk": True,
        "min_sl_distance_pct": "0.003 (fraction)",
        "leverage": 10,
        "initial_capital_quote": "100000 (backtest.initial_balance)",
        "basis": "RESOLVED_CODE",
    },
    "fees": {
        "BINANCE_FUTURES": {
            "taker": "0.0005",
            "maker": "0.0002",
            "source": "binance.info FAQ 360033544231 (regular user USD-M)",
            "source_updated": "2026-05-01",
            "checked_on": "2026-09-19",
        },
        "HYPERLIQUID": {
            "taker": "0.00045",
            "maker": "0.00015",
            "source": "hyperliquid.gitbook.io/hyperliquid-docs/trading/fees (perps base tier)",
            "source_updated": "page states last updated about 1 month ago at fetch time",
            "checked_on": "2026-09-19",
        },
        "fee_formula": "fee = qty * price * rate; maker rate on TP fills, taker elsewhere",
        "funding": "EXCLUDED_BY_DESIGN",
        "basis_rates": "RESOLVED_EXTERNAL",
        "basis_formula": "ASSUMPTION_NOT_A_DECISION",
    },
    "accounting": {
        "quantities": "Decimal; partial exits preserved per fill",
        "r_both": "gross_realized_r and net_realized_r stored separately",
        "open_at_end": (
            "positions still open at the last candle retain exposure; valued "
            "at the last closed M15 close (valid mark); contribution reported "
            "separately, never blended into realized P&L"
        ),
        "no_pooled_returns": (
            "per-venue aggregates only; no cross-venue pooled equity curve "
            "(no capital-allocation/conversion policy exists)"
        ),
        "basis": "DOCUMENTED accounting fields + ASSUMPTION_NOT_A_DECISION valuation",
    },
    "slippage_rate": {"value": "0.001", "basis": "ASSUMPTION_NOT_A_DECISION"},
    "cost_sensitivity": {
        "slippage_grid": ["0.0", "0.0005", "0.001", "0.002"],
        "fee_scale_grid": ["1.0", "0.5", "1.5"],
        "note": "frozen before performance numbers; not a parameter search",
        "basis": "ASSUMPTION_NOT_A_DECISION",
    },
    "excluded": [
        "funding (EXCLUDED_BY_DESIGN)",
        "one-hour time-exit policy from BTC M15/M5 research (not carried over)",
        "parameter search / optimization",
        "live promotion",
    ],
}


def protocol_json_text() -> str:
    return json.dumps(PROTOCOL, indent=2, sort_keys=True) + "\n"


def freeze_protocol(path: Path) -> str:
    text = protocol_json_text()
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"protocol_sha256": digest, "protocol": json.loads(text)}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return digest

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-protocol", action="store_true")
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=Path("research/results/core_v2_1_reference_sim_v1"),
    )
    parser.add_argument(
        "--audit-dir",
        type=Path,
        default=Path("research/results/core_v2_1_audit_replay"),
    )
    parser.add_argument("--data-dir", type=Path, default=Path("app/backtest/data"))
    args = parser.parse_args(argv)
    if args.freeze_protocol:
        digest = freeze_protocol(args.run_dir / "protocol.json")
        print(f"protocol frozen: {digest}")
        return 0
    return _run_simulation(args)
# ---------------------------------------------------------------------------
# Simulation engine
# ---------------------------------------------------------------------------

D = Decimal


@dataclass(frozen=True)
class Fill:
    time: str
    kind: str  # ENTRY | TP1 | TP2 | TP3 | STOP | MARK_END
    qty: D
    price: D
    fee: D
    fee_rate: D


@dataclass
class PositionSim:
    symbol: str
    venue: str
    family: str  # immediate_long | pullback_long
    event_type: str
    sequence: int
    signal_close: pd.Timestamp
    reference_entry: D
    reference_stop: D
    risk_1r: D
    tp1: D
    tp2: D
    tp3: D
    qty_total: D
    qty_tp: D  # one third of original, frozen at entry
    qty_remaining: D
    entry_idx: int
    entry_time: pd.Timestamp
    simulated_fill: D
    stop_triggered: bool = False
    stop_close_time: pd.Timestamp | None = None
    next_tp: int = 1
    fills: list[Fill] = field(default_factory=list)
    closed: bool = False
    close_time: pd.Timestamp | None = None
    close_reason: str | None = None

    @property
    def gross_pnl(self) -> D:
        realized = sum(f.qty * f.price for f in self.fills if f.kind != "ENTRY")
        return realized - self.qty_total * self.simulated_fill

    @property
    def fees(self) -> D:
        return sum((f.fee for f in self.fills), D("0"))

    @property
    def net_pnl(self) -> D:
        return self.gross_pnl - self.fees


def _fee_rates(venue: str, fee_scale: D) -> tuple[D, D]:
    if venue.startswith("HYPERLIQUID"):
        key = "HYPERLIQUID"
    elif venue.startswith("BINANCE"):
        key = "BINANCE_FUTURES"
    else:
        raise KeyError(f"no verified fee schedule for venue {venue!r}")
    spec = PROTOCOL["fees"][key]
    return D(spec["taker"]) * fee_scale, D(spec["maker"]) * fee_scale


def _entry_events(ledger_csv: Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    with ledger_csv.open("r", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["event_type"] not in PROTOCOL["signals"]["entry_event_types"]:
                continue
            event = (json.loads(row["decision_json"]).get("event") or {})
            levels = event.get("trade_levels") or {}
            rows.append(
                {
                    "sequence": int(row["sequence"]),
                    "trigger_closed_at": row["trigger_closed_at"],
                    "symbol": row["symbol"],
                    "venue": row["venue"],
                    "event_type": row["event_type"],
                    "reference_entry": levels["reference_entry"],
                    "reference_stop": levels["reference_stop"],
                    "risk_1r": levels["risk_1r"],
                    "tp1": levels["tp1"],
                    "tp2": levels["tp2"],
                    "tp3": levels["tp3"],
                }
            )
    return pd.DataFrame(rows)


def _simulate_symbol(
    symbol: str,
    venue: str,
    events: pd.DataFrame,
    m15: pd.DataFrame,
    qty_for,  # callable(reference_entry, reference_stop) -> Decimal quantity
    slippage: D,
    fee_scale: D,
) -> tuple[list[PositionSim], list[dict[str, Any]]]:
    taker, maker = _fee_rates(venue, fee_scale)
    positions: list[PositionSim] = []
    skipped: list[dict[str, Any]] = []
    open_pos: PositionSim | None = None
    index = m15.index

    events = events.sort_values("sequence")
    event_iter = {
        pd.Timestamp(row.trigger_closed_at): row for row in events.itertuples()
    }
    final_close = index[-1]
    for row in events.itertuples():
        if pd.Timestamp(row.trigger_closed_at) == final_close:
            skipped.append(
                {
                    "sequence": row.sequence,
                    "symbol": symbol,
                    "event_type": row.event_type,
                    "trigger_closed_at": str(final_close),
                    "reason": "NO_FILL_CANDLE",
                }
            )

    for i in range(len(index)):
        closed_at = index[i]
        candle = m15.iloc[i]
        has_next = i + 1 < len(index)
        nxt = m15.iloc[i + 1] if has_next else None
        next_time = index[i + 1] if has_next else None

        # 1) Existing position: stop evaluated on every close at/after the
        # entry candle; TPs only from the NEXT candle and only when the stop
        # does NOT trigger on this close.
        if open_pos is not None and i >= open_pos.entry_idx:
            stop_now = candle["close"] < candle["ema21"]
            if stop_now:
                open_pos.stop_triggered = True
                open_pos.stop_close_time = closed_at
            elif i > open_pos.entry_idx:
                while open_pos.next_tp <= 3:
                    level = getattr(open_pos, f"tp{open_pos.next_tp}")
                    if candle["high"] >= level:
                        # The final third absorbs the exact remainder so the
                        # three partial quantities always sum to the original
                        # (Decimal qty/3 can leave a dust residue).
                        if open_pos.next_tp == 3:
                            qty = open_pos.qty_remaining
                        else:
                            qty = min(open_pos.qty_tp, open_pos.qty_remaining)
                        open_pos.fills.append(
                            Fill(str(closed_at), f"TP{open_pos.next_tp}", qty, level,
                                 qty * level * maker, maker)
                        )
                        open_pos.qty_remaining -= qty
                        open_pos.next_tp += 1
                        if open_pos.qty_remaining == 0:
                            open_pos.closed = True
                            open_pos.close_time = closed_at
                            open_pos.close_reason = "TP3"
                            break
                    else:
                        break
            if open_pos.closed:
                positions.append(open_pos)
                open_pos = None
                continue

        # 2) Stop exit at the NEXT candle open (pending or triggered this close).
        if (
            open_pos is not None
            and open_pos.stop_triggered
            and has_next
            and i + 1 > open_pos.entry_idx
        ):
            price = D(str(nxt["open"])) * (D("1") - slippage)
            qty = open_pos.qty_remaining
            open_pos.fills.append(
                Fill(str(next_time), "STOP", qty, price, qty * price * taker, taker)
            )
            open_pos.qty_remaining = D("0")
            open_pos.closed = True
            open_pos.close_time = next_time
            open_pos.close_reason = "STOP_EMA21"
            positions.append(open_pos)
            open_pos = None

        # 3) New entry signal on this close (never filled on the signal candle).
        ev = event_iter.get(closed_at)
        if ev is None or not has_next:
            continue
        if open_pos is not None:
            skipped.append(
                {
                    "sequence": ev.sequence,
                    "symbol": symbol,
                    "event_type": ev.event_type,
                    "trigger_closed_at": str(closed_at),
                    "reason": "OVERLAP_SKIPPED",
                }
            )
            continue
        qty = qty_for(D(ev.reference_entry), D(ev.reference_stop))
        if qty <= 0:
            skipped.append(
                {
                    "sequence": ev.sequence,
                    "symbol": symbol,
                    "event_type": ev.event_type,
                    "trigger_closed_at": str(closed_at),
                    "reason": "ZERO_SIZE",
                }
            )
            continue
        fill_price = D(str(nxt["open"])) * (D("1") + slippage)
        pos = PositionSim(
            symbol=symbol,
            venue=venue,
            family="immediate_long" if ev.event_type == "A_PLUS_LONG" else "pullback_long",
            event_type=ev.event_type,
            sequence=ev.sequence,
            signal_close=closed_at,
            reference_entry=D(ev.reference_entry),
            reference_stop=D(ev.reference_stop),
            risk_1r=D(ev.risk_1r),
            tp1=D(ev.tp1),
            tp2=D(ev.tp2),
            tp3=D(ev.tp3),
            qty_total=qty,
            qty_tp=qty / D("3"),
            qty_remaining=qty,
            entry_idx=i + 1,
            entry_time=next_time,
            simulated_fill=fill_price,
        )
        pos.fills.append(Fill(str(next_time), "ENTRY", qty, fill_price, qty * fill_price * taker, taker))
        open_pos = pos

    # 4) Mark any still-open position at the last closed candle.
    if open_pos is not None:
        last_close = m15.iloc[-1]["close"]
        open_pos.mark_price = D(str(last_close))  # type: ignore[attr-defined]
        open_pos.close_reason = "OPEN_AT_END"
        positions.append(open_pos)
    for p in positions:
        if p.close_time is None:
            p.close_time = pd.Timestamp(p.fills[-1].time)
    return positions, skipped

def _assert_reproduction(audit_csv: Path, new_csv: Path) -> None:
    key = lambda r: (r["sequence"], r["trigger_closed_at"], r["symbol"],
                     r["event_type"], r["decision_kind"])
    with audit_csv.open("r", newline="", encoding="utf-8") as fh, new_csv.open(
        "r", newline="", encoding="utf-8"
    ) as fn:
        old = [key(r) for r in csv.DictReader(fh)]
        new = [key(r) for r in csv.DictReader(fn)]
    if old != new:
        raise SystemExit(
            "replayed ledger is not identical to the audited ledger; "
            "simulation aborted before any performance number"
        )


def _make_qty_fn():
    from app.trading.portfolio.position_sizer import PositionSizer

    sizing = PROTOCOL["sizing"]
    config = {
        "risk": {
            "risk_per_trade_pct": D(sizing["risk_per_trade_pct"].split(" ")[0]),
            "max_position_size_pct": D(sizing["max_position_size_pct"].split(" ")[0]),
            "use_risk_based_sizing": True,
            "use_initial_capital_for_risk": True,
            "min_sl_distance_pct": D(sizing["min_sl_distance_pct"].split(" ")[0]),
            "leverage": sizing["leverage"],
        },
        "backtest": {"initial_balance": D("100000")},
    }
    sizer = PositionSizer(config, exchange=None)

    def qty_for(reference_entry: D, reference_stop: D) -> D:
        return sizer.calculate(
            balance=D("100000"), entry_price=reference_entry, sl_price=reference_stop
        )

    return qty_for


def _run_all(frames, events: pd.DataFrame, slippage: D, fee_scale: D):
    from app.backtest.core_v2_1.coverage import venue_for_symbol

    qty_for = _make_qty_fn()
    all_positions: list[PositionSim] = []
    all_skipped: list[dict[str, Any]] = []
    for symbol, m15 in frames.alt_m15.items():
        sym_events = events[events["symbol"] == symbol]
        venue = venue_for_symbol(symbol)
        positions, skipped = _simulate_symbol(
            symbol, venue, sym_events, m15, qty_for, slippage, fee_scale
        )
        all_positions.extend(positions)
        all_skipped.extend(skipped)
    all_positions.sort(key=lambda p: p.sequence)
    all_skipped.sort(key=lambda s: s["sequence"])
    return all_positions, all_skipped


def _summarize(positions: list[PositionSim]) -> dict[str, Any]:
    def pack(group: list[PositionSim]) -> dict[str, Any]:
        closed = [p for p in group if p.close_reason != "OPEN_AT_END"]
        open_end = [p for p in group if p.close_reason == "OPEN_AT_END"]
        gross = sum((p.gross_pnl for p in closed), D("0"))
        net = sum((p.net_pnl for p in closed), D("0"))
        gross_r = sum(
            (p.gross_pnl / (p.risk_1r * p.qty_total) for p in closed if p.risk_1r > 0), D("0")
        )
        net_r = sum(
            (p.net_pnl / (p.risk_1r * p.qty_total) for p in closed if p.risk_1r > 0), D("0")
        )
        holds = [int((p.close_time - p.entry_time).total_seconds() // 900) for p in closed]
        return {
            "positions": len(group),
            "closed": len(closed),
            "open_at_end": len(open_end),
            "gross_pnl_quote": str(gross),
            "net_pnl_quote": str(net),
            "gross_realized_r": str(gross_r),
            "net_realized_r": str(net_r),
            "holding_bars_min": min(holds) if holds else None,
            "holding_bars_median": sorted(holds)[len(holds) // 2] if holds else None,
            "holding_bars_max": max(holds) if holds else None,
            "open_at_end_mark_value_quote": str(
                sum(
                    (p.qty_remaining * (p.mark_price - p.simulated_fill) for p in open_end),
                    D("0"),
                )
            ),
        }

    by_family: dict[str, list[PositionSim]] = {}
    by_symbol: dict[str, list[PositionSim]] = {}
    by_venue: dict[str, list[PositionSim]] = {}
    for p in positions:
        by_family.setdefault(p.family, []).append(p)
        by_symbol.setdefault(p.symbol, []).append(p)
        by_venue.setdefault(p.venue, []).append(p)
    return {
        "all": pack(positions),
        "by_entry_family": {k: pack(v) for k, v in sorted(by_family.items())},
        "by_venue": {k: pack(v) for k, v in sorted(by_venue.items())},
        "by_symbol": {k: pack(v) for k, v in sorted(by_symbol.items())},
    }

def _position_record(p: PositionSim) -> dict[str, Any]:
    return {
        "sequence": p.sequence,
        "symbol": p.symbol,
        "venue": p.venue,
        "family": p.family,
        "event_type": p.event_type,
        "signal_close": str(p.signal_close),
        "entry_time": str(p.entry_time),
        "close_time": str(p.close_time) if p.close_time else None,
        "close_reason": p.close_reason,
        "reference_entry": str(p.reference_entry),
        "reference_stop": str(p.reference_stop),
        "risk_1r": str(p.risk_1r),
        "tp1": str(p.tp1),
        "tp2": str(p.tp2),
        "tp3": str(p.tp3),
        "qty_total": str(p.qty_total),
        "qty_tp_each": str(p.qty_tp),
        "simulated_fill": str(p.simulated_fill),
        "fills": [
            {
                "time": f.time,
                "kind": f.kind,
                "qty": str(f.qty),
                "price": str(f.price),
                "fee": str(f.fee),
                "fee_rate": str(f.fee_rate),
            }
            for f in p.fills
        ],
        "gross_pnl_quote": str(p.gross_pnl),
        "fees_quote": str(p.fees),
        "net_pnl_quote": str(p.net_pnl),
        "gross_realized_r": (
            str(p.gross_pnl / (p.risk_1r * p.qty_total)) if p.risk_1r > 0 else None
        ),
        "net_realized_r": (
            str(p.net_pnl / (p.risk_1r * p.qty_total)) if p.risk_1r > 0 else None
        ),
        "holding_bars": (
            int((p.close_time - p.entry_time).total_seconds() // 900) if p.close_time else None
        ),
        "mark_price": str(getattr(p, "mark_price", "")) or None,
        "open_mark_value_quote": (
            str(p.qty_remaining * (p.mark_price - p.simulated_fill))
            if p.close_reason == "OPEN_AT_END"
            else None
        ),
    }


def _holding_distribution(positions: list[PositionSim]) -> dict[str, Any]:
    holds = sorted(
        int((p.close_time - p.entry_time).total_seconds() // 900)
        for p in positions
        if p.close_time
    )
    if not holds:
        return {"count": 0, "bars": []}
    buckets = {"1-4": 0, "5-12": 0, "13-24": 0, "25-48": 0, "49-96": 0, "97+": 0}
    for h in holds:
        if h <= 4:
            buckets["1-4"] += 1
        elif h <= 12:
            buckets["5-12"] += 1
        elif h <= 24:
            buckets["13-24"] += 1
        elif h <= 48:
            buckets["25-48"] += 1
        elif h <= 96:
            buckets["49-96"] += 1
        else:
            buckets["97+"] += 1
    return {
        "count": len(holds),
        "min_bars": holds[0],
        "median_bars": holds[len(holds) // 2],
        "max_bars": holds[-1],
        "mean_bars": sum(holds) / len(holds),
        "buckets": buckets,
        "bars": holds,
    }

def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    try:
        temp.write_text(text, encoding="utf-8", newline="\n")
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    return plt, mdates


def _render_trade_chart(position: PositionSim, m15: pd.DataFrame, out_path: Path) -> None:
    plt, mdates = _matplotlib()
    center = position.entry_time
    index = m15.index
    loc = index.searchsorted(center)
    window = m15.iloc[max(0, loc - 24) : loc + 40]
    figure, axis = plt.subplots(figsize=(11, 5.2))
    axis.plot(window.index, window["close"], color="#1f2328", lw=1.1, label="M15 close")
    axis.plot(window.index, window["ema21"], color="#0a6ed1", lw=1.0, label="EMA21")
    for label, value in (
        ("ref entry", position.reference_entry),
        ("ref stop", position.reference_stop),
        ("TP1", position.tp1),
        ("TP2", position.tp2),
        ("TP3", position.tp3),
    ):
        axis.axhline(float(value), color="#9a6700", lw=0.7, ls=":")
        axis.text(window.index[0], float(value), f" {label}", fontsize=7, color="#9a6700")
    colors = {"ENTRY": "#1a7f37", "STOP": "#cf222e"}
    for f in position.fills:
        ts = pd.Timestamp(f.time)
        if ts < window.index[0] or ts > window.index[-1]:
            continue
        color = colors.get(f.kind, "#8250df")
        axis.scatter([ts], [float(f.price)], color=color, zorder=5, s=44)
        axis.annotate(f.kind, (ts, float(f.price)), textcoords="offset points",
                      xytext=(0, 8), fontsize=7, color=color)
    axis.set_title(
        f"{position.symbol} {position.family} seq {position.sequence} "
        f"({position.close_reason}) - candle-price proxy fills, not guaranteed",
        fontsize=9,
    )
    axis.legend(loc="upper left", fontsize=8)
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M", tz=window.index.tz))
    figure.autofmt_xdate()
    figure.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(out_path, dpi=150)
    plt.close(figure)


def _render_holding_chart(distribution: dict[str, Any], out_path: Path) -> None:
    plt, _ = _matplotlib()
    buckets = distribution["buckets"]
    figure, axis = plt.subplots(figsize=(8, 4.2))
    axis.bar(list(buckets), list(buckets.values()), color="#0a6ed1")
    axis.set_title("Holding-time distribution (M15 bars, closed positions)", fontsize=10)
    axis.set_ylabel("positions")
    figure.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(out_path, dpi=150)
    plt.close(figure)

def _run_simulation(args: argparse.Namespace) -> int:
    run_dir: Path = args.run_dir
    protocol_path = run_dir / "protocol.json"
    if not protocol_path.is_file():
        raise SystemExit("freeze the protocol first (--freeze-protocol)")
    frozen = json.loads(protocol_path.read_text(encoding="utf-8"))
    if frozen["protocol"] != json.loads(protocol_json_text()):
        raise SystemExit("PROTOCOL dict drifted from the frozen protocol.json; aborting")
    protocol_hash = frozen["protocol_sha256"]

    from app.backtest.core_v2_1.replay import (
        CoreV21PointInTimeReplay,
        build_replay_frames,
        load_available_universe,
    )

    # 1) Regenerate the audited replay and require exact reproduction.
    source = load_available_universe(args.data_dir, require_all=True)
    frames = build_replay_frames(source)
    replay_result = CoreV21PointInTimeReplay(frames).run(
        start=source.common_start, end=source.common_end
    )
    replay_check_dir = run_dir / "replay_check"
    paths = replay_result.ledger.export(
        replay_check_dir, metadata={"purpose": "parity check only"}
    )
    _assert_reproduction(args.audit_dir / "core_v2_1_replay.csv", paths.csv)

    # 2) Base-case simulation (frozen headline costs) + frozen sensitivity grid.
    events = _entry_events(args.audit_dir / "core_v2_1_replay.csv")
    base_slippage = D(PROTOCOL["slippage_rate"]["value"])
    base_positions, base_skipped = _run_all(frames, events, base_slippage, D("1"))
    summary = _summarize(base_positions)
    summary["overlap_skipped"] = len(base_skipped)
    summary["protocol_sha256"] = protocol_hash

    sensitivity: list[dict[str, Any]] = []
    for slip in PROTOCOL["cost_sensitivity"]["slippage_grid"]:
        for scale in PROTOCOL["cost_sensitivity"]["fee_scale_grid"]:
            positions, _ = _run_all(frames, events, D(slip), D(scale))
            closed = [p for p in positions if p.close_reason != "OPEN_AT_END"]
            sensitivity.append(
                {
                    "slippage": slip,
                    "fee_scale": scale,
                    "gross_pnl_quote": str(sum((p.gross_pnl for p in closed), D("0"))),
                    "net_pnl_quote": str(sum((p.net_pnl for p in closed), D("0"))),
                }
            )

    # 3) Persist ledger, summaries, charts.
    records = [_position_record(p) for p in base_positions]
    _atomic_write(
        run_dir / "trades.json",
        json.dumps(
            {"protocol_sha256": protocol_hash, "positions": records, "skipped": base_skipped},
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    holding = _holding_distribution(base_positions)
    _atomic_write(
        run_dir / "results.json",
        json.dumps(
            {
                "protocol_sha256": protocol_hash,
                "summary": summary,
                "holding_distribution": holding,
                "cost_sensitivity": sensitivity,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    charts_dir = run_dir / "charts"
    _render_holding_chart(holding, charts_dir / "holding_time.png")
    charted = ["charts/holding_time.png"]
    closed_sorted = [p for p in base_positions if p.close_reason != "OPEN_AT_END"]
    picks = {
        "best_net": max(closed_sorted, key=lambda p: p.net_pnl, default=None),
        "worst_net": min(closed_sorted, key=lambda p: p.net_pnl, default=None),
        "first_pullback": next(
            (p for p in closed_sorted if p.family == "pullback_long"), None
        ),
    }
    for name, pos in picks.items():
        if pos is None:
            continue
        _render_trade_chart(pos, frames.alt_m15[pos.symbol], charts_dir / f"trade_{name}.png")
        charted.append(f"charts/trade_{name}.png")
    _atomic_write(
        run_dir / "manifest.json",
        json.dumps(
            {
                "protocol_sha256": protocol_hash,
                "outputs": {
                    p: _sha256_file(run_dir / p)
                    for p in ["trades.json", "results.json", *charted]
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    print(json.dumps(summary["by_entry_family"], indent=2))
    print(json.dumps(summary["all"], indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())