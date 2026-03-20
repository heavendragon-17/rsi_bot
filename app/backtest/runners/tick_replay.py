"""
Tick-level simulation backtest using SimExchange.

Refactored from run_paper_tick_replay.py — replays aggTrades tick data
through a strategy with realistic SL/TP fill simulation.
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
import structlog

from app.backtest.config_builder import build_backtest_config
from app.backtest.engine import BacktestEngine
from app.core.actions import ClosePosition, DoNothing, MoveSL, OpenPosition, PartialClose
from app.core.constants import WARMUP
from app.core.events import SignalEvent
from app.core.snapshots import ContextSnapshot
from app.trading.exchange.sim.sim_exchange import SimExchange
from app.trading.portfolio.manager import PortfolioManager
from app.trading.strategy.loader import STRATEGY_MAP

logger = structlog.get_logger()


class TickReplayRunner:
    """Tick-level simulation backtest using SimExchange."""

    def __init__(
        self,
        symbol: str,
        timeframe: str,
        balance: float,
        strategy_name: str,
        ohlc_path: str,
        ticks_path: str,
    ):
        self.symbol = symbol
        self.timeframe = timeframe
        self.balance = balance
        self.strategy_name = strategy_name
        self.ohlc_path = ohlc_path
        self.ticks_path = ticks_path

    def run(self, progress_cb=None) -> dict:
        """Execute tick-level replay and return results dict."""
        config = self._build_config()
        strategy_class = STRATEGY_MAP[self.strategy_name]
        strategy = strategy_class(config)

        full_df = self._load_ohlc(strategy)
        exchange = self._make_sim_exchange(config)
        portfolio = PortfolioManager(exchange, config)
        context = ContextSnapshot(state="SCANNING")

        logger.info(
            "replay_start", strategy=self.strategy_name, symbol=self.symbol,
            ohlc_rows=len(full_df), warmup=WARMUP,
        )

        total_candles = len(full_df) - WARMUP
        processed = 0
        total_ticks = 0
        tick_file = open(self.ticks_path, "r", newline="", encoding="utf-8")
        reader = csv.DictReader(tick_file)
        pending_tick: Optional[dict] = None
        tick_exhausted = False

        def _next_tick():
            nonlocal tick_exhausted
            if tick_exhausted:
                return None
            try:
                return next(reader)
            except StopIteration:
                tick_exhausted = True
                return None

        t_start = time.time()

        for candle_idx in range(WARMUP, len(full_df)):
            row = full_df.iloc[candle_idx]
            candle_ts_ms = full_df.index[candle_idx].value // 10**6
            previous_ts_ms = full_df.index[candle_idx - 1].value // 10**6
            exchange._sim_time = candle_ts_ms / 1000.0

            if candle_idx < len(full_df) - 1:
                next_candle_ts_ms = full_df.index[candle_idx + 1].value // 10**6
            else:
                next_candle_ts_ms = candle_ts_ms + (candle_ts_ms - previous_ts_ms)

            candle_open_ms = candle_ts_ms
            candle_close_ms = next_candle_ts_ms

            open_price = Decimal(str(row["open"]))
            exchange.on_kline_open(self.symbol, open_price)

            while True:
                if pending_tick is None:
                    pending_tick = _next_tick()
                if pending_tick is None:
                    break

                tick_ts_raw = pending_tick.get("transact_time", "")
                if not tick_ts_raw.strip().lstrip("-").isdigit():
                    pending_tick = _next_tick()
                    continue

                tick_ts = int(tick_ts_raw)
                if tick_ts < candle_open_ms:
                    pending_tick = _next_tick()
                    continue
                if tick_ts >= candle_close_ms:
                    break

                price = Decimal(pending_tick["price"])
                exchange.on_tick(self.symbol, price, tick_ts / 1000.0)
                total_ticks += 1
                pending_tick = _next_tick()

            df_slice = full_df.iloc[: candle_idx + 1].copy()
            position = portfolio.get_position_snapshot(self.symbol)
            result = strategy.analyze(self.symbol, df_slice, position=position, context=context)
            context = result.new_context

            with exchange.state.lock:
                ex_has_pos = self.symbol in exchange.state.positions
            pm_has_pos = self.symbol in portfolio.positions
            if pm_has_pos and not ex_has_pos:
                portfolio.positions.pop(self.symbol, None)
                context = ContextSnapshot(state="SCANNING")

            for action in result.actions:
                if isinstance(action, OpenPosition) and self.symbol not in portfolio.positions:
                    portfolio.on_signal(_action_to_signal(action))
                elif isinstance(action, ClosePosition):
                    portfolio.close_position(action.symbol, reason=action.reason, price=action.price)
                elif isinstance(action, MoveSL):
                    portfolio.move_stop_loss(action.symbol, action.new_sl_price)
                elif isinstance(action, PartialClose):
                    portfolio.execute_partial_close(
                        action.symbol, action.tp_level, new_sl_price=action.new_sl_price,
                    )

            processed += 1
            if processed % max(1, total_candles // 20) == 0:
                elapsed = time.time() - t_start
                rate = total_ticks / elapsed if elapsed > 0 else 0
                logger.info(
                    "replay_progress",
                    pct=f"{processed / total_candles * 100:.1f}%",
                    candle=f"{processed}/{total_candles}",
                    ticks=total_ticks, rate=f"{rate:,.0f}/s",
                )

            if tick_exhausted and pending_tick is None:
                remaining = total_candles - processed
                if remaining > 0:
                    logger.warning(
                        "tick_data_exhausted",
                        last_candle=full_df.index[candle_idx].strftime("%Y-%m-%d %H:%M"),
                        skipped=remaining,
                    )
                break

        tick_file.close()
        exchange._notification_worker.stop()
        elapsed = time.time() - t_start

        logger.info("replay_done", candles=processed, ticks=total_ticks, elapsed=f"{elapsed:.1f}s")

        results = _compute_results(exchange, self.balance)
        _send_telegram_summary(config, results, self.symbol, self.timeframe, self.strategy_name, elapsed)
        return results

    # ── internal helpers ────────────────────────────────────────────────

    def _build_config(self) -> dict:
        config = build_backtest_config(
            symbol=self.symbol, timeframe=self.timeframe,
            strategy_name=self.strategy_name, initial_balance=self.balance,
        )
        config.setdefault("bot", {})["mode"] = "sim"
        config.setdefault("sim", {})["initial_balance"] = self.balance
        return config

    def _load_ohlc(self, strategy) -> pd.DataFrame:
        data = pd.read_csv(self.ohlc_path)
        data["timestamp"] = pd.to_datetime(data["timestamp"])
        df = data.copy()
        df.set_index("timestamp", inplace=True)
        df["closed"] = True
        df["ts"] = df.index.astype(np.int64) // 10**6
        return strategy.indicators.compute(df, symbol=self.symbol, timeframe="backtest")

    def _make_sim_exchange(self, config: dict) -> SimExchange:
        from app.notification.notification_service import NotificationService
        from app.notification.null_notifier import NullNotifier

        ns = NotificationService(NullNotifier(), mode="mock")
        return SimExchange(config, notification_service=ns)


# ── module-level helpers ────────────────────────────────────────────────────

def _action_to_signal(action: OpenPosition) -> SignalEvent:
    tp_prices = action.tp_prices or []
    return SignalEvent(
        symbol=action.symbol, signal_type="BUY", price=action.entry_price,
        timestamp=datetime.now(), reason=action.reason,
        sl_price=action.sl_price, soft_sl_price=action.soft_sl_price,
        tp1_price=tp_prices[0] if len(tp_prices) > 0 else None,
        tp2_price=tp_prices[1] if len(tp_prices) > 1 else None,
        tp3_price=tp_prices[2] if len(tp_prices) > 2 else None,
        signal_class=action.signal_class,
        lock_profit_price=action.lock_profit_price,
        tp_allocations=action.tp_allocations,
    )


def _compute_results(exchange: SimExchange, initial_balance: float) -> dict:
    """Compute P&L metrics from SimExchange closed_trades."""
    if not exchange.state.closed_trades:
        return {
            "total_trades": 0, "initial_balance": initial_balance,
            "final_balance": float(exchange.state.balance),
            "net_profit": 0.0, "net_profit_pct": 0.0, "closed_trades": [],
        }

    ordered: list[dict] = []
    for ct in exchange.state.closed_trades:
        ordered.append({
            "symbol": ct.symbol, "side": "BUY",
            "price": float(ct.entry_price), "amount": float(ct.amount),
            "pnl": None,
            "time": datetime.fromtimestamp(ct.opened_at, tz=timezone.utc) if ct.opened_at else None,
            "info": {},
            "margin": float(ct.entry_price * ct.amount / 10),
            "notional": float(ct.entry_price * ct.amount), "leverage": 10,
        })
        ordered.append({
            "symbol": ct.symbol, "side": "SELL",
            "price": float(ct.exit_price), "amount": float(ct.amount),
            "pnl": float(ct.pnl_net),
            "time": datetime.fromtimestamp(ct.closed_at, tz=timezone.utc),
            "info": {"exit_reason": ct.exit_reason},
            "margin": float(ct.entry_price * ct.amount / 10),
            "notional": float(ct.exit_price * ct.amount), "leverage": 10,
        })

    df_trades = pd.DataFrame(ordered)
    round_trips = BacktestEngine._build_round_trips(df_trades)
    if round_trips.empty:
        return {
            "total_trades": 0, "initial_balance": initial_balance,
            "final_balance": float(exchange.state.balance),
            "net_profit": 0.0, "net_profit_pct": 0.0, "closed_trades": [],
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
        "metrics": metrics, "risk_metrics": risk_metrics,
        "drawdown": drawdown_full, "monthly_returns": monthly_returns,
        "equity_curve": equity_curve, "drawdown_curve": drawdown_curve,
        "round_trips": rt_list,
        "initial_balance": initial_balance, "final_balance": final_balance,
        "net_profit": realized_pnl, "net_profit_pct": net_pnl_pct,
    }


def _print_report(results: dict, symbol: str, timeframe: str, strategy_name: str) -> None:
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
    print(f"  Max Drawdown     : {d.get('max_drawdown_pct', 0):.2f}%")
    print(f"  Sharpe Ratio     : {r.get('sharpe_ratio', 0):.2f}")
    print(banner)
    monthly = results.get("monthly_returns", {})
    if monthly:
        print("\n  Monthly P&L:")
        for month, v in sorted(monthly.items()):
            sign = "+" if v["pnl"] >= 0 else ""
            print(f"    {month}  {sign}${v['pnl']:.2f}  ({v['trades']} trades)")
    print()


def _send_telegram_summary(
    config: dict, results: dict, symbol: str,
    timeframe: str, strategy_name: str, elapsed: float,
) -> None:
    try:
        from app.notification.telegram_bot import TelegramBot

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

        bot.send_message("\n".join(lines), chat_id=chat_id)
    except Exception as exc:
        logger.warning("telegram_summary_failed", error=str(exc))


# ── CLI entry point ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Tick-level sim backtest using SimExchange",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--ohlc", required=True, help="Path to OHLC CSV")
    parser.add_argument("--ticks", required=True, help="Path to aggTrades tick CSV")
    parser.add_argument("--symbol", type=str, default="BTC/USDT")
    parser.add_argument("--timeframe", type=str, default="5m")
    parser.add_argument("--balance", type=float, default=10_000)
    parser.add_argument("--strategy", type=str, default="rsi_no_retest", choices=list(STRATEGY_MAP.keys()))
    args = parser.parse_args()

    runner = TickReplayRunner(
        symbol=args.symbol, timeframe=args.timeframe,
        balance=args.balance, strategy_name=args.strategy,
        ohlc_path=args.ohlc, ticks_path=args.ticks,
    )
    results = runner.run()
    _print_report(results, args.symbol, args.timeframe, args.strategy)


if __name__ == "__main__":
    main()
