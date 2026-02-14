"""
Backtest Executor
=================
Orchestrates a full backtest run:
  1. Creates a DB run record
  2. Resolves data path from symbol + timeframe
  3. Runs BacktestEngine + BacktestReporter
  4. Persists results to DB
  5. Publishes SSE progress events

Usage (async, from FastAPI route):
    run_id = await run_backtest(session_id, config, loop)
"""
import asyncio
import os
from typing import Optional

from app.backtest.engine import BacktestEngine
from app.backtest.reporting import BacktestReporter
from app.strategies.loader import load_strategy
from app.db.connection import get_connection
from app.db.repositories import run_repo, session_repo
from app.api.sse import publish_from_thread, get_queue


# ─────────────────────────────────────────────
# Symbol helpers
# ─────────────────────────────────────────────

# Known quote currencies — longest first to avoid partial matches
_QUOTE_CURRENCIES = ["USDT", "USDC", "BUSD", "USD", "ETH", "BTC"]


def normalize_symbol(raw: str) -> str:
    """
    Accept any common user input and return the base ticker only (uppercase).

    Examples:
        "BTC/USDT" -> "BTC"
        "BTC/USD"  -> "BTC"
        "BTCUSDT"  -> "BTC"
        "BTC"      -> "BTC"
        "eth"      -> "ETH"
    """
    s = raw.upper().strip()
    if "/" in s:
        return s.split("/")[0]
    for quote in _QUOTE_CURRENCIES:
        if s.endswith(quote) and len(s) > len(quote):
            return s[: -len(quote)]
    return s


def resolve_data_path(symbol: str, timeframe: str) -> str:
    """
    Build CSV path from symbol + timeframe.
    Tries two naming conventions:
      1. BTC_USDT_15m.csv  (underscore-separated, e.g. downloaded via download_data)
      2. BTCUSDT_15m.csv   (no slash, e.g. run_batch_analysis convention)

    Args:
        symbol: Raw symbol string (any format)
        timeframe: e.g. "15m", "1h"

    Returns:
        str: Absolute path of the first existing file, or the underscore variant if neither exists.
    """
    base = normalize_symbol(symbol)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    data_dir = os.path.join(project_root, "data")

    # Convention 1: BTC_USDT_15m.csv
    path1 = os.path.join(data_dir, f"{base}_USDT_{timeframe}.csv")
    if os.path.exists(path1):
        return path1

    # Convention 2: BTCUSDT_15m.csv
    path2 = os.path.join(data_dir, f"{base}USDT_{timeframe}.csv")
    if os.path.exists(path2):
        return path2

    # Return path1 (the preferred convention) so the "not found" error is descriptive
    return path1


# ─────────────────────────────────────────────
# Config builder
# ─────────────────────────────────────────────

def build_engine_config(api_config: dict) -> dict:
    """
    Transform the flat API config dict into the nested config dict
    expected by BacktestEngine / BacktestReporter.

    API config fields (from UI backtestStore):
        symbol, timeframe, strategy, startDate, endDate,
        capital, leverage, riskPercent,
        params: { rsi_period, ema_fast, ema_slow, tp1_rr, tp2_rr,
                  sl_buffer_pct, overbought, oversold }

    Returns nested engine config.
    """
    params = api_config.get("params", {})
    symbol = api_config.get("symbol", "BTC/USDT")
    base = normalize_symbol(symbol)
    full_symbol = f"{base}/USDT"

    return {
        "symbols": [full_symbol],
        "strategy": api_config.get("strategy", "rsi_no_retest"),
        "backtest": {
            "initial_balance": float(api_config.get("capital", 10000)),
            "start_date": api_config.get("startDate"),
            "end_date": api_config.get("endDate"),
        },
        "risk": {
            "leverage": int(api_config.get("leverage", 1)),
            "risk_per_trade_pct": float(api_config.get("riskPercent", 1)) / 100,
            "use_risk_based_sizing": True,
            "tp1_close_pct": 0.50,
            "tp2_close_pct": 0.50,
        },
        "indicators": {
            "rsi_period": int(params.get("rsi_period", 14)),
            "ema_fast": int(params.get("ema_fast", 9)),
            "ema_slow": int(params.get("ema_slow", 21)),
            "overbought": int(params.get("overbought", 70)),
            "oversold": int(params.get("oversold", 30)),
        },
        "tp": {
            "tp1_rr": float(params.get("tp1_rr", 1.5)),
            "tp2_rr": float(params.get("tp2_rr", 3.0)),
        },
        "sl": {
            "sl_buffer_pct": float(params.get("sl_buffer_pct", 0.5)) / 100,
        },
        # Passthrough for reporter
        "timeframe": api_config.get("timeframe", "15m"),
    }


# ─────────────────────────────────────────────
# Synchronous worker (runs in thread pool)
# ─────────────────────────────────────────────

def _run_backtest_sync(run_id: int, session_id: str, api_config: dict, loop: asyncio.AbstractEventLoop) -> dict:
    """
    Blocking backtest worker. Designed to run inside a thread pool executor.

    Args:
        run_id: Pre-created run ID
        session_id: Session ID
        api_config: Raw config from API request
        loop: The running event loop (for publishing SSE events)

    Returns:
        dict: Metrics dict on success, {"error": str} on failure
    """

    def emit(event_type: str, data: dict) -> None:
        publish_from_thread(run_id, event_type, data, loop)

    try:
        # ── Mark running ──────────────────────────────
        with get_connection() as conn:
            run_repo.update_run_status(conn, run_id, "running")

        emit("progress", {"pct": 5, "message": "Resolving data file..."})

        # ── Resolve data path ─────────────────────────
        symbol = api_config.get("symbol", "BTC/USDT")
        timeframe = api_config.get("timeframe", "15m")
        data_path = resolve_data_path(symbol, timeframe)

        if not os.path.exists(data_path):
            raise FileNotFoundError(f"Data file not found: {data_path}")

        emit("progress", {"pct": 10, "message": "Loading strategy..."})

        # ── Build engine config ───────────────────────
        engine_config = build_engine_config(api_config)

        # ── Load strategy class ───────────────────────
        strategy_class = load_strategy(engine_config)

        emit("progress", {"pct": 15, "message": "Initializing engine..."})

        # ── Run BacktestEngine ────────────────────────
        engine = BacktestEngine(data_path, strategy_class, engine_config)

        emit("progress", {"pct": 20, "message": "Running backtest..."})
        engine.run()

        emit("progress", {"pct": 60, "message": "Calculating metrics..."})

        # ── Compute metrics via reporter internals ────
        import pandas as pd
        trades = engine.exchange.trade_history
        if not trades:
            # No signals fired — complete with zero metrics (not an error)
            with get_connection() as conn:
                run_repo.save_run_config(conn, run_id, {
                    "symbol": engine_config["symbols"][0],
                    "is_batch_mode": False,
                    "timeframe": timeframe,
                    "start_date": api_config.get("startDate") or "",
                    "end_date": api_config.get("endDate") or "",
                    "initial_capital": str(api_config.get("capital", 10000)),
                    "leverage": engine_config["risk"]["leverage"],
                    "risk_per_trade_pct": str(engine_config["risk"]["risk_per_trade_pct"]),
                    "params": api_config.get("params", {}),
                })
                run_repo.save_run_results(conn, run_id, {"total_trades": 0, "win_rate": 0})
                run_repo.update_run_status(conn, run_id, "completed")
            zero_summary = {
                "run_id": run_id,
                "status": "completed",
                "metrics": {
                    "net_profit": 0.0, "net_profit_pct": 0.0,
                    "total_trades": 0, "win_rate": 0.0,
                    "profit_factor": 0.0, "sharpe_ratio": 0.0,
                    "max_drawdown_pct": 0.0,
                },
            }
            emit("done", zero_summary)
            return zero_summary

        df = pd.DataFrame(trades)
        reporter = BacktestReporter(
            engine.exchange,
            engine_config,
            initial_balance=float(api_config.get("capital", 10000)),
            symbol=engine_config["symbols"][0],
            timeframe=timeframe,
            strategy_name=api_config.get("strategy", "rsi_no_retest"),
        )

        round_trips = reporter._build_round_trips(df)
        metrics = reporter._calculate_metrics(round_trips)
        drawdown = reporter._calculate_drawdown(round_trips)
        risk_metrics = reporter._calculate_risk_metrics(round_trips, drawdown)
        monthly_returns = reporter._calculate_monthly_returns(round_trips)

        # Net PnL
        realized_pnl = float(round_trips["pnl"].sum()) if not round_trips.empty else 0.0
        initial_balance = float(api_config.get("capital", 10000))
        net_pnl_pct = (realized_pnl / initial_balance) * 100

        emit("progress", {"pct": 75, "message": "Saving results to database..."})

        # ── Persist to DB ─────────────────────────────
        with get_connection() as conn:
            # Run config
            run_config = {
                "symbol": engine_config["symbols"][0],
                "is_batch_mode": False,
                "timeframe": timeframe,
                "start_date": api_config.get("startDate") or "",
                "end_date": api_config.get("endDate") or "",
                "initial_capital": str(initial_balance),
                "leverage": engine_config["risk"]["leverage"],
                "risk_per_trade_pct": str(engine_config["risk"]["risk_per_trade_pct"]),
                "params": api_config.get("params", {}),
            }
            run_repo.save_run_config(conn, run_id, run_config)

            # Run results — map reporter fields to DB fields
            results = {
                "net_profit": str(realized_pnl),
                "net_profit_pct": net_pnl_pct,
                "gross_profit": str(metrics.get("gross_profit", 0)),
                "gross_loss": str(metrics.get("gross_loss", 0)),
                "win_rate": metrics.get("win_rate", 0),
                "profit_factor": metrics.get("profit_factor", 0),
                "expectancy": metrics.get("expectancy", 0),
                "max_drawdown_pct": drawdown.get("max_drawdown_pct", 0),
                "max_drawdown_value": str(drawdown.get("max_drawdown_value", 0)),
                "max_drawdown_duration_days": drawdown.get("max_dd_duration", 0),
                "volatility": risk_metrics.get("volatility", 0),
                "sharpe_ratio": risk_metrics.get("sharpe_ratio", 0),
                "sortino_ratio": risk_metrics.get("sortino_ratio", 0),
                "calmar_ratio": risk_metrics.get("calmar_ratio", 0),
                "total_trades": metrics.get("total_trades", 0),
                "winning_trades": metrics.get("win_count", 0),
                "losing_trades": metrics.get("loss_count", 0),
                "avg_win": str(metrics.get("avg_win", 0)),
                "avg_loss": str(metrics.get("avg_loss", 0)),
                "largest_win": str(metrics.get("largest_win", 0)),
                "largest_loss": str(metrics.get("largest_loss", 0)),
                "max_consecutive_wins": metrics.get("max_consec_wins", 0),
                "max_consecutive_losses": metrics.get("max_consec_losses", 0),
                "avg_hold_time_hours": metrics.get("avg_hold_hours", 0),
                "exit_reasons": metrics.get("exit_reason_counts", {}),
            }
            run_repo.save_run_results(conn, run_id, results)

            # Equity curve timeseries
            equity_curve = drawdown.get("equity_curve", [initial_balance])
            run_repo.save_run_timeseries(
                conn,
                run_id,
                equity_curve=equity_curve,
                monthly_returns=monthly_returns,
            )

            # Trades from round_trips
            if not round_trips.empty:
                trades_to_save = []
                for _, rt in round_trips.iterrows():
                    trades_to_save.append({
                        "symbol": rt.get("symbol", engine_config["symbols"][0]),
                        "side": "BUY",
                        "entry_time": str(rt.get("entry_time", "")),
                        "exit_time": str(rt.get("exit_time", "")),
                        "hold_time_hours": rt.get("hold_duration_hours"),
                        "entry_price": str(rt.get("entry_price", "")),
                        "exit_price": str(rt.get("avg_exit_price", "")),
                        "quantity": str(rt.get("amount", "")),
                        "size_usd": str(rt.get("notional", "")),
                        "pnl": str(rt.get("pnl", "")),
                        "pnl_pct": rt.get("pnl_pct"),
                        "exit_reason": rt.get("exit_reason", ""),
                    })
                run_repo.save_trades(conn, run_id, trades_to_save)

            # Mark completed
            run_repo.update_run_status(conn, run_id, "completed")

        emit("progress", {"pct": 95, "message": "Finalizing..."})

        # Build summary for SSE done event
        summary = {
            "run_id": run_id,
            "status": "completed",
            "metrics": {
                "net_profit": realized_pnl,
                "net_profit_pct": net_pnl_pct,
                "total_trades": metrics.get("total_trades", 0),
                "win_rate": metrics.get("win_rate", 0),
                "profit_factor": metrics.get("profit_factor", 0),
                "sharpe_ratio": risk_metrics.get("sharpe_ratio", 0),
                "max_drawdown_pct": drawdown.get("max_drawdown_pct", 0),
            },
        }

        emit("done", summary)
        return summary

    except Exception as exc:
        error_msg = str(exc)
        try:
            with get_connection() as conn:
                run_repo.update_run_status(conn, run_id, "failed")
        except Exception:
            pass
        emit("error", {"message": error_msg, "run_id": run_id})
        return {"error": error_msg, "run_id": run_id}


# ─────────────────────────────────────────────
# Async entry point (called from FastAPI route)
# ─────────────────────────────────────────────

async def run_backtest(session_id: str, api_config: dict) -> int:
    """
    Create a run record and launch the backtest in a thread pool.
    Returns run_id immediately (non-blocking).

    The thread publishes SSE events via publish_from_thread().
    Connect to GET /api/backtest/{run_id}/progress to stream progress.
    """
    loop = asyncio.get_running_loop()

    # Look up strategy_id from DB (default strategy seed = id 1)
    strategy_name = api_config.get("strategy", "rsi_no_retest")
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT id FROM strategies WHERE name = ? LIMIT 1", (strategy_name,)
        )
        row = cursor.fetchone()
        strategy_id = row[0] if row else 1

    # Pre-create the SSE queue so the client can connect before the thread starts
    get_queue.__doc__  # noqa — just ensure module is imported
    # Actually create the run first, then the queue
    with get_connection() as conn:
        run_id = run_repo.create_run(
            conn,
            strategy_id=strategy_id,
            session_id=session_id,
            run_type="backtest",
        )

    # Create queue before launching thread (so client can connect immediately)
    from app.api.sse import get_queue as _get_queue
    _get_queue(run_id)

    # Launch in thread pool — non-blocking
    loop.run_in_executor(
        None,
        _run_backtest_sync,
        run_id,
        session_id,
        api_config,
        loop,
    )

    return run_id
