"""Core V2.1 execution backtest on the shared portfolio engine (research-only).

Runs ONE frozen protocol (``core-v2.1-engine-backtest-v1``) with the thin
:class:`CoreV21EngineStrategy` adapter inside the existing
:class:`PortfolioEngine` + :class:`MockExchange` stack.  No parallel
simulator: signals, sizing, fills, fees, and accounting all flow through
production-path components.

Funding is EXCLUDED_BY_DESIGN.  No pooled cross-venue returns are reported.

Usage (repo root)::

    python -m app.backtest.core_v2_1.engine_backtest --freeze-protocol
    python -m app.backtest.core_v2_1.engine_backtest --run-dir research/results/core_v2_1_engine_backtest_v1
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import structlog
import yaml

from app.backtest.core_v2_1.coverage import venue_for_symbol
from app.backtest.core_v2_1.engine_adapter import CoreV21EngineStrategy
from app.backtest.core_v2_1.replay import build_replay_frames, load_available_universe
from app.backtest.engine.batch_event_source import BatchPortfolioEventSource
from app.backtest.engine.portfolio_engine import PortfolioEngine
from app.backtest.exchange.mock_exchange import MockExchange
from app.core.constants import DEFAULT_MAKER_FEE, DEFAULT_TAKER_FEE

logger = structlog.get_logger()

REPO_ROOT = Path(__file__).resolve().parents[3]
PROTOCOL_NAME = "core-v2.1-engine-backtest-v1"

D = Decimal

# ---------------------------------------------------------------------------
# Frozen protocol.  basis: DOCUMENTED | RESOLVED_CODE | RESOLVED_EXTERNAL |
# ASSUMPTION_NOT_A_DECISION | GENUINELY_UNRESOLVED | EXCLUDED_BY_DESIGN
# ---------------------------------------------------------------------------
PROTOCOL: dict[str, Any] = {
    "name": PROTOCOL_NAME,
    "engine": "shared PortfolioEngine + MockExchange + PortfolioManager (no parallel simulator)",
    "signals": {
        "rule": "locked CoreV21 evaluator over locked point-in-time replay frames; "
        "A_PLUS_LONG and PULLBACK_LONG open positions; state machine advances "
        "during positions so re-arm stays deterministic",
        "basis": "DOCUMENTED",
    },
    "entry": {
        "fill": "next_M15_open * (1 + slippage_rate) via shared MockExchange market slippage",
        "timing": "adapter defers the signal one candle; entry action carries the next open",
        "basis": "DOCUMENTED (execution decision 3)",
    },
    "take_profits": {
        "levels": "original signal reference TP1/TP2/TP3 (1R/2R/3R)",
        "allocation": "TP1 = 1/3 of original, TP2 = 1/2 of remainder, TP3 = exact remainder",
        "activation": "resting limit orders filled by shared WickFillMode (high >= level)",
        "basis_levels": "DOCUMENTED",
        "basis_allocation": "ASSUMPTION_NOT_A_DECISION",
        "basis_activation": "ASSUMPTION_NOT_A_DECISION (engine wick-fill semantics)",
    },
    "strategy_stop": {
        "trigger": "fully closed M15 Close < current M15 EMA21 (strict; wicks ignored)",
        "exit_fill": "remaining quantity at following M15 open * (1 - slippage_rate) "
        "via ClosePosition at the next open",
        "same_candle_tp": "TP limit fills already standing in the trigger/exit candle "
        "are kept; the reference simulator ignored them (explained difference)",
        "tp1_breakeven_move": "DISABLED via DISABLE_TP1_BREAKEVEN_MOVE (no approved rule)",
        "basis_trigger": "DOCUMENTED (execution decision 2)",
        "basis_exit_fill": "ASSUMPTION_NOT_A_DECISION",
    },
    "disaster_stop": {"rule": "none placed; reference stop is sizing reference only", "basis": "DOCUMENTED boundary"},
    "max_holding": {"rule": "no force-close applied", "basis": "GENUINELY_UNRESOLVED"},
    "overlap": {
        "rule": "one open position per strategy+symbol; extra entries OVERLAP_SKIPPED, "
        "signal machine unaffected",
        "basis": "DOCUMENTED (execution decision 6)",
    },
    "sizing": {
        "implementation": "shared PositionSizer via TradeExecutor (soft_sl=reference stop, "
        "no hard SL placed)",
        "entry_price_basis": "actual next-open order price (reference sim used reference close)",
        "config_source": "shared config.yaml risk + backtest blocks (no V2-only block)",
        "basis": "RESOLVED_CODE",
    },
    "fees": {
        "BINANCE_FUTURES": {"taker": "0.0005", "maker": "0.0002",
                            "source": "binance.info FAQ 360033544231 (regular user USD-M)",
                            "source_updated": "2026-05-01", "checked_on": "2026-09-19"},
        "HYPERLIQUID_PERP": {"taker": "0.00045", "maker": "0.00015",
                             "source": "hyperliquid.gitbook.io perps base tier",
                             "source_updated": "about 1 month before 2026-09-19", "checked_on": "2026-09-19"},
        "fee_formula": "shared MockExchange executor: qty * price * rate; maker on limit TP, taker on market",
        "funding": "EXCLUDED_BY_DESIGN",
        "basis_rates": "RESOLVED_EXTERNAL",
        "basis_formula": "RESOLVED_CODE",
    },
    "accounting": {
        "rule": "every fill kept with qty/price/fee/rate/kind/time; gross and net realized R "
        "stored separately on the fixed risk-amount basis; EOD closes labeled, never "
        "blended silently; venues reported separately, no pooling",
        "basis": "DOCUMENTED accounting fields",
    },
    "slippage_rate": {"value": "0.001", "basis": "ASSUMPTION_NOT_A_DECISION"},
    "excluded": ["funding (EXCLUDED_BY_DESIGN)", "parameter search / optimization", "live promotion"],
}


def protocol_json_text() -> str:
    return json.dumps(PROTOCOL, indent=2, sort_keys=True) + "\n"


def freeze_protocol(path: Path) -> str:
    text = protocol_json_text()
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"protocol_sha256": digest, "protocol": json.loads(text)}, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return digest


def _shared_config(data_dir: Path, taker: float, maker: float, slippage: float) -> dict:
    with (REPO_ROOT / "config.yaml").open("r", encoding="utf-8") as handle:
        file_cfg = yaml.safe_load(handle) or {}
    risk = dict(file_cfg.get("risk", {}))
    backtest = dict(file_cfg.get("backtest", {}))
    risk["taker_fee"] = taker
    risk["maker_fee"] = maker
    return {"risk": risk, "backtest": backtest, "slippage_pct": slippage}


def run_venue(
    venue: str, symbols: list[str], frames, config: dict, progress: bool = False
) -> dict[str, Any]:
    """Run one venue through the shared engine; return engine outputs + ledger."""
    dfs = {symbol: frames.alt_m15[symbol] for symbol in symbols}
    balance = float(config.get("backtest", {}).get("initial_balance", 100000))
    risk_cfg = config.get("risk", {})
    exchange = MockExchange(
        initial_balance=balance,
        leverage=int(risk_cfg.get("leverage", 10)),
        taker_fee=float(risk_cfg.get("taker_fee", DEFAULT_TAKER_FEE)),
        maker_fee=float(risk_cfg.get("maker_fee", DEFAULT_MAKER_FEE)),
        slippage_pct=float(config.get("slippage_pct", 0.0)),
    )
    CoreV21EngineStrategy.bind_frames(frames)
    try:
        engine = PortfolioEngine(
            event_source=BatchPortfolioEventSource(dfs, start_idx=0),
            strategy_class=CoreV21EngineStrategy,
            exchange=exchange,
            config=config,
            symbols=symbols,
        )
        results = engine.run()
        strategy: CoreV21EngineStrategy = engine.strategy
        strategy.finalize({s: dfs[s].index[-1].isoformat() for s in symbols})
        return {
            "results": results,
            "trade_history": [dict(row) for row in exchange.trade_history],
            "ledger": [dict(row) for row in strategy.ledger],
            "not_ready": dict(strategy.not_ready_counts()),
        }
    finally:
        CoreV21EngineStrategy.unbind_frames()


def _fill_order_key(row: dict) -> tuple:
    """Chronological fill order: candle time, then numeric fill sequence.

    Fill rows mint a fresh ``mock_N`` id at execution time, so the numeric
    suffix orders fills within a candle (string sort would put mock_10
    before mock_9 and fake overlaps when a TP3 close and a new entry share
    a candle).
    """
    raw_id = str(row.get("id", ""))
    try:
        seq = int(raw_id.rsplit("_", 1)[-1])
    except ValueError:
        seq = 0
    return (str(row.get("time")), seq)


def build_positions(
    trade_history: list[dict], ledger: list[dict], risk_amount: D
) -> tuple[list[dict], list[dict]]:
    """Join engine fills into positions via the one-position-per-symbol invariant."""
    positions: list[dict[str, Any]] = []
    skipped = [row for row in ledger if row.get("type") in ("overlap_skipped", "no_fill_candle")]
    open_by_symbol: dict[str, dict[str, Any]] = {}
    remaining_by_symbol: dict[str, D] = {}
    for row in sorted(trade_history, key=_fill_order_key):
        symbol = row["symbol"]
        side = (row.get("side") or "").upper()
        reason = ((row.get("info") or {}).get("exit_reason") or "")
        qty = D(str(row.get("filled", row.get("amount", 0))))
        price = D(str(row.get("price", 0)))
        fee = D(str((row.get("fee") or {}).get("cost", 0)))
        rate = D(str((row.get("fee") or {}).get("rate", 0)))
        open_pos = open_by_symbol.get(symbol)
        remaining = remaining_by_symbol.get(symbol, D("0"))
        if side == "BUY" and not reason:
            if open_pos is not None:
                raise ValueError(f"overlapping engine position for {symbol} (invariant broken)")
            open_pos = {
                "symbol": symbol, "entry_time": str(row.get("time")),
                "entry_fill": str(price), "entry_qty": str(qty),
                "entry_fee": str(fee), "entry_fee_rate": str(rate),
                "fills": [], "close_reason": None, "close_time": None,
            }
            open_by_symbol[symbol] = open_pos
            remaining_by_symbol[symbol] = qty
        elif side == "SELL" and open_pos is not None:
            qty = min(qty, remaining)
            open_pos["fills"].append(
                {"kind": reason or "EXIT", "time": str(row.get("time")),
                 "qty": str(qty), "price": str(price), "fee": str(fee), "fee_rate": str(rate)}
            )
            remaining -= qty
            # Shared trade_history serializes floats: allow the engine's own
            # 1e-8 cleanup-scale dust, recorded explicitly per position.
            entry_qty = D(open_pos["entry_qty"])
            dust_tol = max(abs(entry_qty) * D("1e-9"), D("1e-12"))
            if remaining <= dust_tol:
                open_pos["close_reason"] = reason or "EXIT"
                open_pos["close_time"] = str(row.get("time"))
                open_pos["close_dust_qty"] = str(remaining)
                positions.append(_finish_position(open_pos, risk_amount))
                del open_by_symbol[symbol]
                del remaining_by_symbol[symbol]
            else:
                remaining_by_symbol[symbol] = remaining
    for symbol, open_pos in open_by_symbol.items():  # engine EOD-closes everything
        open_pos["close_reason"] = "UNCLOSED_ENGINE"
        positions.append(_finish_position(open_pos, risk_amount))
    return positions, skipped


def _finish_position(pos: dict[str, Any], risk_amount: D) -> dict[str, Any]:
    entry_qty = D(pos["entry_qty"])
    entry_fill = D(pos["entry_fill"])
    gross = sum((D(f["qty"]) * D(f["price"]) for f in pos["fills"]), D("0")) - entry_qty * entry_fill
    fees = D(pos["entry_fee"]) + sum((D(f["qty"]) * D(f["price"]) * D(f["fee_rate"]) for f in pos["fills"]), D("0"))
    # NOTE: engine-recorded exit fees are authoritative; recompute only as a check.
    recorded = D(pos["entry_fee"]) + sum((D(f["fee"]) for f in pos["fills"]), D("0"))
    net = gross - recorded
    pos["gross_pnl"] = str(gross)
    pos["net_pnl"] = str(net)
    pos["fees_recorded"] = str(recorded)
    pos["fees_recomputed"] = str(fees)
    pos["gross_realized_r"] = str(gross / risk_amount) if risk_amount > 0 else "0"
    pos["net_realized_r"] = str(net / risk_amount) if risk_amount > 0 else "0"
    return pos


def summarize(positions: list[dict]) -> dict[str, Any]:
    gross = sum((D(p["gross_pnl"]) for p in positions), D("0"))
    net = sum((D(p["net_pnl"]) for p in positions), D("0"))
    gross_r = sum((D(p["gross_realized_r"]) for p in positions), D("0"))
    net_r = sum((D(p["net_realized_r"]) for p in positions), D("0"))
    reasons: dict[str, int] = {}
    for pos in positions:
        reasons[pos["close_reason"]] = reasons.get(pos["close_reason"], 0) + 1
    return {
        "positions": len(positions),
        "gross_pnl": str(gross), "net_pnl": str(net),
        "gross_r": str(gross_r), "net_r": str(net_r),
        "close_reasons": reasons,
    }


def check_parity(
    ledger: list[dict], audit_csv: Path, symbols: set[str] | None = None
) -> dict[str, Any]:
    """Entry-event + reference-level parity against the audited replay.

    The audit CSV is grouped per symbol (not globally chronological), so
    order-sensitive list comparison is meaningless.  Parity is therefore:
    same multiset of (symbol, trigger close, event type), same Decimal
    reference levels per event, and the engine ledger internally
    chronological (non-decreasing trigger closes) within one engine run.
    Call once per venue ledger; concatenating venue ledgers would break the
    chronological check artifactually.
    """
    expected: list[tuple] = []
    with audit_csv.open("r", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["event_type"] in ("A_PLUS_LONG", "PULLBACK_LONG"):
                if symbols is not None and row["symbol"] not in symbols:
                    continue
                event = json.loads(row["decision_json"]).get("event") or {}
                levels = event.get("trade_levels") or {}
                expected.append(
                    (row["symbol"], row["trigger_closed_at"], row["event_type"],
                     levels.get("reference_entry"), levels.get("reference_stop"),
                     levels.get("tp1"), levels.get("tp2"), levels.get("tp3"))
                )
    actual: list[tuple] = []
    for row in ledger:
        if row.get("type") == "signal" and row.get("event_type") in ("A_PLUS_LONG", "PULLBACK_LONG"):
            levels = row.get("levels") or {}
            actual.append(
                (row["symbol"], row["closed_at"], row["event_type"],
                 levels.get("reference_entry"), levels.get("reference_stop"),
                 levels.get("tp1"), levels.get("tp2"), levels.get("tp3"))
            )
    key = lambda r: (r[1], r[0], r[2])
    norm = lambda v: str(D(str(v))) if v is not None else None
    norm_row = lambda r: (r[0], r[1], r[2], norm(r[3]), norm(r[4]), norm(r[5]), norm(r[6]), norm(r[7]))
    closes = [r[1] for r in actual]
    return {
        "expected_entry_events": len(expected),
        "actual_entry_events": len(actual),
        "event_multiset_match": sorted(map(key, expected)) == sorted(map(key, actual)),
        "ledger_chronological": all(b >= a for a, b in zip(closes, closes[1:])),
        "levels_match": sorted(map(norm_row, expected)) == sorted(map(norm_row, actual)),
        "audit_csv_globally_chronological": [key(r) for r in expected] == sorted(map(key, expected)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-protocol", action="store_true")
    parser.add_argument("--run-dir", type=Path,
                        default=Path("research/results/core_v2_1_engine_backtest_v1"))
    parser.add_argument("--audit-dir", type=Path,
                        default=Path("research/results/core_v2_1_audit_replay"))
    parser.add_argument("--data-dir", type=Path, default=Path("app/backtest/data"))
    args = parser.parse_args(argv)
    run_dir = args.run_dir
    if args.freeze_protocol:
        print(f"protocol frozen: {freeze_protocol(run_dir / 'protocol.json')}")
        return 0

    frozen = json.loads((run_dir / "protocol.json").read_text(encoding="utf-8"))
    if frozen.get("protocol") != json.loads(protocol_json_text()):
        raise SystemExit("code PROTOCOL drifted from frozen protocol.json; re-freeze first")

    data_dir = args.data_dir if args.data_dir.is_absolute() else REPO_ROOT / args.data_dir
    source = load_available_universe(data_dir, require_all=True)
    frames = build_replay_frames(source)
    symbols = sorted(frames.alt_m15)
    binance = [s for s in symbols if venue_for_symbol(s) == "BINANCE_FUTURES"]
    hyperliquid = [s for s in symbols if venue_for_symbol(s) != "BINANCE_FUTURES"]

    slippage = float(PROTOCOL["slippage_rate"]["value"])
    out: dict[str, Any] = {"protocol_sha256": frozen["protocol_sha256"], "venues": {}}
    all_positions: list[dict] = []
    for venue, syms, taker, maker in (
        ("BINANCE_FUTURES", binance, 0.0005, 0.0002),
        ("HYPERLIQUID_PERP", hyperliquid, 0.00045, 0.00015),
    ):
        if not syms:
            continue
        config = _shared_config(data_dir, taker, maker, slippage)
        risk_amount = D(str(config["backtest"].get("initial_balance", 100000))) * D(
            str(config["risk"].get("risk_per_trade_pct", 0.002))
        )
        ran = run_venue(venue, syms, frames, config)
        positions, skipped = build_positions(ran["trade_history"], ran["ledger"], risk_amount)
        for pos in positions:
            pos["venue"] = venue
        all_positions.extend(positions)
        out["venues"][venue] = {
            "symbols": syms,
            "summary": summarize(positions),
            "skipped": skipped,
            "not_ready_counts": ran["not_ready"],
            "engine_net_profit": ran["results"].get("net_profit"),
            "engine_final_balance": ran["results"].get("final_balance"),
        }
        (run_dir / f"ledger_{venue}.json").write_text(
            json.dumps(ran["ledger"], indent=2) + "\n", encoding="utf-8")

    audit_csv = args.audit_dir / "core_v2_1_replay.csv"
    audit_csv = audit_csv if audit_csv.is_absolute() else REPO_ROOT / audit_csv
    parity_by_venue: dict[str, Any] = {}
    for venue in out["venues"]:
        venue_ledger = json.loads((run_dir / f"ledger_{venue}.json").read_text(encoding="utf-8"))
        parity_by_venue[venue] = check_parity(
            venue_ledger, audit_csv, set(out["venues"][venue]["symbols"])
        )
    parity = {
        "expected_entry_events": sum(p["expected_entry_events"] for p in parity_by_venue.values()),
        "actual_entry_events": sum(p["actual_entry_events"] for p in parity_by_venue.values()),
        "event_multiset_match": all(p["event_multiset_match"] for p in parity_by_venue.values()),
        "ledger_chronological": all(p["ledger_chronological"] for p in parity_by_venue.values()),
        "levels_match": all(p["levels_match"] for p in parity_by_venue.values()),
        "audit_csv_globally_chronological": all(
            p["audit_csv_globally_chronological"] for p in parity_by_venue.values()
        ),
        "by_venue": parity_by_venue,
    }
    out["parity"] = parity
    out["summary_all_venues_separate"] = {v: info["summary"] for v, info in out["venues"].items()}
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "trades.json").write_text(
        json.dumps(all_positions, indent=2) + "\n", encoding="utf-8")
    (run_dir / "results.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    manifest = {
        name: hashlib.sha256((run_dir / name).read_bytes()).hexdigest()
        for name in ("protocol.json", "trades.json", "results.json")
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"parity": parity, "venues": out["summary_all_venues_separate"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
