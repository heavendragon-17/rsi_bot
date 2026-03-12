import re

with open('app/api/routes/backtest.py', 'r') as f:
    content = f.read()

imports_to_add = """
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
"""
content = content.replace("from app.repository.backtest.models import (", imports_to_add + "from app.repository.backtest.models import (")

run_endpoint_new = """
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
"""

content = re.sub(r'@router\.post\("/run", status_code=201, response_model=BacktestStartResponse\)\nasync def start_backtest\(.*?(?=@router\.get\("/\{run_id\}/progress"\))', run_endpoint_new, content, flags=re.DOTALL)

with open('app/api/routes/backtest.py', 'w') as f:
    f.write(content)

with open('app/api/routes/backtest.py', 'a') as f:
    f.write("""

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

""")

with open('app/api/routes/backtest.py', 'r') as f:
     c = f.read()

c = re.sub(r'@router\.delete\("/\{run_id\}"\)\ndef cancel_backtest\(run_id: int, db: Session = Depends\(get_db\)\):.*?return \{"cancelled": True, "was_pending": cancelled\}', '', c, flags=re.DOTALL, count=1)

with open('app/api/routes/backtest.py', 'w') as f:
     f.write(c)
