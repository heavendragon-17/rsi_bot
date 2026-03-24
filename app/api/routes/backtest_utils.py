import json
import zlib
from datetime import datetime

from app.repository.backtest.database import SessionLocal
from app.repository.backtest.models import (
    BatchRun, BatchRunResult,
    PortfolioRun, PortfolioRunResult, PortfolioTrade
)

def _persist_batch_results(batch_run_id: int, results: list[dict]):
    db = SessionLocal()
    try:
        run = db.query(BatchRun).filter_by(id=batch_run_id).first()
        if not run: return
        run.status = "completed"
        run.completed_at = datetime.utcnow()

        aggregate_stats = {}

        per_symbol_stats = []
        failed_symbols = []
        all_trades = []
        total_pnl = 0
        total_trades = 0
        total_initial = 0
        total_final = 0

        import pandas as pd
        for res in results:
            if "error" in res:
                failed_symbols.append(res["symbol"])
                per_symbol_stats.append({"symbol": res["symbol"], "status": "failed", "error": res["error"]})
                continue

            metrics = res.get("metrics", {})
            total_pnl += res.get("profit", 0)
            total_trades += metrics.get("total_trades", 0)
            total_initial += res.get("initial_balance", 0)
            total_final += res.get("final_balance", 0)

            per_symbol_stats.append({
                "symbol": res["symbol"],
                "status": "completed",
                "net_profit": str(res.get("profit", 0)),
                "net_profit_pct": res.get("profit_pct", 0),
                "win_rate": metrics.get("win_rate", 0),
                "profit_factor": metrics.get("profit_factor", 0),
                "max_drawdown_pct": res.get("drawdown", 0),
                "sharpe_ratio": res.get("risk_metrics", {}).get("sharpe_ratio"),
                "total_trades": metrics.get("total_trades", 0)
            })

            if 'round_trips' in res and not res['round_trips'].empty:
                t = res['round_trips'].copy()
                t['symbol'] = res['symbol']
                t['exit_time'] = pd.to_datetime(t['exit_time'])
                all_trades.append(t)

        portfolio_return = ((total_final - total_initial) / total_initial) * 100 if total_initial > 0 else 0
        aggregate_stats = {
            "total_pnl": total_pnl,
            "portfolio_return": portfolio_return,
            "total_trades": total_trades
        }

        equity_values = [{"date": "Start", "balance": total_initial}]
        if all_trades:
            combined = pd.concat(all_trades).sort_values('exit_time')
            current_equity = total_initial
            for i, row in combined.iterrows():
                current_equity += row['pnl']
                equity_values.append({
                    "date": row['exit_time'].strftime('%Y-%m-%d %H:%M'),
                    "balance": current_equity
                })

        result_row = BatchRunResult(
            batch_run_id=batch_run_id,
            aggregate_stats=json.dumps(aggregate_stats),
            per_symbol_stats=json.dumps(per_symbol_stats),
            failed_symbols=json.dumps(failed_symbols),
            equity_curve=zlib.compress(json.dumps(equity_values).encode()),
            monthly_returns="{}"
        )
        db.add(result_row)
        if failed_symbols and len(failed_symbols) == len(results):
             run.status = "failed"
        elif failed_symbols:
             run.status = "partial"
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def _persist_portfolio_results(portfolio_run_id: int, results: dict):
    db = SessionLocal()
    try:
        run = db.query(PortfolioRun).filter_by(id=portfolio_run_id).first()
        if not run: return
        run.status = "completed"
        run.completed_at = datetime.utcnow()

        metrics = results.get("metrics", {})
        drawdown = results.get("drawdown", {})
        risk = results.get("risk_metrics", {})

        result_row = PortfolioRunResult(
            portfolio_run_id=portfolio_run_id,
            net_profit=str(results.get("net_profit", 0)),
            net_profit_pct=results.get("net_profit_pct", 0),
            win_rate=metrics.get("win_rate", 0),
            profit_factor=metrics.get("profit_factor", 0),
            max_drawdown_pct=drawdown.get("max_drawdown_pct", 0),
            sharpe_ratio=risk.get("sharpe_ratio", 0),
            total_trades=metrics.get("total_trades", 0),
            exit_reasons=json.dumps(metrics.get("exit_reason_counts", {})),
            equity_curve=zlib.compress(json.dumps(results.get("equity_curve", [])).encode()),
            drawdown_curve=zlib.compress(json.dumps(results.get("drawdown_curve", [])).encode()),
            monthly_returns=json.dumps(results.get("monthly_returns", {}))
        )
        db.add(result_row)

        for rt in results.get("round_trips", []):
            trade_row = PortfolioTrade(
                portfolio_run_id=portfolio_run_id,
                symbol=rt.get("symbol", ""),
                side="LONG",
                entry_time=rt.get("entry_time"),
                exit_time=rt.get("exit_time"),
                entry_price=str(rt.get("entry_price", 0)),
                exit_price=str(rt.get("avg_exit_price", rt.get("exit_price", 0))),
                quantity=str(rt.get("amount", 0)),
                pnl=str(rt.get("pnl", 0)),
                pnl_pct=rt.get("pnl_pct", 0),
                exit_reason=rt.get("exit_reason", "")
            )
            db.add(trade_row)

        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()
