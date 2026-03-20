"""
Sim Exchange Tick Replay
===========================
Run a full strategy backtest against tick-level aggTrades data,
using SimExchange for realistic SL/TP fill simulation instead
of the wick-approximation MockExchange.

Architecture
------------
1. Load OHLC CSV for indicator pre-computation (same as BacktestEngine).
2. Replay candles through the strategy to generate signals/actions.
3. On each candle open → call SimExchange.on_kline_open() to fill pending entries.
4. On each tick from the aggTrades CSV → call SimExchange.on_tick() for SL/TP fills.
5. On each candle close → run strategy.analyze() and dispatch actions via PortfolioManager.
6. After replay → compute results using BacktestEngine.compute_results() logic.

Usage
-----
    python app/backtest/run_paper_tick_replay.py \\
        --ohlc   app/backtest/data/BTCUSDT_5m.csv \\
        --ticks  app/backtest/data/BTCUSDT_ticks_2024_01.csv \\
        --symbol BTC/USDT \\
        --timeframe 5m \\
        --balance 10000

The --ohlc CSV must already cover the same period as --ticks.
You can download it with app/backtest/download_data.py.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import numpy as np
import pandas as pd

# ── project root on path ────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv()

import logging
logging.getLogger().setLevel(logging.WARNING)
import warnings
warnings.filterwarnings("ignore")


from app.backtest.config_builder import build_backtest_config
from app.backtest.engine import BacktestEngine  # for compute_results helpers
from app.core.actions import ClosePosition, DoNothing, MoveSL, OpenPosition, PartialClose
from app.core.events import SignalEvent
from app.trading.portfolio.manager import PortfolioManager
from app.core.snapshots import ContextSnapshot
from app.sim.exchange import SimExchange
from app.strategies.loader import STRATEGY_MAP

# ── constants ────────────────────────────────────────────────────────────────
from app.core.constants import WARMUP


# ── helpers ──────────────────────────────────────────────────────────────────

def _build_config(symbol: str, timeframe: str, balance: float, strategy_name: str) -> dict:
    config = build_backtest_config(
        symbol=symbol,
        timeframe=timeframe,
        strategy_name=strategy_name,
        initial_balance=balance,
    )
    # Ensure mode is sim
    config.setdefault("bot", {})["mode"] = "sim"
    config.setdefault("sim", {})["initial_balance"] = balance
    return config


def _load_ohlc(path: str, symbol: str, strategy) -> pd.DataFrame:
    """Load + indicator-compute the OHLC CSV (same pre-processing as BacktestEngine)."""
    data = pd.read_csv(path)
    data["timestamp"] = pd.to_datetime(data["timestamp"])
    df = data.copy()
    df.set_index("timestamp", inplace=True)
    df["closed"] = True
    df["ts"] = df.index.astype(np.int64) // 10 ** 6
    df = strategy.indicators.compute(df, symbol=symbol, timeframe="backtest")
    return df


def _action_to_signal(action: OpenPosition) -> SignalEvent:
    tp_prices = action.tp_prices or []
    return SignalEvent(
        symbol=action.symbol,
        signal_type="BUY",
        price=action.entry_price,
        timestamp=datetime.now(),
        reason=action.reason,
        sl_price=action.sl_price,
        soft_sl_price=action.soft_sl_price,
        tp1_price=tp_prices[0] if len(tp_prices) > 0 else None,
        tp2_price=tp_prices[1] if len(tp_prices) > 1 else None,
        tp3_price=tp_prices[2] if len(tp_prices) > 2 else None,
        signal_class=action.signal_class,
        lock_profit_price=action.lock_profit_price,
        tp_allocations=action.tp_allocations,
    )


def _make_sim_exchange(config: dict) -> SimExchange:
    """Create a SimExchange with notifications silenced (replay uses summary only)."""
    from app.services.notification.null_notifier import NullNotifier
    from app.services.notification.notification_service import NotificationService
    ns = NotificationService(NullNotifier(), mode="mock")
    ex = SimExchange(config, notification_service=ns)
    return ex


# ── results computation (adapted from BacktestEngine) ─────────────────────────

def _compute_results(exchange: SimExchange, initial_balance: float) -> dict:
    """
    Compute P&L metrics from SimExchange closed_trades.
    Mirrors BacktestEngine.compute_results() using the same helpers.
    """
    trades = []
    for ct in exchange.state.closed_trades:
        # Translate ClosedTrade → trade_history dict format used by BacktestEngine
        trades.append({
            "symbol": ct.symbol,
            "side": "SELL",
            "price": float(ct.exit_price),
            "amount": float(ct.amount),
            "pnl": float(ct.pnl_net),
            "time": datetime.fromtimestamp(ct.closed_at, tz=timezone.utc),
            "info": {"exit_reason": ct.exit_reason},
            "margin": float(ct.pnl_gross / ct.amount) if ct.amount else 0,  # approximate
            "notional": float(ct.exit_price * ct.amount),
        })
        # Pair with a synthetic BUY record for round-trip matching
        trades.append({
            "symbol": ct.symbol,
            "side": "BUY",
            "price": float(ct.entry_price),
            "amount": float(ct.amount),
            "pnl": None,
            "time": datetime.fromtimestamp(ct.opened_at, tz=timezone.utc) if ct.opened_at else None,
            "info": {},
            "margin": 0,
            "notional": float(ct.entry_price * ct.amount),
        })

    if not trades:
        return {
            "total_trades": 0,
            "initial_balance": initial_balance,
            "final_balance": float(exchange.state.balance),
            "net_profit": 0.0,
            "net_profit_pct": 0.0,
            "closed_trades": [],
        }

    # Build a trades DataFrame in the chronological order BacktestEngine expects
    # (alternating BUY then SELL for each round trip)
    ordered = []
    for ct in exchange.state.closed_trades:
        ordered.append({
            "symbol": ct.symbol,
            "side": "BUY",
            "price": float(ct.entry_price),
            "amount": float(ct.amount),
            "pnl": None,
            "time": datetime.fromtimestamp(ct.opened_at, tz=timezone.utc) if ct.opened_at else None,
            "info": {},
            "margin": float(ct.entry_price * ct.amount / 10),  # approx with 10x leverage
            "notional": float(ct.entry_price * ct.amount),
            "leverage": 10,
        })
        ordered.append({
            "symbol": ct.symbol,
            "side": "SELL",
            "price": float(ct.exit_price),
            "amount": float(ct.amount),
            "pnl": float(ct.pnl_net),
            "time": datetime.fromtimestamp(ct.closed_at, tz=timezone.utc),
            "info": {"exit_reason": ct.exit_reason},
            "margin": float(ct.entry_price * ct.amount / 10),
            "notional": float(ct.exit_price * ct.amount),
            "leverage": 10,
        })

    df_trades = pd.DataFrame(ordered)
    round_trips = BacktestEngine._build_round_trips(df_trades)
    if round_trips.empty:
        return {
            "total_trades": 0,
            "initial_balance": initial_balance,
            "final_balance": float(exchange.state.balance),
            "net_profit": 0.0,
            "net_profit_pct": 0.0,
            "closed_trades": [],
        }

    metrics = BacktestEngine._calculate_metrics(round_trips)
    drawdown_full = BacktestEngine._calculate_drawdown(round_trips, initial_balance)
    risk_metrics = BacktestEngine._calculate_risk_metrics(round_trips, drawdown_full, initial_balance)
    monthly_returns = BacktestEngine._calculate_monthly_returns(round_trips)

    rt_list = round_trips.to_dict(orient="records")
    equity_curve = BacktestEngine._build_equity_curve_dated(rt_list, initial_balance)
    drawdown_curve = BacktestEngine._build_drawdown_curve_dated(equity_curve, initial_balance)

    final_balance = float(exchange.state.balance)
    realized_pnl = float(round_trips["pnl"].sum())
    net_pnl_pct = (realized_pnl / initial_balance * 100) if initial_balance > 0 else 0.0

    return {
        "metrics": metrics,
        "risk_metrics": risk_metrics,
        "drawdown": drawdown_full,
        "monthly_returns": monthly_returns,
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
        "round_trips": rt_list,
        "initial_balance": initial_balance,
        "final_balance": final_balance,
        "net_profit": realized_pnl,
        "net_profit_pct": net_pnl_pct,
    }


def _print_report(results: dict, symbol: str, timeframe: str, strategy_name: str) -> None:
    """Print a concise text summary of the backtest results."""
    m = results.get("metrics", {})
    r = results.get("risk_metrics", {})
    d = results.get("drawdown", {})

    banner = "=" * 60
    print(f"\n{banner}")
    print(f" TICK-LEVEL PAPER BACKTEST RESULTS")
    print(f" Symbol: {symbol}  |  Timeframe: {timeframe}  |  Strategy: {strategy_name}")
    print(banner)
    print(f"  Initial Balance  : ${results['initial_balance']:>12,.2f}")
    print(f"  Final Balance    : ${results['final_balance']:>12,.2f}")
    print(f"  Net Profit       : ${results['net_profit']:>+12,.2f}  ({results['net_profit_pct']:+.2f}%)")
    print(f"  Total Trades     : {m.get('total_trades', 0)}")
    print(f"  Win Rate         : {m.get('win_rate', 0):.1f}%")
    print(f"  Profit Factor    : {m.get('profit_factor', 0):.2f}")
    print(f"  Avg Win / Loss   : ${m.get('avg_win', 0):+,.2f} / ${m.get('avg_loss', 0):+,.2f}")
    print(f"  Max Drawdown     : {d.get('max_drawdown_pct', 0):.2f}%")
    print(f"  Sharpe Ratio     : {r.get('sharpe_ratio', 0):.2f}")
    print(f"  Sortino Ratio    : {r.get('sortino_ratio', 0):.2f}")
    print(f"  TP1/TP2/TP3      : {m.get('tp1_count',0)} / {m.get('tp2_count',0)} / {m.get('tp3_count',0)}")
    print(f"  SL hits          : {m.get('sl_count', 0)}")
    print(f"  Max Consec Wins  : {m.get('max_consec_wins', 0)}")
    print(f"  Max Consec Loss  : {m.get('max_consec_losses', 0)}")
    print(f"  Avg Hold (hrs)   : {m.get('avg_hold_hours', 0):.1f}")
    print(banner)

    # Monthly breakdown
    monthly = results.get("monthly_returns", {})
    if monthly:
        print("\n  Monthly P&L:")
        for month, v in sorted(monthly.items()):
            sign = "+" if v["pnl"] >= 0 else ""
            print(f"    {month}  {sign}${v['pnl']:.2f}  ({v['trades']} trades)")
    print()


def _send_telegram_summary(
    config: dict,
    results: dict,
    symbol: str,
    timeframe: str,
    strategy_name: str,
    elapsed: float,
) -> None:
    """Send a single Telegram message summarising the entire tick replay."""
    try:
        from app.services.notification.telegram_bot import TelegramBot
        sim_cfg = config.get("sim", config.get("paper_sim", {}))
        token_override = sim_cfg.get("telegram_token", "").strip()
        token_env = "SIM_TELEGRAM_BOT_TOKEN" if token_override else "TELEGRAM_BOT_TOKEN"
        bot = TelegramBot(token_env=token_env)
        chat_id = sim_cfg.get("chat_id", "").strip() or None

        m = results.get("metrics", {})
        r = results.get("risk_metrics", {})
        d = results.get("drawdown", {})
        monthly = results.get("monthly_returns", {})

        lines = [
            "📊 <b>TICK REPLAY RESULTS</b>",
            f"Symbol: <code>{symbol}</code>  |  TF: <code>{timeframe}</code>  |  Strat: <code>{strategy_name}</code>",
            "",
            f"💰 Net P&L: <b>${results['net_profit']:+,.2f}</b> ({results['net_profit_pct']:+.2f}%)",
            f"📈 Balance: ${results['initial_balance']:,.2f} → ${results['final_balance']:,.2f}",
            f"🎯 Trades: {m.get('total_trades', 0)}  |  Win: {m.get('win_rate', 0):.1f}%  |  PF: {m.get('profit_factor', 0):.2f}",
            f"📉 Max DD: {d.get('max_drawdown_pct', 0):.2f}%  |  Sharpe: {r.get('sharpe_ratio', 0):.2f}",
            f"⏱ {elapsed:.0f}s runtime",
        ]

        if monthly:
            lines.append("")
            lines.append("<b>Monthly:</b>")
            for month, v in sorted(monthly.items()):
                sign = "+" if v["pnl"] >= 0 else ""
                lines.append(f"  {month}: {sign}${v['pnl']:.2f} ({v['trades']}t)")

        msg = "\n".join(lines)
        bot.send_message(msg, chat_id=chat_id)
        print("[Replay] Telegram summary sent ✓")
    except Exception as e:
        print(f"[Replay] Could not send Telegram summary: {e}")


# ── main replay loop ─────────────────────────────────────────────────────────

def run_replay(
    ohlc_path: str,
    ticks_path: str,
    symbol: str,
    timeframe: str,
    balance: float,
    strategy_name: str,
) -> dict:
    print(f"[Replay] Strategy={strategy_name}, Symbol={symbol}, TF={timeframe}, Balance=${balance:,.0f}")

    config = _build_config(symbol, timeframe, balance, strategy_name)
    strategy_class = STRATEGY_MAP[strategy_name]
    strategy = strategy_class(config)

    # 1. Pre-compute indicators on the full OHLC dataset
    print("[Replay] Pre-computing indicators on OHLC data…")
    full_df = _load_ohlc(ohlc_path, symbol, strategy)
    print(f"[Replay] OHLC rows: {len(full_df):,}  (warm-up: {WARMUP}, active: {len(full_df)-WARMUP:,})")

    # 2. Determine tick time window from OHLC index
    ohlc_start_ts = full_df.index[WARMUP].value // 10**6   # ms
    ohlc_end_ts   = full_df.index[-1].value  // 10**6 + 60_000  # add 1 extra minute

    # 3. Create SimExchange and PortfolioManager
    # Notifications are silenced at creation (NullNotifier injected by _make_sim_exchange).
    # A single Telegram summary is sent after the replay completes.
    exchange = _make_sim_exchange(config)
    portfolio = PortfolioManager(exchange, config)
    context = ContextSnapshot(state="SCANNING")

    # 4. Build an iterator over tick rows (low-memory streaming)
    print(f"[Replay] Streaming ticks from: {ticks_path}")
    print("[Replay] Starting replay… (this may take a while for 40M+ tick files)")

    # Map candle close timestamps → slice of ticks that belong IN that candle
    # We will read the tick file once per candle using a generator approach.
    # To avoid loading 40M rows into RAM, we open the file once and advance
    # it concurrently with the candle loop.

    tick_file = open(ticks_path, "r", newline="", encoding="utf-8")
    reader = csv.DictReader(tick_file)

    total_candles = len(full_df) - WARMUP
    processed_candles = 0
    total_ticks_fed = 0

    # Ring buffer: pending ticks that belong to the current or next candle.
    # We peek ahead so ticks crossing a candle boundary are handled correctly.
    pending_tick: Optional[dict] = None  # one lookahead tick
    tick_exhausted = False

    def _next_tick():
        nonlocal tick_exhausted
        if tick_exhausted:
            return None
        try:
            row = next(reader)
            return row
        except StopIteration:
            tick_exhausted = True
            return None

    t_start = time.time()

    for candle_idx in range(WARMUP, len(full_df)):
        row = full_df.iloc[candle_idx]
        candle_ts_ms = full_df.index[candle_idx].value // 10**6   # candle OPEN time
        previous_ts_ms = full_df.index[candle_idx - 1].value // 10**6

        # Set simulated clock so SimExchange timestamps match candle time
        exchange._sim_time = candle_ts_ms / 1000.0

        # Determine the candle's time window
        # Candle covers: (previous candle close, this candle close]
        # In Binance 5m bars: open_ms = index, close_ms = open_ms + 5*60*1000 - 1
        # We approximate using the index gap between consecutive candles.
        if candle_idx < len(full_df) - 1:
            next_candle_ts_ms = full_df.index[candle_idx + 1].value // 10**6
        else:
            next_candle_ts_ms = candle_ts_ms + (candle_ts_ms - previous_ts_ms)

        candle_open_ms  = candle_ts_ms
        candle_close_ms = next_candle_ts_ms

        # 4a. Signal candle open → fill pending_open entry orders
        open_price = Decimal(str(row["open"]))
        exchange.on_kline_open(symbol, open_price)

        # 4b. Feed all ticks that fall within this candle's window
        while True:
            if pending_tick is None:
                pending_tick = _next_tick()

            if pending_tick is None:
                # tick file exhausted — stop replay (no tick data for remaining candles)
                break

            tick_ts_raw = pending_tick.get("transact_time", "")
            if not tick_ts_raw.strip().lstrip('-').isdigit():
                # Skip header rows or malformed lines (e.g. duplicate header in CSV)
                pending_tick = _next_tick()
                continue
            tick_ts = int(tick_ts_raw)

            if tick_ts < candle_open_ms:
                # tick is before the candle window — skip
                pending_tick = _next_tick()
                continue

            if tick_ts >= candle_close_ms:
                # tick belongs to the next candle — stop consuming
                break

            # Tick is within this candle
            price = Decimal(pending_tick["price"])
            exchange.on_tick(symbol, price, tick_ts / 1000.0)
            total_ticks_fed += 1
            pending_tick = _next_tick()

        # 4c. Strategy analysis on candle close (same logic as MultiSymbolRunner)
        df_slice = full_df.iloc[: candle_idx + 1].copy()
        position = portfolio.get_position_snapshot(symbol)
        result = strategy.analyze(symbol, df_slice, position=position, context=context)
        context = result.new_context

        # Sync TP fills that happened via exchange ticks (SimExchange already did this
        # via on_tick(), but we still need to reconcile PortfolioManager state)
        with exchange.state.lock:
            ex_has_pos = symbol in exchange.state.positions
        pm_has_pos = symbol in portfolio.positions
        if pm_has_pos and not ex_has_pos:
            # Exchange closed the position via SL/TP tick — clean up PortfolioManager
            portfolio.positions.pop(symbol, None)
            context = ContextSnapshot(state="SCANNING")

        # Dispatch actions from strategy
        for action in result.actions:
            if isinstance(action, OpenPosition):
                if symbol not in portfolio.positions:
                    signal = _action_to_signal(action)
                    portfolio.on_signal(signal)
            elif isinstance(action, ClosePosition):
                portfolio.close_position(action.symbol, reason=action.reason, price=action.price)
            elif isinstance(action, MoveSL):
                portfolio.move_stop_loss(action.symbol, action.new_sl_price)
            elif isinstance(action, PartialClose):
                portfolio.execute_partial_close(action.symbol, action.tp_level, new_sl_price=action.new_sl_price)

        processed_candles += 1

        # Progress logging every 5%
        pct = processed_candles / total_candles * 100
        if processed_candles % max(1, total_candles // 20) == 0:
            elapsed = time.time() - t_start
            rate = total_ticks_fed / elapsed if elapsed > 0 else 0
            print(
                f"[Replay] {pct:5.1f}%  candle {processed_candles}/{total_candles}"
                f"  ticks fed: {total_ticks_fed:,}  ({rate:,.0f} ticks/s)"
            )

        # Stop if tick data is exhausted — continuing without ticks would
        # produce inaccurate SL/TP fills (only on_kline_open, no tick scan).
        if tick_exhausted and pending_tick is None:
            remaining = total_candles - processed_candles
            if remaining > 0:
                last_candle_date = full_df.index[candle_idx].strftime('%Y-%m-%d %H:%M')
                print(f"\n[Replay] ⚠ Tick data exhausted at {last_candle_date}")
                print(f"[Replay]   Stopping early — {remaining} candles skipped (no tick coverage)")
                print(f"[Replay]   To cover the full OHLC range, download more tick data.")
            break

    tick_file.close()
    
    # Wait for the background notification thread to flush its queue
    exchange._notification_worker.stop()
    
    elapsed = time.time() - t_start

    print(f"\n[Replay] Done! {processed_candles} candles, {total_ticks_fed:,} ticks in {elapsed:.1f}s")

    # 5. Compute and return results
    res = _compute_results(exchange, balance)
    
    # 6. Send ONE summary message to Telegram (replaces per-trade spam)
    _send_telegram_summary(config, res, symbol, timeframe, strategy_name, elapsed)

    return res


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Tick-level sim backtest using SimExchange",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--ohlc", required=True,
        help="Path to the OHLC CSV (e.g. app/backtest/data/BTCUSDT_5m.csv)",
    )
    parser.add_argument(
        "--ticks", required=True,
        help="Path to the aggTrades tick CSV (e.g. app/backtest/data/BTCUSDT_ticks_2024_01.csv)",
    )
    parser.add_argument("--symbol",    type=str, default="BTC/USDT",       help="Trading pair")
    parser.add_argument("--timeframe", type=str, default="5m",             help="Candle timeframe")
    parser.add_argument("--balance",   type=float, default=10_000,         help="Initial USDT balance")
    parser.add_argument(
        "--strategy", type=str, default="rsi_no_retest",
        choices=list(STRATEGY_MAP.keys()),
        help="Strategy to use",
    )
    args = parser.parse_args()

    results = run_replay(
        ohlc_path=args.ohlc,
        ticks_path=args.ticks,
        symbol=args.symbol,
        timeframe=args.timeframe,
        balance=args.balance,
        strategy_name=args.strategy,
    )

    _print_report(results, args.symbol, args.timeframe, args.strategy)


if __name__ == "__main__":
    main()
