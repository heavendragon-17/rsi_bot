"""
Backtest routes.

POST   /api/backtest/run                  — start a backtest
GET    /api/backtest/{run_id}/progress    — SSE stream
DELETE /api/backtest/{run_id}             — cancel
GET    /api/backtest/{run_id}             — run detail (metrics + trades)
GET    /api/backtest/{run_id}/timeseries  — equity/drawdown curves (lazy)
"""
from __future__ import annotations

import asyncio
import json
import os
import zlib
from datetime import date, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api import executor as exc_mod
from app.api.schemas import (
    BacktestRequest,
    BacktestStartResponse,
    RunDetail,
    TimeseriesResponse,
)
from app.backtest.config_builder import build_backtest_config
from app.repository.backtest.database import SessionLocal

from app.api.schemas import (
    BatchSymbolResult,
    BatchRunDetail,
    PortfolioRunDetail,
    BatchTimeseriesResponse,
    PortfolioTimeseriesResponse,
)
from app.repository.backtest.models import (
    BatchRun, BatchRunConfig, BatchRunResult,
    PortfolioRun, PortfolioRunConfig, PortfolioRunResult, PortfolioTrade
)
from app.repository.backtest.models import (
    Run,
    RunConfig,
    RunResult,
    RunTimeseries,
    Strategy,
    Tag,
    Trade,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/backtest", tags=["backtest"])

DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "app", "backtest", "data")
)

STRATEGY_MAP: dict[str, Any] = {}


def _load_strategies():
    global STRATEGY_MAP
    if not STRATEGY_MAP:
        from app.strategies.rsi_no_retest import RsiNoRetestStrategy
        from app.strategies.rsi_wma_retest import RsiWmaRetestStrategy

        STRATEGY_MAP = {
            "rsi_no_retest": RsiNoRetestStrategy,
            "rsi_wma_retest": RsiWmaRetestStrategy,
        }
    return STRATEGY_MAP


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _csv_path(symbol: str, timeframe: str) -> str:
    safe = symbol.replace("/", "")
    return os.path.join(DATA_DIR, f"{safe}_{timeframe}.csv")


# ---------------------------------------------------------------------------
# POST /api/backtest/run
# ---------------------------------------------------------------------------



@router.post("/run", status_code=201, response_model=BacktestStartResponse)
async def start_backtest(body: BacktestRequest, db: Session = Depends(get_db)):
    mode = body.mode

    strategies = _load_strategies()
    strategy_class = strategies.get(body.strategy)
    if strategy_class is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown strategy: {body.strategy}. Available: {list(strategies)}",
        )

    strat_row = db.query(Strategy).filter_by(name=body.strategy).first()
    if strat_row is None:
        raise HTTPException(status_code=400, detail=f"Strategy '{body.strategy}' not seeded in DB")

    loop = asyncio.get_event_loop()

    if mode == "single":
        csv_path = _csv_path(body.symbols[0], body.timeframe)
        if not os.path.exists(csv_path):
            safe = body.symbols[0].replace("/", "")
            raise HTTPException(
                status_code=400,
                detail=f"Data file not found: {safe}_{body.timeframe}.csv. Download data first.",
            )

        run = Run(
            strategy_id=strat_row.id,
            status="running",
            started_at=datetime.utcnow(),
        )
        db.add(run)
        db.flush()

        cfg = RunConfig(
            run_id=run.id,
            symbol=body.symbols[0],
            timeframe=body.timeframe,
            start_date=date.fromisoformat(body.start_date),
            end_date=date.fromisoformat(body.end_date),
            initial_capital=body.initial_capital,
            leverage=body.leverage,
            risk_per_trade_pct=body.risk_per_trade_pct,
            fee_tier=body.fee_tier,
            slippage_model=body.slippage_model,
            slippage_pct=body.slippage_pct,
            params=body.params,
        )
        db.add(cfg)
        db.commit()

        run_id = run.id
        exc_mod.create_progress_queue(run_id)
        progress_cb = exc_mod.make_progress_callback(run_id, loop)

        engine_config = build_backtest_config(
            symbol=body.symbols[0],
            timeframe=body.timeframe,
            strategy_name=body.strategy,
            initial_balance=float(body.initial_capital),
            leverage=body.leverage,
            risk_per_trade_pct=float(body.risk_per_trade_pct),
            params=body.params,
        )

        def _run_backtest():
            from app.backtest.engine import BacktestEngine
            try:
                engine = BacktestEngine(csv_path, strategy_class, engine_config)
                results = engine.run(on_progress=progress_cb)
                _persist_results(run_id, results)
                exc_mod.publish_event(run_id, loop, "complete", {"run_id": run_id, "status": "completed"})
            except Exception as err:
                logger.error("backtest_worker_error", run_id=run_id, error=str(err))
                _mark_failed(run_id, str(err))
                exc_mod.publish_event(run_id, loop, "error", {"run_id": run_id, "message": str(err)})
            finally:
                exc_mod.cleanup_job(run_id)

        exc_mod.submit_backtest(run_id, _run_backtest)
        return BacktestStartResponse(run_id=run_id, mode="single", status="running")

    elif mode == "batch":
        run = BatchRun(strategy_id=strat_row.id, status="running", started_at=datetime.utcnow(), capital_mode=body.capital_mode)
        db.add(run)
        db.flush()

        cfg = BatchRunConfig(
            batch_run_id=run.id,
            symbols=json.dumps(body.symbols),
            timeframe=body.timeframe,
            start_date=date.fromisoformat(body.start_date),
            end_date=date.fromisoformat(body.end_date),
            initial_capital=body.initial_capital,
            leverage=body.leverage,
            risk_per_trade_pct=body.risk_per_trade_pct,
            params=json.dumps(body.params),
        )
        db.add(cfg)
        db.commit()

        run_id = run.id
        exc_mod.create_progress_queue(run_id)
        progress_cb = exc_mod.make_progress_callback(run_id, loop)

        def _run_batch_backtest():
            from app.backtest.run_batch_analysis import run_single_backtest
            from concurrent.futures import ProcessPoolExecutor, as_completed
            import multiprocessing

            completed = 0
            total = len(body.symbols)
            results = []
            failed = []

            max_workers = min(multiprocessing.cpu_count(), total)
            per_symbol_cap = float(body.initial_capital) if body.capital_mode == "full" else float(body.initial_capital) / total

            # Download data first
            from app.backtest.download_data import download_data, calculate_candle_limit
            limit = 8832
            try:
                 limit = calculate_candle_limit(body.timeframe, days=0, months=0, years=0) # simplified
            except: pass

            missing = []
            for symbol in body.symbols:
                 safe = symbol.replace("/", "")
                 path = _csv_path(symbol, body.timeframe)
                 if not os.path.exists(path): missing.append((symbol, safe, path))

            if missing:
                 import ccxt
                 shared_exchange = ccxt.binanceusdm()
                 shared_exchange.load_markets()
                 for symbol, safe_symbol, data_file in missing:
                      try: download_data(symbol, body.timeframe, limit, DATA_DIR, exchange=shared_exchange)
                      except Exception as e: failed.append(symbol)

            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                config_for_single = {
                    "backtest": {"initial_balance": per_symbol_cap},
                    "risk": {"leverage": body.leverage, "risk_per_trade_pct": float(body.risk_per_trade_pct)},
                    "strategy_params": body.params
                }
                futures = {
                    executor.submit(
                        run_single_backtest,
                        symbol=sym,
                        config=config_for_single,
                        timeframe=body.timeframe,
                        balance=per_symbol_cap,
                        strategy_name=body.strategy,
                        data_dir=DATA_DIR,
                        report_dir=os.path.join(DATA_DIR, "reports")
                    ): sym for sym in body.symbols if sym not in failed
                }
                for future in as_completed(futures):
                    sym = futures[future]
                    completed += 1
                    try:
                        res = future.result()
                        results.append(res)
                        status = "completed" if "error" not in res else "failed"
                        exc_mod.publish_event(run_id, loop, "progress", {"pct": int(completed/total*100), "completed": completed, "total": total, "symbol": sym, "symbol_status": status})
                        if "error" in res:
                             failed.append(sym)
                    except Exception as e:
                        failed.append(sym)
                        exc_mod.publish_event(run_id, loop, "symbol_error", {"symbol": sym, "message": str(e)})

            from app.api.routes.backtest_utils import _persist_batch_results
            try:
                _persist_batch_results(run_id, results)
                final_status = "partial" if failed else "completed"
                exc_mod.publish_event(run_id, loop, "complete", {"batch_run_id": run_id, "status": final_status, "failed": failed})
            except Exception as e:
                exc_mod.publish_event(run_id, loop, "error", {"message": str(e)})
            finally:
                exc_mod.cleanup_job(run_id)

        exc_mod.submit_backtest(run_id, _run_batch_backtest)
        return BacktestStartResponse(batch_run_id=run_id, mode="batch", status="running")

    elif mode == "portfolio":
        run = PortfolioRun(strategy_id=strat_row.id, status="running", started_at=datetime.utcnow())
        db.add(run)
        db.flush()

        cfg = PortfolioRunConfig(
            portfolio_run_id=run.id,
            symbols=json.dumps(body.symbols),
            timeframe=body.timeframe,
            start_date=date.fromisoformat(body.start_date),
            end_date=date.fromisoformat(body.end_date),
            initial_capital=body.initial_capital,
            leverage=body.leverage,
            risk_per_trade_pct=body.risk_per_trade_pct,
            params=json.dumps(body.params),
        )
        db.add(cfg)
        db.commit()

        run_id = run.id
        exc_mod.create_progress_queue(run_id)
        progress_cb = exc_mod.make_progress_callback(run_id, loop)

        def _run_portfolio_backtest():
            try:
                from app.backtest.run_portfolio_backtest import _enrich_round_trips
                from app.backtest.download_data import download_data, calculate_candle_limit
                import ccxt
                from app.backtest.portfolio_engine import PortfolioEngine
                from app.backtest.portfolio_event_source import PortfolioEventSource
                from app.backtest.mock_exchange import MockExchange
                import pandas as pd
                from app.backtest.engine import BacktestEngine

                limit = 8832
                missing = []
                for symbol in body.symbols:
                     safe = symbol.replace("/", "")
                     path = _csv_path(symbol, body.timeframe)
                     if not os.path.exists(path): missing.append((symbol, safe, path))

                if missing:
                     shared_exchange = ccxt.binanceusdm()
                     shared_exchange.load_markets()
                     for symbol, safe_symbol, data_file in missing:
                          try: download_data(symbol, body.timeframe, limit, DATA_DIR, exchange=shared_exchange)
                          except Exception as e: raise ValueError(f"Download failed for {symbol}")

                dfs = {}
                strategy_instance = strategy_class({"strategy_params": body.params})
                for symbol in body.symbols:
                     safe_symbol = symbol.replace('/', '')
                     data_file = os.path.join(DATA_DIR, f"{safe_symbol}_{body.timeframe}.csv")
                     df = pd.read_csv(data_file)
                     df["timestamp"] = pd.to_datetime(df["timestamp"])
                     prepared_df = BacktestEngine._prepare_dataframe(df, strategy_instance, symbol)
                     dfs[symbol] = prepared_df

                event_source = PortfolioEventSource(dfs, start_idx=220)
                exchange = MockExchange(
                    initial_balance=float(body.initial_capital),
                    leverage=body.leverage,
                    taker_fee=float(body.fee_tier),
                    maker_fee=float(body.fee_tier)*0.4,
                )

                config = {
                    "backtest": {"initial_balance": float(body.initial_capital)},
                    "risk": {"leverage": body.leverage, "risk_per_trade_pct": float(body.risk_per_trade_pct)},
                    "strategy_params": body.params
                }

                engine = PortfolioEngine(
                     event_source=event_source,
                     strategy_class=strategy_class,
                     exchange=exchange,
                     config=config,
                     symbols=body.symbols
                )

                def p_cb(data):
                     pct = data.get("pct", 0)
                     exc_mod.publish_event(run_id, loop, "progress", {"pct": pct})

                results = engine.run(on_progress=p_cb)

                from app.api.routes.backtest_utils import _persist_portfolio_results
                _persist_portfolio_results(run_id, results)
                exc_mod.publish_event(run_id, loop, "complete", {"portfolio_run_id": run_id, "status": "completed"})

            except Exception as e:
                logger.error("portfolio worker error", error=str(e))
                exc_mod.publish_event(run_id, loop, "error", {"message": str(e)})
            finally:
                exc_mod.cleanup_job(run_id)

        exc_mod.submit_backtest(run_id, _run_portfolio_backtest)
        return BacktestStartResponse(portfolio_run_id=run_id, mode="portfolio", status="running")
@router.get("/{run_id}/progress")
async def stream_progress(run_id: int):
    """SSE endpoint. Client connects and receives progress events."""
    q = exc_mod.get_progress_queue(run_id)
    if q is None:
        # Run already finished or doesn't exist — send synthetic complete
        async def _done():
            yield f"event: complete\ndata: {json.dumps({'run_id': run_id, 'status': 'completed'})}\n\n"

        return StreamingResponse(
            _done(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def _generate():
        try:
            while True:
                event = await asyncio.wait_for(q.get(), timeout=300.0)
                evt_name = event.pop("event", "progress")
                yield f"event: {evt_name}\ndata: {json.dumps(event)}\n\n"
                if evt_name in ("complete", "error"):
                    break
        except asyncio.TimeoutError:
            yield f"event: error\ndata: {json.dumps({'message': 'timeout'})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# DELETE /api/backtest/{run_id}  — Cancel
# ---------------------------------------------------------------------------





# ---------------------------------------------------------------------------
# GET /api/backtest/{run_id}  — Run detail
# ---------------------------------------------------------------------------


@router.get("/{run_id}", response_model=RunDetail)
def get_run_detail(run_id: int, db: Session = Depends(get_db)):
    run = db.query(Run).filter_by(id=run_id).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    strat = db.query(Strategy).filter_by(id=run.strategy_id).first()
    cfg = db.query(RunConfig).filter_by(run_id=run_id).first()
    result = db.query(RunResult).filter_by(run_id=run_id).first()
    trades = db.query(Trade).filter_by(run_id=run_id).order_by(Trade.entry_time).all()

    config_dict: dict[str, Any] = {}
    if cfg:
        config_dict = {
            "symbol": cfg.symbol,
            "timeframe": cfg.timeframe,
            "start_date": cfg.start_date.isoformat() if cfg.start_date else None,
            "end_date": cfg.end_date.isoformat() if cfg.end_date else None,
            "initial_capital": str(cfg.initial_capital),
            "leverage": cfg.leverage,
            "risk_per_trade_pct": str(cfg.risk_per_trade_pct),
            "params": cfg.params or {},
        }

    results_dict: dict[str, Any] | None = None
    if result:
        results_dict = {
            "net_profit": str(result.net_profit) if result.net_profit is not None else None,
            "net_profit_pct": result.net_profit_pct,
            "gross_profit": str(result.gross_profit) if result.gross_profit is not None else None,
            "gross_loss": str(result.gross_loss) if result.gross_loss is not None else None,
            "win_rate": result.win_rate,
            "profit_factor": result.profit_factor,
            "expectancy": str(result.expectancy) if result.expectancy is not None else None,
            "max_drawdown_pct": result.max_drawdown_pct,
            "max_drawdown_value": str(result.max_drawdown_value) if result.max_drawdown_value is not None else None,
            "volatility": result.volatility,
            "sharpe_ratio": result.sharpe_ratio,
            "sortino_ratio": result.sortino_ratio,
            "calmar_ratio": result.calmar_ratio,
            "total_trades": result.total_trades,
            "winning_trades": result.winning_trades,
            "losing_trades": result.losing_trades,
            "avg_win": str(result.avg_win) if result.avg_win is not None else None,
            "avg_loss": str(result.avg_loss) if result.avg_loss is not None else None,
            "largest_win": str(result.largest_win) if result.largest_win is not None else None,
            "largest_loss": str(result.largest_loss) if result.largest_loss is not None else None,
            "max_consecutive_wins": result.max_consecutive_wins,
            "max_consecutive_losses": result.max_consecutive_losses,
            "avg_hold_time_hours": result.avg_hold_time_hours,
            "exit_reasons": result.exit_reasons or {},
        }

    trades_list = [
        {
            "id": t.id,
            "symbol": t.symbol,
            "side": t.side,
            "entry_time": t.entry_time.isoformat() if t.entry_time else None,
            "exit_time": t.exit_time.isoformat() if t.exit_time else None,
            "hold_time_hours": t.hold_time_hours,
            "entry_price": str(t.entry_price),
            "exit_price": str(t.exit_price) if t.exit_price is not None else None,
            "stop_loss_price": str(t.stop_loss_price) if t.stop_loss_price is not None else None,
            "tp1_price": str(t.tp1_price) if t.tp1_price is not None else None,
            "tp2_price": str(t.tp2_price) if t.tp2_price is not None else None,
            "tp3_price": str(t.tp3_price) if t.tp3_price is not None else None,
            "quantity": str(t.quantity),
            "size_usd": str(t.size_usd),
            "pnl": str(t.pnl) if t.pnl is not None else None,
            "pnl_pct": t.pnl_pct,
            "exit_reason": t.exit_reason,
        }
        for t in trades
    ]

    return RunDetail(
        id=run.id,
        strategy_name=strat.name if strat else "",
        symbol=cfg.symbol if cfg else "",
        timeframe=cfg.timeframe if cfg else "",
        status=run.status,
        created_at=run.created_at.isoformat() if run.created_at else "",
        config=config_dict,
        results=results_dict,
        trades=trades_list,
    )


# ---------------------------------------------------------------------------
# GET /api/backtest/{run_id}/timeseries  — Lazy-load charts
# ---------------------------------------------------------------------------


@router.get("/{run_id}/timeseries", response_model=TimeseriesResponse)
def get_timeseries(run_id: int, db: Session = Depends(get_db)):
    ts = db.query(RunTimeseries).filter_by(run_id=run_id).first()
    if ts is None:
        raise HTTPException(status_code=404, detail="Timeseries not found for this run")

    equity_curve = json.loads(zlib.decompress(ts.equity_curve)) if ts.equity_curve else []
    drawdown_curve = json.loads(zlib.decompress(ts.drawdown_curve)) if ts.drawdown_curve else []

    return TimeseriesResponse(
        run_id=run_id,
        equity_curve=equity_curve,
        drawdown_curve=drawdown_curve,
        monthly_returns=ts.monthly_returns or {},
    )


# ---------------------------------------------------------------------------
# Internal helpers (called from worker thread)
# ---------------------------------------------------------------------------


def _persist_results(run_id: int, results: dict[str, Any]) -> None:
    """Write engine results to DB. Runs in a thread — uses its own session."""
    from app.repository.backtest.database import SessionLocal as _SessionLocal

    db = _SessionLocal()
    try:
        run = db.query(Run).filter_by(id=run_id).first()
        if run is None:
            return

        run.status = "completed"
        run.completed_at = datetime.utcnow()

        metrics = results.get("metrics", {})
        drawdown = results.get("drawdown", {})
        risk = results.get("risk_metrics", {})

        result_row = RunResult(
            run_id=run_id,
            net_profit=str(results.get("net_profit", 0)),
            net_profit_pct=results.get("net_profit_pct", 0.0),
            gross_profit=str(metrics.get("gross_profit", 0)),
            gross_loss=str(metrics.get("gross_loss", 0)),
            win_rate=metrics.get("win_rate"),
            profit_factor=metrics.get("profit_factor"),
            expectancy=str(metrics.get("expectancy", 0)),
            max_drawdown_pct=drawdown.get("max_drawdown_pct"),
            max_drawdown_value=str(drawdown.get("max_drawdown_value", 0)),
            max_drawdown_duration_days=drawdown.get("max_dd_duration"),
            volatility=risk.get("volatility"),
            sharpe_ratio=risk.get("sharpe_ratio"),
            sortino_ratio=risk.get("sortino_ratio"),
            calmar_ratio=risk.get("calmar_ratio"),
            total_trades=metrics.get("total_trades"),
            winning_trades=metrics.get("win_count"),
            losing_trades=metrics.get("loss_count"),
            avg_win=str(metrics.get("avg_win", 0)),
            avg_loss=str(metrics.get("avg_loss", 0)),
            largest_win=str(metrics.get("largest_win", 0)),
            largest_loss=str(metrics.get("largest_loss", 0)),
            max_consecutive_wins=metrics.get("max_consec_wins"),
            max_consecutive_losses=metrics.get("max_consec_losses"),
            avg_hold_time_hours=metrics.get("avg_hold_hours"),
            exit_reasons=metrics.get("exit_reason_counts", {}),
        )
        db.add(result_row)

        # Timeseries (zlib-compressed JSON)
        equity_curve = results.get("equity_curve", [])
        drawdown_curve = results.get("drawdown_curve", [])
        monthly_returns = results.get("monthly_returns", {})

        ts_row = RunTimeseries(
            run_id=run_id,
            equity_curve=zlib.compress(json.dumps(equity_curve).encode()),
            drawdown_curve=zlib.compress(json.dumps(drawdown_curve).encode()),
            monthly_returns=monthly_returns,
        )
        db.add(ts_row)

        # Individual trades
        for rt in results.get("round_trips", []):
            entry_t = rt.get("entry_time")
            exit_t = rt.get("exit_time")

            def _parse_dt(val):
                if val is None:
                    return None
                if isinstance(val, datetime):
                    return val
                try:
                    import pandas as pd
                    return pd.to_datetime(val).to_pydatetime()
                except Exception:
                    return None

            trade_row = Trade(
                run_id=run_id,
                symbol=rt.get("symbol", ""),
                side="LONG",
                entry_time=_parse_dt(entry_t),
                exit_time=_parse_dt(exit_t),
                hold_time_hours=rt.get("hold_duration_hours"),
                entry_price=str(rt.get("entry_price", 0)),
                exit_price=str(rt.get("avg_exit_price", rt.get("exit_price", 0))),
                quantity=str(rt.get("amount", 0)),
                size_usd=str(rt.get("notional", rt.get("margin", 0))),
                pnl=str(rt.get("pnl", 0)),
                pnl_pct=rt.get("pnl_pct"),
                exit_reason=rt.get("exit_reason"),
            )
            db.add(trade_row)

        db.commit()
        logger.info("backtest_persisted", run_id=run_id)
    except Exception as err:
        db.rollback()
        logger.error("persist_error", run_id=run_id, error=str(err))
        raise
    finally:
        db.close()


def _mark_failed(run_id: int, error_msg: str) -> None:
    """Mark a run as failed in its own session."""
    from app.repository.backtest.database import SessionLocal as _SessionLocal

    db = _SessionLocal()
    try:
        run = db.query(Run).filter_by(id=run_id).first()
        if run:
            run.status = "failed"
            run.completed_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


@router.delete("/{run_id}")
def cancel_backtest(run_id: int, mode: str = "single", db: Session = Depends(get_db)):
    cancelled = exc_mod.cancel_job(run_id)
    if mode == "single":
        run = db.query(Run).filter_by(id=run_id).first()
        if run:
            run.status = "cancelled"
            db.commit()
    elif mode == "batch":
        run = db.query(BatchRun).filter_by(id=run_id).first()
        if run:
            run.status = "cancelled"
            db.commit()
    elif mode == "portfolio":
        run = db.query(PortfolioRun).filter_by(id=run_id).first()
        if run:
            run.status = "cancelled"
            db.commit()
    return {"cancelled": True, "was_pending": cancelled}

@router.get("/batch/{run_id}", response_model=BatchRunDetail)
def get_batch_run_detail(run_id: int, db: Session = Depends(get_db)):
    run = db.query(BatchRun).filter_by(id=run_id).first()
    if not run: raise HTTPException(status_code=404)
    strat = db.query(Strategy).filter_by(id=run.strategy_id).first()
    cfg = db.query(BatchRunConfig).filter_by(batch_run_id=run_id).first()
    res = db.query(BatchRunResult).filter_by(batch_run_id=run_id).first()

    symbols_list = json.loads(cfg.symbols) if cfg else []
    per_sym_stats = json.loads(res.per_symbol_stats) if res and res.per_symbol_stats else []

    sym_res = []
    for s in per_sym_stats:
         sym_res.append(BatchSymbolResult(
              symbol=s.get("symbol"),
              status=s.get("status"),
              error=s.get("error"),
              net_profit=s.get("net_profit"),
              net_profit_pct=s.get("net_profit_pct"),
              win_rate=s.get("win_rate"),
              profit_factor=s.get("profit_factor"),
              max_drawdown_pct=s.get("max_drawdown_pct"),
              sharpe_ratio=s.get("sharpe_ratio"),
              total_trades=s.get("total_trades"),
              trades=[]
         ))

    agg = json.loads(res.aggregate_stats) if res and res.aggregate_stats else {}

    return BatchRunDetail(
        id=run.id,
        strategy_name=strat.name if strat else "",
        timeframe=cfg.timeframe if cfg else "",
        status=run.status,
        created_at=run.created_at.isoformat() if run.created_at else "",
        config={"symbols": symbols_list, "initial_capital": cfg.initial_capital if cfg else "", "leverage": cfg.leverage if cfg else 1, "params": json.loads(cfg.params) if cfg else {}},
        capital_mode=run.capital_mode,
        symbol_count=len(symbols_list),
        failed_symbols=json.loads(res.failed_symbols) if res and res.failed_symbols else [],
        aggregate=agg,
        symbols=sym_res
    )

@router.get("/portfolio/{run_id}", response_model=PortfolioRunDetail)
def get_portfolio_run_detail(run_id: int, db: Session = Depends(get_db)):
    run = db.query(PortfolioRun).filter_by(id=run_id).first()
    if not run: raise HTTPException(status_code=404)
    strat = db.query(Strategy).filter_by(id=run.strategy_id).first()
    cfg = db.query(PortfolioRunConfig).filter_by(portfolio_run_id=run_id).first()
    res = db.query(PortfolioRunResult).filter_by(portfolio_run_id=run_id).first()
    trades = db.query(PortfolioTrade).filter_by(portfolio_run_id=run_id).all()

    syms = json.loads(cfg.symbols) if cfg else []

    results_dict = None
    if res:
        results_dict = {
             "net_profit": str(res.net_profit),
             "net_profit_pct": res.net_profit_pct,
             "win_rate": res.win_rate,
             "profit_factor": res.profit_factor,
             "max_drawdown_pct": res.max_drawdown_pct,
             "sharpe_ratio": res.sharpe_ratio,
             "total_trades": res.total_trades,
             "exit_reasons": json.loads(res.exit_reasons) if res.exit_reasons else {}
        }

    trades_list = [{
         "symbol": t.symbol, "side": t.side,
         "entry_time": t.entry_time.isoformat() if t.entry_time else None,
         "exit_time": t.exit_time.isoformat() if t.exit_time else None,
         "entry_price": str(t.entry_price), "exit_price": str(t.exit_price),
         "quantity": str(t.quantity), "pnl": str(t.pnl), "pnl_pct": t.pnl_pct, "exit_reason": t.exit_reason
    } for t in trades]

    return PortfolioRunDetail(
        id=run.id,
        strategy_name=strat.name if strat else "",
        timeframe=cfg.timeframe if cfg else "",
        status=run.status,
        created_at=run.created_at.isoformat() if run.created_at else "",
        config={"symbols": syms, "initial_capital": cfg.initial_capital if cfg else "", "leverage": cfg.leverage if cfg else 1, "params": json.loads(cfg.params) if cfg else {}},
        symbols=syms,
        results=results_dict or {},
        trades=trades_list
    )

@router.get("/batch/{run_id}/timeseries", response_model=BatchTimeseriesResponse)
def get_batch_timeseries(run_id: int, db: Session = Depends(get_db)):
    res = db.query(BatchRunResult).filter_by(batch_run_id=run_id).first()
    if not res: raise HTTPException(status_code=404)

    equity_curve = json.loads(zlib.decompress(res.equity_curve)) if res.equity_curve else []
    monthly_returns = json.loads(res.monthly_returns) if res.monthly_returns else {}

    return BatchTimeseriesResponse(
        batch_run_id=run_id,
        portfolio_equity_curve=equity_curve,
        per_symbol_equity={},
        monthly_returns=monthly_returns
    )

@router.get("/portfolio/{run_id}/timeseries", response_model=PortfolioTimeseriesResponse)
def get_portfolio_timeseries(run_id: int, db: Session = Depends(get_db)):
    res = db.query(PortfolioRunResult).filter_by(portfolio_run_id=run_id).first()
    if not res: raise HTTPException(status_code=404)

    equity_curve = json.loads(zlib.decompress(res.equity_curve)) if res.equity_curve else []
    drawdown_curve = json.loads(zlib.decompress(res.drawdown_curve)) if res.drawdown_curve else []
    monthly_returns = json.loads(res.monthly_returns) if res.monthly_returns else {}

    return PortfolioTimeseriesResponse(
        portfolio_run_id=run_id,
        equity_curve=equity_curve,
        drawdown_curve=drawdown_curve,
        monthly_returns=monthly_returns
    )
