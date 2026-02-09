import threading
from pathlib import Path
from datetime import datetime
import os

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

# Determine paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(SCRIPT_DIR)))

class BacktestAPI:
    def __init__(self):
        self.runs_repo = RunsRepository()

    def get_data_files(self):
        """Scan CSV files in data directory."""
        data_dir = Path(PROJECT_ROOT) / "app" / "backtest" / "data"
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
        """Execute backtest synchronously for Sprint 5."""
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
                "strategy": strategy_name,
                "symbol": "UNKNOWN", # Will be updated from engine
                "timeframe": "UNKNOWN" # Will be updated from engine
            }
            
            # Initialize Engine
            engine = BacktestEngine(
                data_path=data_file,
                strategy_class=strategy_class,
                config=config
            )
            
            # Run
            engine.run()
            
            # Generate Report Metrics
            metrics = engine.results
            
            # Persist to DB
            with get_cursor() as cursor:
                # Create Run
                # Use engine symbol/timeframe if available
                final_config = {
                    **config, 
                    "symbol": getattr(engine, 'symbol', "UNKNOWN"), 
                    "timeframe": getattr(engine, 'timeframe', "UNKNOWN"),
                    "start_date": getattr(engine, 'start_date', None),
                    "end_date": getattr(engine, 'end_date', None)
                }
                
                run_id = self.runs_repo.create_run(
                    cursor, 
                    strategy_id=1, 
                    status="completed",
                    config=final_config
                )
                
                # Save Results
                self.runs_repo.save_results(cursor, run_id, metrics)
                
                # Save Trades
                for trade in engine.trades:
                     create_trade(cursor, run_id, trade)
                
                # Save Timeseries
                if hasattr(engine, 'equity_curve'):
                    save_timeseries(cursor, run_id, engine.equity_curve, getattr(engine, 'drawdown_curve', None))
            
            return {
                "success": True,
                "data": {
                    "run_id": run_id,
                    "metrics": metrics
                }
            }

        except Exception as e:
            import traceback
            traceback.print_exc() # Print error to terminal for debugging
            return {"success": False, "error": str(e), "error_code": "BACKTEST_ERROR"}

    def run_grid_search(self, params: dict):
        """
        Run grid search optimization.
        
        Args:
            params: {
                "strategy_name": str,
                "data_file": str,
                "initial_balance": float,
                "param_grid": {
                    "rsi_period": [14, 21, 28],
                    "rsi_wma_length": [30, 45, 60]
                }
            }
        """
        try:
            from app.backtest.grid_search import GridSearch
            
            strategy_name = params.get("strategy_name", "rsi_wma_retest")
            strategy_class = STRATEGY_MAP.get(strategy_name)
            
            if not strategy_class:
                return {"success": False, "error": f"Unknown strategy: {strategy_name}", "error_code": "STRATEGY_NOT_FOUND"}
            
            data_file = params.get("data_file")
            if not data_file:
                return {"success": False, "error": "data_file is required", "error_code": "VALIDATION_ERROR"}
            
            # Resolve path
            if not os.path.isabs(data_file):
                data_file = os.path.join(PROJECT_ROOT, data_file)
            
            if not os.path.exists(data_file):
                return {"success": False, "error": f"File not found: {data_file}", "error_code": "FILE_NOT_FOUND"}
            
            param_grid = params.get("param_grid", {})
            if not param_grid:
                return {"success": False, "error": "param_grid is required", "error_code": "VALIDATION_ERROR"}
            
            # Build base config
            config = {
                "strategy": strategy_name,
                "symbol": params.get("symbol", "UNKNOWN"),
                "timeframe": params.get("timeframe", "UNKNOWN"),
                "backtest": {
                    "initial_balance": params.get("initial_balance", 10000)
                }
            }
            
            # Run grid search
            grid = GridSearch(
                data_path=data_file,
                strategy_class=strategy_class,
                base_config=config
            )
            
            result = grid.run(param_grid)
            
            return {
                "success": True,
                "data": result
            }
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e), "error_code": "GRID_SEARCH_ERROR"}

    def compare_runs(self, run_ids: list):
        """
        Compare multiple runs.
        """
        try:
            from app.backtest.comparison import RunComparison
            
            if not run_ids or not isinstance(run_ids, list):
                 return {"success": False, "error": "run_ids must be a list", "error_code": "VALIDATION_ERROR"}

            comparator = RunComparison()
            result = comparator.compare(run_ids)
            
            return {
                "success": True,
                "data": result
            }
        except Exception as e:
             import traceback
             traceback.print_exc()
             return {"success": False, "error": str(e), "error_code": "COMPARISON_ERROR"}

    def run_walk_forward(self, params: dict):
        """
        Run Walk-Forward Analysis.
        """
        try:
            from app.backtest.walk_forward import WalkForwardOptimization
            
            strategy_name = params.get("strategy_name", "rsi_wma_retest")
            strategy_class = STRATEGY_MAP.get(strategy_name)
            
            if not strategy_class:
                return {"success": False, "error": f"Unknown strategy: {strategy_name}", "error_code": "STRATEGY_NOT_FOUND"}

            data_file = params.get("data_file")
            # Resolve path
            if not os.path.isabs(data_file):
                data_file = os.path.join(PROJECT_ROOT, data_file)
                
            config = {
                "strategy": strategy_name,
                "symbol": params.get("symbol", "UNKNOWN"),
                "timeframe": params.get("timeframe", "UNKNOWN"),
                "backtest": {
                    "initial_balance": params.get("initial_balance", 10000)
                }
            }
            
            wf = WalkForwardOptimization(
                data_path=data_file,
                strategy_class=strategy_class,
                base_config=config
            )
            
            result = wf.run(
                periods=params.get("periods", 5),
                train_ratio=params.get("train_ratio", 0.7)
            )
            
            return {"success": True, "data": result}
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e), "error_code": "WF_ERROR"}

    def run_sensitivity(self, params: dict):
        """Run Sensitivity Analysis."""
        try:
            from app.backtest.sensitivity import SensitivityAnalysis
            
            strategy_name = params.get("strategy_name")
            strategy_class = STRATEGY_MAP.get(strategy_name)
            
            if not strategy_class:
                return {"success": False, "error": f"Unknown strategy: {strategy_name}", "error_code": "STRATEGY_NOT_FOUND"}

            data_file = params.get("data_file")
             # Resolve path
            if not os.path.isabs(data_file):
                data_file = os.path.join(PROJECT_ROOT, data_file)

            config = {
                "strategy": strategy_name,
                "symbol": params.get("symbol", "UNKNOWN"),
                "timeframe": params.get("timeframe", "UNKNOWN"),
                "backtest": {"initial_balance": params.get("initial_balance", 10000)}
            }
            
            sa = SensitivityAnalysis(data_file, strategy_class, config)
            result = sa.run(
                param_name=params.get("param_name"),
                center_value=params.get("center_value"),
                step=params.get("step"),
                steps_count=params.get("steps_count", 5)
            )
            
            return {"success": True, "data": result}
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    def export_run(self, run_id: int, format: str = "csv"):
        """Export run trades to CSV/JSON."""
        try:
            with get_cursor() as cursor:
                # Get trades (assuming we stored them in run_results or need to fetch child runs?)
                # For this MVP, we'll fetch trades from the run_results trades_json if available, or re-run?
                # Actually, trades are stored in a separate table 'trades' linked to run_id in the full schema,
                # but in our defined schema in models.py (which I should check), do we have a trades table?
                # Checking database models... existing code in engine.py uses 'trades' table.
                
                rows = cursor.execute("SELECT * FROM trades WHERE run_id = ?", (run_id,)).fetchall()
                if not rows:
                    return {"success": False, "error": "No trades found"}
                
                # Convert to list of dicts
                columns = [desc[0] for desc in cursor.description]
                trades = [dict(zip(columns, row)) for row in rows]
                
                if format == "json":
                    return {"success": True, "data": trades}
                
                # CSV formatting
                import pandas as pd
                df = pd.DataFrame(trades)
                csv_string = df.to_csv(index=False)
                return {"success": True, "data": csv_string}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
