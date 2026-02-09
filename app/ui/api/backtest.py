import threading
from pathlib import Path
from datetime import datetime

# Import repositories and engine
from app.db.connection import get_cursor
from app.db.models import Run
from app.db.repositories.runs import RunsRepository
from app.db.repositories.timeseries import save_timeseries
from app.db.repositories.trades import create_trade
from app.backtest.engine import BacktestEngine
from app.strategies.rsi_wma_retest import RsiWmaRetestStrategy
from app.strategies.rsi_no_retest import RsiNoRetestStrategy

STRATEGY_MAP = {
    "rsi_wma_retest": RsiWmaRetestStrategy,
    "rsi_no_retest": RsiNoRetestStrategy,
}

class BacktestAPI:
    def __init__(self):
        self.runs_repo = RunsRepository()

    def get_data_files(self):
        """Scan CSV files in data directory."""
        data_dir = Path("app/backtest/data")
        files = []
        try:
            if not data_dir.exists():
                return {"success": True, "data": []}
                
            for f in data_dir.glob("*.csv"):
                stat = f.stat()
                parts = f.stem.split("_")
                
                # Infer symbol/timeframe
                symbol_raw = parts[0]
                if symbol_raw.endswith("USDT"):
                    symbol = f"{symbol_raw[:-4]}/USDT"
                else:
                    symbol = symbol_raw
                
                timeframe = parts[1] if len(parts) > 1 else "unknown"

                files.append({
                    "name": f.name,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "path": str(f.absolute()),
                    "size_mb": round(stat.st_size / 1024 / 1024, 2),
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
            
            # Sort by modified date descending
            files.sort(key=lambda x: x["modified"], reverse=True)
            return {"success": True, "data": files}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def run_backtest(self, params):
        """Execute backtest in a separate thread (simulated for API, actually synchronous here for simplicity or threaded)."""
        # For PyWebView, we need to return a Promise result. 
        # If the backtest is long, we might want to return a 'started' status and have the UI poll or use events.
        # For simplicity in Sprint 2, we'll run synchronously and return the result.
        
        try:
            strategy_name = params.get("strategy_name")
            data_file = params.get("data_file")
            initial_balance = params.get("initial_balance", 10000)
            
            if strategy_name not in STRATEGY_MAP:
                 return {"success": False, "error": f"Unknown strategy: {strategy_name}", "error_code": "STRATEGY_NOT_FOUND"}
            
            strategy_class = STRATEGY_MAP[strategy_name]
            
            # Prepare config
            config = {
                "backtest": {"initial_balance": initial_balance},
                "strategy": strategy_name
                # Add other overrides from params if needed
            }
            
            # Initialize Engine
            engine = BacktestEngine(
                data_path=data_file,
                strategy_class=strategy_class,
                config=config
            )
            
            # Run
            engine.run()
            
            # Generate Report Metrics (simplified)
            # In a real app, BacktestReporter does heavy lifting. 
            # Here we extract what we need for the API response.
            metrics = engine.calculate_metrics() if hasattr(engine, 'calculate_metrics') else {}
            # Fallback if engine doesn't return metrics directly in method
            if not metrics and hasattr(engine, 'results'):
                 metrics = engine.results
            
            # Persist to DB
            with get_cursor() as cursor:
                # Create Run
                run_id = self.runs_repo.create_run(
                    cursor, 
                    strategy_id=1, # TODO: Look up strategy ID dynamically
                    status="completed",
                    config={**config, "symbol": engine.symbol, "timeframe": engine.timeframe} # Merge details
                )
                
                # Save Results
                self.runs_repo.save_results(cursor, run_id, metrics)
                
                # Save Trades
                for trade in engine.trades:
                     create_trade(cursor, run_id, trade) # trade needs to be a dict
                
                # Save Timeseries
                # Assumes engine tracks equity_curve property
                if hasattr(engine, 'equity_curve'):
                    save_timeseries(cursor, run_id, engine.equity_curve, getattr(engine, 'drawdown_curve', None))
            
            return {
                "success": True,
                "data": {
                    "run_id": run_id,
                    "metrics": metrics,
                    # preview points could be added here
                }
            }

        except Exception as e:
            return {"success": False, "error": str(e), "error_code": "BACKTEST_ERROR"}
