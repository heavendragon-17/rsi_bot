from app.db.repository import BacktestRepository
# from app.backtest.engine import BacktestEngine
from app.backtest.data import load_csv_data  # Assuming this exists or will be implemented
import pandas as pd
import json
from app.backtest.grid_search import run_grid_search
from app.backtest.walk_forward import run_walk_forward
from app.backtest.sensitivity import run_sensitivity
from app.backtest.comparison import compare_runs

class BacktestAPIMixin:
    """Methods related to running backtests and viewing results."""

    def run_backtest(self, config: dict) -> dict:
        """Execute backtest and return results."""
        # 1. Prepare Configuration
        strategy_name = config.get("strategy_name")
        symbol = config.get("symbol")
        timeframe = config.get("timeframe")
        start_date = config.get("start_date")
        end_date = config.get("end_date")

        # 2. Run Engine (Placeholder logic - needs integration with actual engine)
        # In a real implementation, you'd instantiate BacktestEngine(config) and run()

        # Simulating a result for now
        run_data = {
            "strategy_name": strategy_name,
            "symbol": symbol,
            "timeframe": timeframe,
            "start_date": start_date,
            "end_date": end_date,
            "config_json": json.dumps(config)
        }

        repo = BacktestRepository()
        run_id = repo.save_run(run_data)

        # Simulating results
        results = {
            "total_profit": 100.0,
            "win_rate": 0.5,
            "total_trades": 10,
            "profit_factor": 1.5,
            "max_drawdown": -5.0,
            "sharpe_ratio": 1.2
        }
        repo.save_run_results(run_id, results)

        # Simulating timeseries
        equity = [{"t": 1, "v": 1000}, {"t": 2, "v": 1100}]
        drawdown = [{"t": 1, "v": 0}, {"t": 2, "v": -2}]
        repo.save_timeseries(run_id, equity, drawdown)

        return {
            "run_id": run_id,
            "metrics": results,
            "equity_preview": equity[:100]  # Only return preview
        }

    def get_run_history(self, filters: dict = None) -> list[dict]:
        """Get history of runs."""
        repo = BacktestRepository()
        runs = repo.get_all_runs()

        # Basic filtering could be implemented here
        # Return summary list
        summary = []
        for run in runs:
            results = repo.get_run_results(run["id"])
            if results:
                summary.append({
                    "run_id": run["id"],
                    "strategy_name": run["strategy_name"],
                    "symbol": run["symbol"],
                    "timeframe": run["timeframe"],
                    "created_at": run["created_at"],
                    "net_profit_pct": 0.0, # Placeholder
                    "win_rate": results["win_rate"],
                    "total_trades": results["total_trades"]
                })
        return summary

    def get_run_details(self, run_id: int) -> dict:
        """Get details for a single run."""
        repo = BacktestRepository()
        run = repo.get_run(run_id)
        if not run:
            return {"error": "Run not found"}

        results = repo.get_run_results(run_id)
        return {
            "run": run,
            "results": results
        }

    def get_run_timeseries(self, run_id: int) -> dict:
        """Get full timeseries data."""
        repo = BacktestRepository()
        return repo.get_timeseries(run_id)

    def get_trades(self, run_id: int) -> list[dict]:
        """Get trades for a run."""
        repo = BacktestRepository()
        return repo.get_trades(run_id)

    def run_grid_search(self, config: dict) -> list[dict]:
        """Run grid search analysis."""
        return run_grid_search(
            strategy_name=config["strategy_name"],
            symbol=config["symbol"],
            data_file=config["data_file"],
            param_grid=config["param_grid"],
            base_config=config["base_config"]
        )

    def run_walk_forward(self, config: dict) -> dict:
        """Run walk-forward analysis."""
        return run_walk_forward(
            strategy_name=config["strategy_name"],
            symbol=config["symbol"],
            data_file=config["data_file"],
            config=config["config"],
            train_days=config.get("train_days", 90),
            test_days=config.get("test_days", 30),
            step_days=config.get("step_days", 30)
        )

    def run_sensitivity(self, config: dict) -> dict:
        """Run sensitivity analysis."""
        return run_sensitivity(
            strategy_name=config["strategy_name"],
            symbol=config["symbol"],
            data_file=config["data_file"],
            base_config=config["base_config"],
            param_name=config["param_name"],
            param_range=config["param_range"],
            metric=config.get("metric", "profit")
        )

    def compare_runs(self, run_id_1: int, run_id_2: int) -> dict:
        """Compare two runs."""
        return compare_runs(run_id_1, run_id_2)

    def export_results(self, run_id: int, format: str) -> dict:
        """Export results to file."""
        repo = BacktestRepository()
        run = repo.get_run(run_id)
        if not run:
            return {"success": False, "error": "Run not found"}

        trades = repo.get_trades(run_id)

        import os
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        export_dir = os.path.join(base_dir, "data", "exports")
        if not os.path.exists(export_dir):
            os.makedirs(export_dir)

        filename = f"{run['strategy_name']}_{run['symbol']}_{run_id}.{format}"
        filepath = os.path.join(export_dir, filename)

        try:
            if format == "csv":
                pd.DataFrame(trades).to_csv(filepath, index=False)
            elif format == "json":
                pd.DataFrame(trades).to_json(filepath, orient="records", date_format="iso")
            else:
                 return {"success": False, "error": "Invalid format"}

            return {"success": True, "file_path": filepath}
        except Exception as e:
            return {"success": False, "error": str(e)}
