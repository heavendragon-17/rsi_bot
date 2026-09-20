"""Core V2.1 two-year Binance-only history backtest on the shared engine (research-only).

Runs ONE frozen protocol (``core-v2.1-engine-history-binonly-v1``) over an
explicit two-calendar-year evaluation window with the thin
:class:`CoreV21EngineStrategy` adapter inside the existing
:class:`PortfolioEngine` + :class:`MockExchange` stack.  No parallel
simulator: signals, sizing, fills, fees, and accounting all flow through
production-path components.

How this differs from ``engine_backtest.py`` (which is preserved untouched):

* Binance venue only.  Hyperliquid ``PUMP`` is excluded from this run only;
  its data file, live universe entry, and venue routing are unchanged.
* Indicators are seeded from each file's earliest available history
  (research-only ``HISTORY_ANCHOR``), NOT from the locked live feature
  anchor (``2026-06-29T11:15Z``).  The live anchor, live config, and live
  runtime are untouched.
* Per-symbol state warmup over up to ``STATE_WARMUP_BARS`` pre-window
  candles (state-machine memory is <= 5 bars by construction: a WAIT cycle
  is at most 4 bars; ARMED/DISARMED flips per candle).  No orders are
  placed before the evaluation start.
* One shared-capital portfolio execution (``BatchPortfolioEventSource`` is
  an implementation detail, not per-symbol accounts).  New listings join
  once eligible; nothing is fabricated.

Funding is EXCLUDED_BY_DESIGN.  No pooled cross-venue returns exist here
(single venue); per-symbol breakdowns are diagnostic, not sub-accounts.

Usage (repo root, project interpreter)::

    python -m app.backtest.core_v2_1.engine_history --freeze-protocol \\
        --eval-start 2024-09-21T00:00:00+00:00 --eval-end 2026-09-20T14:30:00+00:00 \\
        --run-dir research/results/core_v2_1_history_binonly_2y_v1
    python -m app.backtest.core_v2_1.engine_history \\
        --run-dir research/results/core_v2_1_history_binonly_2y_v1 \\
        --data-dir app/backtest/data
"""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import structlog
import yaml

from app.backtest.core_v2_1.coverage import data_path_for_symbol, normalize_symbol
from app.backtest.core_v2_1.data import (
    CandleDataError,
    load_stored_candles,
    resample_closed_candles,
)
from app.backtest.core_v2_1.engine_adapter import (
    CoreV21EngineStrategy,
    _SymbolState,
)
from app.backtest.core_v2_1.engine_backtest import (
    _shared_config,
    build_positions,
    check_parity,
    summarize,
)
from app.backtest.core_v2_1.replay import (
    CoreV21PointInTimeReplay,
    ReplayFrames,
    _readiness_reasons,
    _to_core_evaluation_input,
    build_point_in_time_context,
)
from app.backtest.engine.batch_event_source import BatchPortfolioEventSource
from app.backtest.engine.portfolio_engine import PortfolioEngine
from app.backtest.exchange.mock_exchange import MockExchange
from app.core.constants import DEFAULT_MAKER_FEE, DEFAULT_TAKER_FEE
from app.trading.strategy.core_v2_1 import (
    CONFIG_VERSION,
    INDICATOR_SEED_CONVENTION,
    INDICATOR_VERSION,
    STRATEGY_VERSION,
    CoreState,
    compute_alt_h1_indicators,
    compute_btc_h1_indicators,
    compute_btc_h4_indicators,
    compute_m15_indicators,
    evaluate_core_v2_1,
)
from app.trading.strategy.core_v2_1.config import (
    HYPERLIQUID_TRADE_CANDIDATES,
    TRADE_CANDIDATES,
)

logger = structlog.get_logger()

REPO_ROOT = Path(__file__).resolve().parents[3]
PROTOCOL_NAME = "core-v2.1-engine-history-binonly-v1"
SHORT_PROTOCOL_NAME = "core-v2.1-engine-history-binonly-short-v1"
BTC_SYMBOL = "BTCUSDT"

# Research-only history anchor: indicators seed from each file's earliest
# available row.  This NEVER replaces the locked live feature anchor.
HISTORY_ANCHOR_VERSION = "core-v2.1-history-anchor-file-start-v1"

# State-machine memory is <= 5 M15 bars by construction (WAIT cycles are at
# most 4 bars; ARMED/DISARMED flips per candle), so 5000 pre-window bars
# (≈52 days, the standardized seed-contract length) is a 1000x margin.
STATE_WARMUP_BARS = 5000

# The shared Engine skips analyze() while effective_len < 50, i.e. the first
# 49 candles of each event-source frame.  Each frame therefore starts 49
# bars before the evaluation start so the first analyzed candle is exactly
# the evaluation start (late listings: first analyzed is later, reported).
LEADIN_BARS = 49

BINANCE_SYMBOLS: tuple[str, ...] = tuple(
    s for s in TRADE_CANDIDATES if s not in frozenset(HYPERLIQUID_TRADE_CANDIDATES)
)

D = Decimal

# ---------------------------------------------------------------------------
# Frozen protocol.  basis: DOCUMENTED | RESOLVED_CODE | RESOLVED_EXTERNAL |
# ASSUMPTION_NOT_A_DECISION | GENUINELY_UNRESOLVED | EXCLUDED_BY_DESIGN
# ---------------------------------------------------------------------------
PROTOCOL: dict[str, Any] = {
    "name": PROTOCOL_NAME,
    "engine": "shared PortfolioEngine + MockExchange + PortfolioManager, single Binance venue, one shared-capital portfolio (no parallel simulator)",
    "universe": {
        "rule": "24 Binance trade candidates (locked universe minus Hyperliquid PUMP) + BTC benchmark for context only; PUMP excluded from this run only, its file/routing/config untouched",
        "basis": "DOCUMENTED (locked universe minus one venue exclusion)",
    },
    "history_anchor": {
        "rule": "research-only file-start seeding per symbol (HISTORY_ANCHOR_VERSION); live feature anchor 2026-06-29T11:15Z untouched and unused here",
        "basis": "ASSUMPTION_NOT_A_DECISION (research-only preparation mode)",
    },
    "indicators": {
        "rule": "locked compute_m15/alt_h1/btc_h1/btc_h4 builders over full per-symbol history, then window-sliced; H1/H4 derived by resampling M15",
        "basis": "DOCUMENTED (same builders as live/replay)",
    },
    "state_warmup": {
        "rule": "CoreState warmed over up to 5000 contiguous pre-window bars per symbol (state memory <= 5 bars by construction); no orders before evaluation start; late listings warm from file start and join once eligible",
        "basis": "ASSUMPTION_NOT_A_DECISION (warmup length) + DOCUMENTED (evaluator semantics)",
    },
    "signals": {
        "rule": "locked CoreV21 evaluator; A_PLUS_LONG and PULLBACK_LONG open positions; state machine advances during positions so re-arm stays deterministic",
        "basis": "DOCUMENTED",
    },
    "entry": {
        "fill": "entry-candle M15 open * (1 + slippage_rate) via shared MockExchange market slippage; labeled candle-price proxy",
        "timing": "adapter defers the signal one candle; entry action carries the next open",
        "basis": "DOCUMENTED (execution decision 3)",
    },
    "take_profits": {
        "levels": "original signal reference TP1/TP2/TP3 (1R/2R/3R)",
        "allocation": "TP1 = 1/3 of original, TP2 = 1/2 of remainder, TP3 = exact remainder",
        "activation": "resting limit orders filled by shared WickFillMode (high >= level); entry-candle TP excluded by construction (limits placed after that candle's fill check); same-candle TP-before-stop fills are kept",
        "basis_levels": "DOCUMENTED",
        "basis_allocation": "ASSUMPTION_NOT_A_DECISION",
        "basis_activation": "ASSUMPTION_NOT_A_DECISION (engine wick-fill semantics)",
    },
    "strategy_stop": {
        "trigger": "fully closed M15 Close < current M15 EMA21 (strict; wicks ignored)",
        "exit_fill": "remaining quantity at following M15 open * (1 - slippage_rate) via ClosePosition at the next open; fills timestamped at that candle's close (candle-price proxy)",
        "tp1_breakeven_move": "DISABLED via DISABLE_TP1_BREAKEVEN_MOVE (no approved rule)",
        "basis_trigger": "DOCUMENTED (execution decision 2)",
        "basis_exit_fill": "ASSUMPTION_NOT_A_DECISION",
    },
    "disaster_stop": {"rule": "none placed; reference stop is sizing reference only", "basis": "DOCUMENTED boundary"},
    "max_holding": {"rule": "no force-close applied", "basis": "GENUINELY_UNRESOLVED"},
    "overlap": {
        "rule": "one open position per strategy+symbol; extra entries OVERLAP_SKIPPED, signal machine unaffected",
        "basis": "DOCUMENTED (execution decision 6)",
    },
    "capital": {
        "rule": "one shared MockExchange account for all 24 symbols; concurrent positions share margin; fund-skipped entries are detected by entry_fired-vs-BUY cross-check and reported, never silently dropped",
        "basis": "RESOLVED_CODE (shared PortfolioEngine capital model)",
    },
    "sizing": {
        "implementation": "shared PositionSizer via TradeExecutor (soft_sl=reference stop, no hard SL placed)",
        "entry_price_basis": "actual next-open order price",
        "config_source": "shared config.yaml risk + backtest blocks (no V2-only block)",
        "basis": "RESOLVED_CODE",
    },
    "fees": {
        "BINANCE_FUTURES": {"taker": "0.0005", "maker": "0.0002",
                            "source": "binance.info FAQ 360033544231 (regular user USD-M)",
                            "source_updated": "2026-05-01", "checked_on": "2026-09-19"},
        "fee_formula": "shared MockExchange executor: qty * price * rate; maker on limit TP, taker on market",
        "funding": "EXCLUDED_BY_DESIGN",
        "basis_rates": "RESOLVED_EXTERNAL",
        "basis_formula": "RESOLVED_CODE",
    },
    "accounting": {
        "rule": "every fill kept with qty/price/fee/rate/kind/time; gross and net realized R stored separately on the fixed risk-amount basis; EOD closes labeled explicitly, never blended; UNCLOSED_ENGINE is defensive-only",
        "basis": "DOCUMENTED accounting fields",
    },
    "slippage_rate": {"value": "0.001", "basis": "ASSUMPTION_NOT_A_DECISION"},
    "parity": {
        "rule": "engine entry events + Decimal reference levels must match an independent CoreV21PointInTimeReplay over identically warmed frames (same window); mismatch fails closed",
        "basis": "DOCUMENTED (independent re-evaluation)",
    },
    "excluded": ["funding (EXCLUDED_BY_DESIGN)", "Hyperliquid PUMP (venue exclusion for this run)", "parameter search / optimization", "live promotion"],
}


def protocol_json_text(direction: str = "long") -> str:
    return json.dumps(protocol_for(direction), indent=2, sort_keys=True) + "\n"


def protocol_for(direction: str) -> dict[str, Any]:
    """Return the frozen protocol mapping for ``direction``.

    ``long`` returns the original long-only PROTOCOL verbatim (existing
    frozen packets keep validating).  ``short`` returns a research-only
    mirror: identical signals/timing/sizing/fees, SELL entries with
    mirrored TP/stop levels and a mirrored (close > EMA21) stop trigger.
    """
    if direction == "long":
        return PROTOCOL
    if direction != "short":
        raise ValueError(f"unknown direction {direction!r}")
    import copy

    short = copy.deepcopy(PROTOCOL)
    short["name"] = SHORT_PROTOCOL_NAME
    short["engine"] = (
        "shared PortfolioEngine + MockExchange + PortfolioManager, single Binance venue, "
        "one shared-capital portfolio (no parallel simulator), SHORT-MIRROR research variant"
    )
    short["signals"] = {
        "rule": "locked CoreV21 evaluator unchanged (A_PLUS_LONG/PULLBACK_LONG signal timing identical to long run); every fired entry is mirrored to a SELL",
        "basis": "DOCUMENTED (same signals) + ASSUMPTION_NOT_A_DECISION (direction mirror)",
    }
    short["entry"] = {
        "fill": "entry-candle M15 open * (1 - slippage_rate) via shared MockExchange side-aware market slippage (adverse to trader); labeled candle-price proxy",
        "timing": "adapter defers the signal one candle; entry action carries the next open (same timing as long)",
        "side": "SELL (short); quantity from the same $risk sizing basis (soft stop one risk distance above fill)",
        "basis": "DOCUMENTED (execution decision 3) + ASSUMPTION_NOT_A_DECISION (mirror)",
    }
    short["take_profits"] = {
        "levels": "mirrored at fill: exec_tpN = fill_open - (signal_tpN - signal_reference_entry), preserving 1R/2R/3R distances",
        "allocation": "TP1 = 1/3 of original, TP2 = 1/2 of remainder, TP3 = exact remainder",
        "activation": "resting BUY limit orders filled by shared WickFillMode (low <= level); entry-candle TP excluded by construction; same-candle TP-before-stop fills are kept",
        "basis_levels": "ASSUMPTION_NOT_A_DECISION (mirror)",
        "basis_allocation": "ASSUMPTION_NOT_A_DECISION",
        "basis_activation": "ASSUMPTION_NOT_A_DECISION (engine wick-fill semantics)",
    }
    short["strategy_stop"] = {
        "trigger": "fully closed M15 Close > current M15 EMA21 (strict mirror of long; wicks ignored)",
        "exit_fill": "remaining quantity at following M15 open via ClosePosition at the next open (side-aware slippage); fills timestamped at that candle's close (candle-price proxy)",
        "tp1_breakeven_move": "DISABLED via DISABLE_TP1_BREAKEVEN_MOVE (no approved rule)",
        "basis_trigger": "ASSUMPTION_NOT_A_DECISION (mirror of execution decision 2)",
        "basis_exit_fill": "ASSUMPTION_NOT_A_DECISION",
    }
    short["direction"] = {
        "rule": "short mirror: entry SELL at next open, exec soft stop = fill + risk_1r, exec TPs mirrored below fill; signal population, warmup, window, capital, fees identical to long run",
        "basis": "ASSUMPTION_NOT_A_DECISION (research variant, not a strategy decision)",
    }
    short["excluded"] = [*PROTOCOL["excluded"], "long direction (see sibling long-only packet)"]
    return short


def freeze_protocol(path: Path, *, eval_start: str, eval_end: str, direction: str = "long") -> str:
    payload = {
        "protocol": json.loads(protocol_json_text(direction)),
        "direction": direction,
        "eval_start": eval_start,
        "eval_end": eval_end,
        "symbols": list(BINANCE_SYMBOLS),
        "benchmark": BTC_SYMBOL,
    }
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"protocol_sha256": digest, **payload}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return digest


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_history_frames(
    data_dir: Path, symbols: tuple[str, ...]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Strict-load full per-symbol M15 histories (canonical UTC-close frames).

    Returns (frames, file_meta).  Fails closed on gaps/duplicates/invalid
    OHLC — never fabricates candles.
    """
    frames: dict[str, Any] = {}
    meta: dict[str, Any] = {}
    for symbol in [*symbols, BTC_SYMBOL]:
        path = data_dir / f"{symbol}_15m.csv"
        if not path.is_file():
            raise CandleDataError(f"Missing required history file: {path.name}")
        loaded = load_stored_candles(path, strict=True)
        if loaded.frame.empty:
            raise CandleDataError(f"{symbol} history is empty after validation")
        frames[symbol] = loaded.frame
        meta[symbol] = {
            "path": str(path.resolve()),
            "sha256": sha256_file(path),
            "rows": int(loaded.report.output_rows),
            "first_open_utc": loaded.frame["open_at"].iloc[0].isoformat(),
            "last_close_utc": loaded.frame.index[-1].isoformat(),
            "gaps": int(loaded.report.gap_count),
            "missing": int(loaded.report.missing_candles),
            "dups": int(loaded.report.duplicate_timestamps),
        }
    return frames, meta


def build_history_indicators(
    frames: dict[str, Any], symbols: tuple[str, ...]
) -> ReplayFrames:
    """Enrich full-history frames with the locked indicator builders."""
    alt_m15 = {s: compute_m15_indicators(frames[s].copy()) for s in symbols}
    alt_h1 = {
        s: compute_alt_h1_indicators(resample_closed_candles(frames[s], "1h"))
        for s in symbols
    }
    btc_h1 = compute_btc_h1_indicators(resample_closed_candles(frames[BTC_SYMBOL], "1h"))
    btc_h4 = compute_btc_h4_indicators(resample_closed_candles(frames[BTC_SYMBOL], "4h"))
    return ReplayFrames(alt_m15=alt_m15, alt_h1=alt_h1, btc_h1=btc_h1, btc_h4=btc_h4)


def warmup_state(
    symbol: str,
    m15: Any,
    alt_h1: Any,
    btc_h1: Any,
    btc_h4: Any,
    warm_start: pd.Timestamp,
    warm_end_exclusive: pd.Timestamp,
) -> tuple[CoreState, dict[str, int]]:
    """Replay the locked evaluator over [warm_start, warm_end_exclusive).

    Warms only the CoreState (no ledger export, no orders).  NOT_READY
    candles leave state unchanged, mirroring the point-in-time replay.
    """
    state = CoreState.initial()
    warmed, not_ready = 0, 0
    closes = m15.index[(m15.index >= warm_start) & (m15.index < warm_end_exclusive)]
    for closed_at in closes:
        context = build_point_in_time_context(
            symbol=symbol, as_of=closed_at, m15=m15,
            alt_h1=alt_h1, btc_h1=btc_h1, btc_h4=btc_h4,
        )
        if context is None or _readiness_reasons(context):
            not_ready += 1
            continue
        try:
            evaluation_input = _to_core_evaluation_input(context)
        except Exception as exc:
            raise ValueError(
                f"Core V2.1 warmup input invalid for {symbol} at {closed_at}: {exc}"
            ) from exc
        state = evaluate_core_v2_1(evaluation_input, state).next_state
        warmed += 1
    return state, {"warmed": warmed, "not_ready": not_ready}


def _slice(frame: Any, start: pd.Timestamp, end: pd.Timestamp) -> Any:
    return frame.loc[(frame.index >= start) & (frame.index <= end)].copy()


def run_single_portfolio(
    symbols: tuple[str, ...],
    enriched: ReplayFrames,
    full_m15: dict[str, Any],
    config: dict,
    eval_start: pd.Timestamp,
    eval_end: pd.Timestamp,
    direction: str = "long",
) -> dict[str, Any]:
    """Run one shared-capital Binance portfolio over the frozen window."""
    if direction not in ("long", "short"):
        raise ValueError(f"unknown direction {direction!r}")
    dfs: dict[str, Any] = {}
    coverage: dict[str, Any] = {}
    warm_states: dict[str, Any] = {}
    for symbol in symbols:
        full = enriched.alt_m15[symbol]
        # 49-bar lead-in so the engine's 50-candle gate ends exactly at (or,
        # for late listings, after) the evaluation start.
        lead_start = eval_start - pd.Timedelta(minutes=15 * LEADIN_BARS)
        if lead_start < full.index[0]:
            lead_start = full.index[0]
        window = _slice(full, lead_start, eval_end)
        if len(window) < 50:
            coverage[symbol] = {
                "status": "EXCLUDED_SHORT_WINDOW",
                "window_rows": len(window),
                "reason": "fewer than 50 candles; engine gate would never analyze",
            }
            continue
        first_analyzed = window.index[49]
        warm_end = first_analyzed  # exclusive
        warm_bars = full.index[(full.index >= warm_end - pd.Timedelta(minutes=15 * STATE_WARMUP_BARS)) & (full.index < warm_end)]
        warm_start = warm_bars[0] if len(warm_bars) else full.index[0]
        state, counts = warmup_state(
            symbol, full, enriched.alt_h1[symbol],
            enriched.btc_h1, enriched.btc_h4, warm_start, warm_end,
        )
        warm_states[symbol] = state
        dfs[symbol] = window
        coverage[symbol] = {
            "status": "INCLUDED" if first_analyzed <= eval_end else "EXCLUDED_NO_ANALYZED_CANDLE",
            "file_first_close": full.index[0].isoformat(),
            "file_last_close": full.index[-1].isoformat(),
            "window_first_close": window.index[0].isoformat(),
            "window_last_close": window.index[-1].isoformat(),
            "first_analyzed_close": first_analyzed.isoformat(),
            "eligible_from_start": bool(first_analyzed <= eval_start),
            "warm_start": warm_start.isoformat(),
            "warm_end_exclusive": warm_end.isoformat(),
            "warmup_evaluated": counts["warmed"],
            "warmup_not_ready": counts["not_ready"],
            "warmed_phase": state.phase.value,
        }
    active = [s for s in symbols if dfs.get(s) is not None and coverage[s]["status"] == "INCLUDED"]
    if not active:
        raise CandleDataError("No symbol has an analyzable candle in the frozen window")

    adapter_frames = ReplayFrames(
        alt_m15={s: dfs[s] for s in active},
        alt_h1={s: enriched.alt_h1[s] for s in active},
        btc_h1=enriched.btc_h1,
        btc_h4=enriched.btc_h4,
    )
    balance = float(config.get("backtest", {}).get("initial_balance", 100000))
    risk_cfg = config.get("risk", {})
    exchange = MockExchange(
        initial_balance=balance,
        leverage=int(risk_cfg.get("leverage", 10)),
        taker_fee=float(risk_cfg.get("taker_fee", DEFAULT_TAKER_FEE)),
        maker_fee=float(risk_cfg.get("maker_fee", DEFAULT_MAKER_FEE)),
        slippage_pct=float(config.get("slippage_pct", 0.0)),
    )
    CoreV21EngineStrategy.bind_frames(adapter_frames)
    CoreV21EngineStrategy.SHORT_MODE = (direction == "short")
    try:
        engine = PortfolioEngine(
            event_source=BatchPortfolioEventSource(
                {s: dfs[s] for s in active}, start_idx=0
            ),
            strategy_class=CoreV21EngineStrategy,
            exchange=exchange,
            config=config,
            symbols=active,
        )
        # Pre-seed warmed CoreStates so the first analyzed candle continues
        # the exact 15-minute cadence (last_processed_at = candle before it).
        strategy: CoreV21EngineStrategy = engine.strategy
        for symbol in active:
            seeded = _SymbolState(core=warm_states[symbol])
            strategy._states[symbol] = seeded
        results = engine.run()
        strategy.finalize({s: dfs[s].index[-1].isoformat() for s in active})
        return {
            "results": results,
            "trade_history": [dict(row) for row in exchange.trade_history],
            "ledger": [dict(row) for row in strategy.ledger],
            "not_ready": dict(strategy.not_ready_counts()),
            "coverage": coverage,
            "active_symbols": active,
        }
    finally:
        CoreV21EngineStrategy.SHORT_MODE = False
        CoreV21EngineStrategy.unbind_frames()


def _norm_time(value: Any) -> str:
    """Normalize engine timestamps for comparison.

    Adapter ledger records use ISO ``T`` separators while exchange trade
    rows serialize pandas Timestamps with a space separator; comparing raw
    strings false-flags every fill.  Normalizing both sides through
    ``pd.Timestamp`` removes the formatting difference without touching
    the underlying instants.
    """
    try:
        return pd.Timestamp(value).isoformat()
    except Exception:
        return str(value)


def cross_check_fills(
    trade_history: list[dict], ledger: list[dict], direction: str = "long"
) -> dict[str, Any]:
    """Match every engine entry fill to its adapter entry_fired record.

    Long: entries are BUY fills.  Short mirror: entries are SELL fills.
    A fired entry with no matching fill is an order skip (e.g. insufficient
    margin); a matching-side fill with no fired entry breaks the
    one-position invariant path.
    """
    if direction not in ("long", "short"):
        raise ValueError(f"unknown direction {direction!r}")
    entry_side = "BUY" if direction == "long" else "SELL"
    fired: dict[tuple[str, str], dict] = {}
    for row in ledger:
        if row.get("type") == "entry_fired":
            fired[(row["symbol"], _norm_time(row["fill_time"]))] = row
    buys = [
        row for row in trade_history if (row.get("side") or "").upper() == entry_side
    ]
    matched, buys_without_fired = 0, []
    for row in buys:
        key = (row["symbol"], _norm_time(row.get("time")))
        if key in fired:
            matched += 1
        else:
            buys_without_fired.append(
                {"symbol": row["symbol"], "time": str(row.get("time")), "id": str(row.get("id"))}
            )
    buy_keys = {(row["symbol"], _norm_time(row.get("time"))) for row in buys}
    fired_without_buy = [
        {"symbol": sym, "fill_time": ft, "event_type": rec.get("event_type"), "sequence": rec.get("sequence")}
        for (sym, ft), rec in fired.items()
        if (sym, ft) not in buy_keys
    ]
    return {
        "entry_fired": len(fired),
        "buy_fills": len(buys),
        "matched": matched,
        "buys_without_fired": buys_without_fired,
        "fired_without_buy_order_skips": fired_without_buy,
    }


def enrich_with_family(
    positions: list[dict], ledger: list[dict]
) -> list[dict]:
    """Attach entry event family (A_PLUS_LONG/PULLBACK_LONG) per position."""
    fired: dict[tuple[str, str], str] = {}
    for row in ledger:
        if row.get("type") == "entry_fired":
            fired[(row["symbol"], _norm_time(row["fill_time"]))] = str(row.get("event_type"))
    for pos in positions:
        pos["entry_family"] = fired.get(
            (pos["symbol"], _norm_time(pos["entry_time"])), "UNKNOWN")
        pos["venue"] = "BINANCE_FUTURES"
    return positions


def per_symbol_table(positions: list[dict]) -> dict[str, Any]:
    table: dict[str, Any] = {}
    for pos in positions:
        cell = table.setdefault(pos["symbol"], {
            "positions": 0, "gross": D("0"), "net": D("0"),
            "gross_r": D("0"), "net_r": D("0"), "fees": D("0"),
            "wins": 0, "losses": 0, "tp3": 0, "stops": 0, "eod": 0,
            "unclosed": 0, "families": {}, "first_entry": None, "last_close": None,
        })
        gross, net = D(pos["gross_pnl"]), D(pos["net_pnl"])
        cell["positions"] += 1
        cell["gross"] += gross
        cell["net"] += net
        cell["gross_r"] += D(pos["gross_realized_r"])
        cell["net_r"] += D(pos["net_realized_r"])
        cell["fees"] += D(pos["fees_recorded"])
        cell["wins" if net > 0 else "losses"] += 1
        reason = pos["close_reason"]
        if reason == "TP3":
            cell["tp3"] += 1
        elif reason == "EOD":
            cell["eod"] += 1
        elif reason == "UNCLOSED_ENGINE":
            cell["unclosed"] += 1
        elif "STOP" in reason:
            cell["stops"] += 1
        fam = pos.get("entry_family", "UNKNOWN")
        cell["families"][fam] = cell["families"].get(fam, 0) + 1
        if cell["first_entry"] is None or pos["entry_time"] < cell["first_entry"]:
            cell["first_entry"] = pos["entry_time"]
        if cell["last_close"] is None or (pos["close_time"] or "") > cell["last_close"]:
            cell["last_close"] = pos["close_time"]
    for cell in table.values():
        for key in ("gross", "net", "gross_r", "net_r", "fees"):
            cell[key] = str(cell[key])
    return table


def _chart_signals(ledger: list[dict], run_dir: Path) -> str:
    """Signal-activity chart in the established report-visuals style.

    Returns a base64 PNG (portable, same approach as
    research/core_v2_1_report_visuals.py): entry families, per-symbol
    entries, daily activity, and close-reason mix.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    import pandas as pd
    from collections import Counter

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False})
    signals = [r for r in ledger if r.get("type") == "signal"
               and r.get("event_type") in ("A_PLUS_LONG", "PULLBACK_LONG")]
    fired = [r for r in ledger if r.get("type") == "entry_fired"]
    figure, axes = plt.subplots(2, 2, figsize=(14, 10), layout="constrained")
    figure.suptitle("Core V2.1 | Signal activity (parity-verified population)",
                    fontsize=18, fontweight="bold", color="#142d46")
    ax = axes[0, 0]
    fam = Counter(r["event_type"] for r in signals)
    bars = ax.bar(["Immediate long", "Pullback long"],
                  [fam.get("A_PLUS_LONG", 0), fam.get("PULLBACK_LONG", 0)],
                  color=["#277da1", "#43aa8b"])
    ax.bar_label(bars, padding=5, fontsize=13)
    ax.set(title=f"{len(signals)} entry signals ({len(fired)} fired)", ylabel="Signal count")
    ax.margins(y=0.18)
    ax = axes[0, 1]
    syms = sorted({r["symbol"] for r in signals},
                  key=lambda s: (sum(r["symbol"] == s for r in signals), s))
    imm = Counter(r["symbol"] for r in signals if r["event_type"] == "A_PLUS_LONG")
    pb = Counter(r["symbol"] for r in signals if r["event_type"] == "PULLBACK_LONG")
    ax.barh(syms, [imm[s] for s in syms], label="Immediate", color="#277da1")
    ax.barh(syms, [pb[s] for s in syms], left=[imm[s] for s in syms],
            label="Pullback", color="#43aa8b")
    ax.tick_params(axis="y", labelsize=7)
    ax.set(title="Where the signals occurred", xlabel="Entry signals")
    ax.legend(loc="lower right", fontsize=8)
    ax = axes[1, 0]
    if signals:
        daily = pd.Series(1, index=pd.to_datetime(
            [r["closed_at"] for r in signals], utc=True)).resample("D").sum()
        daily = daily.reindex(pd.date_range(daily.index.min().normalize(),
                                            daily.index.max().normalize(), freq="D"), fill_value=0)
        ax.bar(daily.index, daily.values, color="#277da1", width=0.8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.set(title="Entry activity through time", ylabel="Daily signals (UTC)")
    ax.tick_params(axis="x", rotation=25)
    ax = axes[1, 1]
    stops = sum(1 for r in ledger if r.get("type") == "stop_triggered")
    ax.text(0.5, 0.5, f"{len(fired)} fired entries\n{stops} stop triggers",
            ha="center", va="center", fontsize=13)
    ax.set(title="Fired entries vs stop triggers")
    ax.axis("off")
    import base64 as _b64
    figure.savefig(run_dir / "signals.png", dpi=120, facecolor="white")
    plt.close(figure)
    return "data:image/png;base64," + _b64.b64encode(
        (run_dir / "signals.png").read_bytes()).decode("ascii")


def _chart_pnl(by_symbol: dict[str, Any], monthly: dict, positions: list[dict], run_dir: Path) -> str:
    """P&L charts in the established style: per-symbol net bars, monthly
    net bars, and family net.  Returns a base64 PNG."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from collections import Counter, defaultdict

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False})
    figure, axes = plt.subplots(2, 2, figsize=(14, 10), layout="constrained")
    figure.suptitle("Core V2.1 | P&L evidence (shared-engine fills)",
                    fontsize=18, fontweight="bold", color="#142d46")
    rows = sorted(by_symbol.items(), key=lambda kv: float(kv[1]["net"]))
    ax = axes[0, 0]
    syms = [s.replace("USDT", "") for s, _ in rows]
    nets = [float(c["net"]) for _, c in rows]
    colors = ["#b24c56" if v < 0 else "#43aa8b" for v in nets]
    ax.barh(syms, nets, color=colors)
    ax.axvline(0, color="#51606f", linewidth=0.7)
    ax.tick_params(axis="y", labelsize=7)
    ax.set(title="Net P&L by symbol (USDT)", xlabel="Net")
    ax = axes[0, 1]
    months = sorted(monthly) if isinstance(monthly, dict) else []
    mvals = [float(monthly[m].get("pnl", 0.0)) if isinstance(monthly[m], dict)
             else float(monthly[m]) for m in months]
    ax.bar([m[2:] for m in months], mvals,
           color=["#b24c56" if v < 0 else "#43aa8b" for v in mvals])
    ax.axhline(0, color="#51606f", linewidth=0.7)
    ax.tick_params(axis="x", rotation=45, labelsize=7)
    ax.set(title="Monthly net P&L (engine)", ylabel="USDT")
    ax.margins(y=0.18)
    ax = axes[1, 0]
    fam_net: dict[str, float] = defaultdict(float)
    fam_n: Counter = Counter()
    for p in positions:
        fam = p.get("entry_family", "UNKNOWN")
        fam_net[fam] += float(p["net_pnl"])
        fam_n[fam] += 1
    fams = sorted(fam_net)
    fvals = [fam_net[f] for f in fams]
    bars = ax.bar(fams, fvals, color=["#277da1", "#43aa8b", "#9babc0"][:len(fams)])
    ax.bar_label(bars, fmt="%.0f", padding=4, fontsize=9)
    ax.axhline(0, color="#51606f", linewidth=0.7)
    ax.set(title="Net P&L by entry family",
           xlabel=", ".join(f"{f}: {fam_n[f]}" for f in fams))
    ax.margins(y=0.22)
    ax = axes[1, 1]
    wins = sum(1 for p in positions if float(p["net_pnl"]) > 0)
    tp3 = sum(1 for p in positions if p["close_reason"] == "TP3")
    stops = sum(1 for p in positions if "STOP" in (p["close_reason"] or ""))
    ax.text(0.5, 0.5,
            f"{len(positions)} positions\n{wins} net winners\n{tp3} full ladders (TP3)\n{stops} stop exits",
            ha="center", va="center", fontsize=13)
    ax.set(title="Outcome mix")
    ax.axis("off")
    import base64 as _b64
    figure.savefig(run_dir / "pnl.png", dpi=120, facecolor="white")
    plt.close(figure)
    return "data:image/png;base64," + _b64.b64encode(
        (run_dir / "pnl.png").read_bytes()).decode("ascii")


def _embedded(run_dir: Path, name: str) -> str:
    import base64 as _b64

    return "data:image/png;base64," + _b64.b64encode(
        (run_dir / name).read_bytes()).decode("ascii")


def write_report_html(
    out: dict[str, Any], positions: list[dict], run_dir: Path,
    eval_start: str, eval_end: str, protocol_sha: str, direction: str = "long",
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    summary = out["summary"]
    by_symbol = out["per_symbol"]
    equity = out["engine_results"].get("equity_curve") or []
    drawdown_curve = out["engine_results"].get("drawdown_curve") or []
    monthly = out["engine_results"].get("monthly_returns") or {}

    fig, axes = plt.subplots(2, 1, figsize=(12, 8), layout="constrained")
    fig.suptitle(f"Core V2.1 history (Binance-only, 2y, {direction}) | portfolio equity", fontsize=13, fontweight="bold")
    ax = axes[0]
    if equity:
        import pandas as pd

        eq = pd.DataFrame(equity)
        ax.plot(pd.to_datetime(eq["date"]), eq["balance"], linewidth=1.2)
        ax.set_ylabel("Equity (USDT)")
        ax.grid(alpha=0.3)
    else:
        ax.text(0.5, 0.5, "no equity curve", ha="center")
    ax = axes[1]
    if drawdown_curve:
        import pandas as pd

        dd = pd.DataFrame(drawdown_curve)
        col = "drawdown_pct" if "drawdown_pct" in dd.columns else dd.columns[-1]
        ax.plot(pd.to_datetime(dd.iloc[:, 0]), dd[col], linewidth=1.2, color="#b24c56")
        ax.set_ylabel("Drawdown (%)")
        ax.grid(alpha=0.3)
    else:
        ax.text(0.5, 0.5, "no drawdown curve", ha="center")
    fig.savefig(run_dir / "equity.png", dpi=120, facecolor="white")
    plt.close(fig)

    rows = sorted(by_symbol.items(), key=lambda kv: float(kv[1]["net"]))
    body = "".join(
        f"<tr><td>{sym}</td><td>{c['positions']}</td>"
        f"<td>{float(c['gross']):,.2f}</td><td>{float(c['net']):,.2f}</td>"
        f"<td>{c['wins']}/{c['losses']}</td><td>{c['tp3']}</td><td>{c['stops']}</td>"
        f"<td>{c['eod']}</td></tr>"
        for sym, c in rows
    )
    if isinstance(monthly, dict):
        monthly_items = []
        for k, v in monthly.items():
            if isinstance(v, dict):
                monthly_items.append(
                    (k, float(v.get("pnl", 0.0)), int(v.get("trades", 0))))
            else:
                monthly_items.append((k, float(v), 0))
    else:
        monthly_items = []
    monthly_rows = "".join(
        f"<tr><td>{k}</td><td>{pnl:,.2f}</td><td>{trades}</td></tr>"
        for k, pnl, trades in monthly_items
    )
    excluded = "".join(
        f"<li>{sym}: {info.get('status')} — {info.get('reason', info.get('first_analyzed_close', ''))}</li>"
        for sym, info in out["coverage"].items()
        if info.get("status") != "INCLUDED"
    ) or "<li>none</li>"
    skips = out["fill_cross_check"]["fired_without_buy_order_skips"]
    entry_side = "SELL" if direction == "short" else "BUY"
    skips_html = "".join(
        f"<li>{r['symbol']} {r['fill_time']} {r['event_type']} seq={r['sequence']}</li>" for r in skips
    ) or f"<li>none — every fired entry has a {entry_side} fill</li>"
    parity = out["parity"]
    direction_title = "SHORT-mirror" if direction == "short" else "long-only"
    proto_name = out.get("protocol_name", PROTOCOL_NAME)
    risk = out.get("engine_results", {}).get("risk_metrics", {}) or {}
    dd = out.get("engine_results", {}).get("drawdown", {}) or {}
    ledger_path = run_dir / "ledger_BINANCE_FUTURES.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.is_file() else []
    signals_img = _chart_signals(ledger, run_dir) if ledger else ""
    pnl_img = _chart_pnl(by_symbol, monthly, positions, run_dir)
    equity_img = _embedded(run_dir, "equity.png")
    from html import escape
    summary = out["summary"]
    net = float(summary["net_pnl"])
    stops_n = sum(1 for p in positions if "STOP" in (p["close_reason"] or ""))
    tp3_n = sum(1 for p in positions if p["close_reason"] == "TP3")
    wins_n = sum(1 for p in positions if float(p["net_pnl"]) > 0)
    file_meta = out.get("file_meta", {})
    matched_files = sum(1 for v in file_meta.values() if v.get("gaps", 1) == 0 and v.get("dups", 1) == 0)
    signals_sec = (f'<img src="{signals_img}" alt="Entry families, per-symbol signals and timeline">' if signals_img else "<p>Ledger unavailable; signal charts skipped.</p>")
    html = f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Core V2.1 history backtest (Binance-only, 2y, {direction})</title>
<style>body{{font:16px/1.6 system-ui,sans-serif;color:#20364c;background:#f0f4f8;margin:0}}main{{max-width:1120px;margin:auto;padding:36px 20px}}
h1{{font-size:34px;line-height:1.2}}h2{{margin-top:30px}}.card,.notice{{padding:22px;border-radius:12px;background:white;margin:18px 0}}.notice{{border-left:6px solid #dd924a;background:#fff6e9}}
.metrics{{display:flex;gap:16px;flex-wrap:wrap}}.metric{{flex:1;min-width:150px;background:white;padding:20px;border-radius:12px}}strong.big{{display:block;font-size:30px;color:#166b87}}
img{{width:100%;height:auto;border-radius:10px}}table{{width:100%;border-collapse:collapse}}td,th{{padding:10px;text-align:right;border-bottom:1px solid #dde4ec}}td:first-child,th:first-child{{text-align:left}}
li{{margin-bottom:10px}}small{{color:#536878}}code{{overflow-wrap:anywhere}}details{{margin:18px 0}}.tablewrap{{overflow:auto}}</style><main>
<small>CORE V2.1 / SHARED-ENGINE HISTORY / {direction.upper()} / {escape(eval_start[:10])} to {escape(eval_end[:10])}</small>
<h1>Two-year shared-engine backtest<br>({direction_title}).</h1>
<div class="metrics"><div class="metric"><strong class="big">{summary['positions']}</strong>positions</div>
<div class="metric"><strong class="big">{net:,.0f}</strong>net P&amp;L (USDT)</div>
<div class="metric"><strong class="big">{float(summary['net_r']):,.1f}R</strong>net realized R</div>
<div class="metric"><strong class="big">{out['engine_final_balance']:,.0f}</strong>final equity (100k start)</div>
<div class="metric"><strong class="big">{float(dd.get('max_drawdown_pct', 0)):,.1f}%</strong>max drawdown</div></div>
<div class="card"><b>Window:</b> {escape(eval_start)} → {escape(eval_end)} (UTC, trigger-close inclusive)<br>
<b>Parity:</b> {parity['expected_entry_events']} expected / {parity['actual_entry_events']} actual,
multiset_match={parity['event_multiset_match']}, levels_match={parity['levels_match']}<br>
<b>Protocol:</b> <code>{escape(str(proto_name))}</code> sha <code>{escape(protocol_sha)}</code><br>
<b>Outcomes:</b> {wins_n} net winners, {tp3_n} full ladders (TP3), {stops_n} stop exits<br>
<b>Risk:</b> Sharpe {float(risk.get('sharpe_ratio', 0)):.2f}, Sortino {float(risk.get('sortino_ratio', 0)):.2f},
VaR95 {float(risk.get('var_95', 0)):.2f}<br>
<b>Inputs:</b> {matched_files}/{len(file_meta)} history files strict-clean (0 gaps, 0 dups).
Funding excluded by design. Single Binance venue, one shared-capital portfolio.</div>
<div class="card"><h2>Equity &amp; drawdown</h2><img src="{equity_img}" alt="portfolio equity and drawdown"></div>
<div class="card"><h2>Signal activity</h2>{signals_sec}</div>
<div class="card"><h2>P&amp;L evidence</h2><img src="{pnl_img}" alt="Per-symbol, monthly and family P&L"></div>
<div class="card tablewrap"><h2>Per-symbol (net ascending)</h2>
<table><tr><th>Symbol</th><th>N</th><th>Gross</th><th>Net</th><th>W/L</th><th>TP3</th><th>Stops</th><th>EOD</th></tr>{body}</table></div>
<div class="card tablewrap"><h2>Monthly returns (engine)</h2>
<table><tr><th>Month</th><th>P&amp;L</th><th>Trades</th></tr>{monthly_rows}</table></div>
<div class="card"><h2>Excluded / late-admission symbols</h2><ul>{excluded}</ul></div>
<div class="card"><h2>Order skips (fired entries without {entry_side} fill)</h2><ul>{skips_html}</ul></div>
<div class="card"><h2>Limitations</h2><ul>
<li>Indicator seeding is file-start (research-only); live anchor untouched. Per-symbol seed history differs by listing date.</li>
<li>TP allocation (1/3, 1/2 of rest, remainder), 0.1% slippage, taker-market/maker-limit fees are assumptions, not approvals.</li>
<li>Entry/stop fills are next-open candle-price proxies timestamped at that candle's close.</li>
<li>Same-candle TP-before-stop fills are kept by engine wick-fill semantics (reference sim ignored them).</li>
<li>No disaster stop, no max-holding force-close. EOD exits are forced window-end liquidations, not strategy exits.</li>
<li>New listings (HYPE, GRASS, FARTCOIN, LIT*) join once eligible; early-window coverage differs by symbol — see coverage.json.</li>
<li>SHORT-mirror (if applicable) is a research variant: same signals/timing/sizing/fees, direction flipped with mirrored levels. Not a strategy decision.</li>
</ul></div>
<details><summary>Reproducibility</summary><p>Protocol sha: <code>{escape(protocol_sha)}</code>. See adjacent results.json, trades.json,
engine_results.json and manifest.json for values and hashes. This report performs no optimization or live promotion.</p></details>
</main>"""
    (run_dir / "report.html").write_text(html, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-protocol", action="store_true")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=Path("app/backtest/data"))
    parser.add_argument("--eval-start", default="2024-09-21T00:00:00+00:00")
    parser.add_argument("--eval-end", default=None)
    parser.add_argument("--direction", choices=("long", "short"), default="long",
                        help="long: production long-only path; short: research-only mirror (SELL entries, mirrored TP/stop)")
    args = parser.parse_args(argv)
    direction = args.direction
    run_dir = args.run_dir
    eval_start = pd.Timestamp(args.eval_start)
    if eval_start.tzinfo is None:
        raise SystemExit("--eval-start must be timezone-aware")
    eval_start = eval_start.tz_convert("UTC")

    if args.freeze_protocol:
        if not args.eval_end:
            raise SystemExit("--eval-end is required to freeze the window")
        digest = freeze_protocol(
            run_dir / "protocol.json",
            eval_start=eval_start.isoformat(),
            eval_end=pd.Timestamp(args.eval_end).isoformat(),
            direction=direction,
        )
        print(f"protocol frozen: {digest}")
        return 0

    frozen = json.loads((run_dir / "protocol.json").read_text(encoding="utf-8"))
    if frozen.get("protocol") != json.loads(protocol_json_text(direction)):
        raise SystemExit("code PROTOCOL drifted from frozen protocol.json; re-freeze first")
    if frozen.get("direction", "long") != direction:
        raise SystemExit(
            f"--direction={direction} disagrees with frozen protocol.json "
            f"(direction={frozen.get('direction', 'long')})"
        )
    if pd.Timestamp(frozen["eval_start"]).isoformat() != eval_start.isoformat():
        raise SystemExit("eval-start drifted from frozen protocol.json; re-freeze first")
    eval_end = pd.Timestamp(frozen["eval_end"]).tz_convert("UTC")
    if args.eval_end and pd.Timestamp(args.eval_end).isoformat() != eval_end.isoformat():
        raise SystemExit("eval-end argument disagrees with frozen protocol.json")

    data_dir = args.data_dir if args.data_dir.is_absolute() else REPO_ROOT / args.data_dir
    symbols = BINANCE_SYMBOLS
    logger.info("history_load_start", symbols=len(symbols))

    frames, file_meta = load_history_frames(data_dir, symbols)
    enriched = build_history_indicators(frames, symbols)
    logger.info("history_indicators_ready")

    slippage = float(PROTOCOL["slippage_rate"]["value"])
    config = _shared_config(data_dir, 0.0005, 0.0002, slippage)
    risk_amount = D(str(config["backtest"].get("initial_balance", 100000))) * D(
        str(config["risk"].get("risk_per_trade_pct", 0.002))
    )
    ran = run_single_portfolio(symbols, enriched, frames, config, eval_start, eval_end, direction)
    positions, skipped = build_positions(ran["trade_history"], ran["ledger"], risk_amount, direction)
    positions = enrich_with_family(positions, ran["ledger"])

    # --- fail-closed cross-checks ---
    engine_net = ran["results"].get("net_profit")
    ledger_net = float(sum(D(p["net_pnl"]) for p in positions))
    if abs(engine_net - ledger_net) > 0.01:
        raise SystemExit(
            f"engine net_profit {engine_net} disagrees with ledger net {ledger_net}"
        )
    fill_check = cross_check_fills(ran["trade_history"], ran["ledger"], direction)
    if fill_check["buys_without_fired"]:
        entry_side = "SELL" if direction == "short" else "BUY"
        raise SystemExit(
            f"{entry_side} fills without adapter entry_fired (invariant broken): {fill_check['buys_without_fired']}"
        )
    max_fee_dev = max(
        (abs(float(D(p["fees_recorded"]) - D(p["fees_recomputed"]))) for p in positions),
        default=0.0,
    )
    if max_fee_dev > 1e-6:
        raise SystemExit(f"fee recomputation deviates by {max_fee_dev}")

    # --- independent parity replay over identically warmed frames ---
    warm_slices = {}
    for symbol in ran["active_symbols"]:
        full = enriched.alt_m15[symbol]
        cov = ran["coverage"][symbol]
        warm_start = pd.Timestamp(cov["warm_start"])
        warm_slices[symbol] = full.loc[full.index >= warm_start].copy()
    parity_frames = ReplayFrames(
        alt_m15=warm_slices,
        alt_h1={s: enriched.alt_h1[s] for s in ran["active_symbols"]},
        btc_h1=enriched.btc_h1,
        btc_h4=enriched.btc_h4,
    )
    replay = CoreV21PointInTimeReplay(parity_frames).run(start=eval_start, end=eval_end)
    parity_dir = run_dir / "parity_replay"
    parity_dir.mkdir(parents=True, exist_ok=True)
    parity_paths = replay.ledger.export(parity_dir, metadata={"window": [eval_start.isoformat(), eval_end.isoformat()]})
    parity = check_parity(
        ran["ledger"], Path(parity_paths.csv), set(ran["active_symbols"])
    )
    parity_summary = {
        "expected_entry_events": parity["expected_entry_events"],
        "actual_entry_events": parity["actual_entry_events"],
        "event_multiset_match": parity["event_multiset_match"],
        "ledger_chronological": parity["ledger_chronological"],
        "levels_match": parity["levels_match"],
    }
    if not (parity["event_multiset_match"] and parity["levels_match"]):
        raise SystemExit(f"parity failed: {parity_summary}")

    summary = summarize(positions)
    out: dict[str, Any] = {
        "protocol_sha256": frozen["protocol_sha256"],
        "protocol_name": frozen["protocol"]["name"],
        "direction": direction,
        "eval_start": eval_start.isoformat(),
        "eval_end": eval_end.isoformat(),
        "strategy_version": STRATEGY_VERSION,
        "config_version": CONFIG_VERSION,
        "indicator_version": INDICATOR_VERSION,
        "indicator_seed_convention": INDICATOR_SEED_CONVENTION,
        "history_anchor_version": HISTORY_ANCHOR_VERSION,
        "symbols": list(symbols),
        "active_symbols": ran["active_symbols"],
        "file_meta": file_meta,
        "coverage": ran["coverage"],
        "summary": summary,
        "per_symbol": per_symbol_table(positions),
        "skipped": skipped,
        "not_ready_counts": ran["not_ready"],
        "fill_cross_check": fill_check,
        "max_fee_recompute_deviation": max_fee_dev,
        "parity": {**parity_summary, "by_venue": parity.get("by_venue")},
        "engine_results": ran["results"],
        "engine_net_profit": ran["results"].get("net_profit"),
        "engine_final_balance": ran["results"].get("final_balance"),
        "engine_initial_balance": ran["results"].get("initial_balance"),
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "ledger_BINANCE_FUTURES.json").write_text(
        json.dumps(ran["ledger"], indent=2) + "\n", encoding="utf-8"
    )
    (run_dir / "trades.json").write_text(
        json.dumps(positions, indent=2) + "\n", encoding="utf-8"
    )
    engine_results = dict(ran["results"])
    (run_dir / "results.json").write_text(json.dumps(out, indent=2, default=str) + "\n", encoding="utf-8")
    (run_dir / "engine_results.json").write_text(
        json.dumps(engine_results, indent=2, default=str) + "\n", encoding="utf-8"
    )
    manifest = {
        name: hashlib.sha256((run_dir / name).read_bytes()).hexdigest()
        for name in ("protocol.json", "trades.json", "results.json", "engine_results.json")
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    write_report_html(out, positions, run_dir, eval_start.isoformat(), eval_end.isoformat(), frozen["protocol_sha256"], direction)
    print(json.dumps({"parity": parity_summary, "summary": summary}, indent=2, default=str))
    logger.info(
        "history_backtest_complete",
        run_dir=str(run_dir),
        positions=summary["positions"],
        net=summary["net_pnl"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
