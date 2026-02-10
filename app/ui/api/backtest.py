import copy
import json
import os
import pandas as pd
from decimal import Decimal
from datetime import datetime

from app.db.repository import BacktestRepository
from app.backtest.engine import BacktestEngine
from app.backtest.reporting import BacktestReporter
from app.strategies.loader import load_strategy
from app.backtest.grid_search import run_grid_search
from app.backtest.walk_forward import run_walk_forward
from app.backtest.sensitivity import run_sensitivity
from app.backtest.compare import compare_runs

class BacktestAPIMixin:
    """Methods related to running backtests and viewing results."""

    def run_backtest(self, config: dict) -> dict:
        """
        Execute backtest using the real BacktestEngine and return results.
        Follows the pattern in app/backtest/run_batch_analysis.py.
        """
        try:
            # 1. Prepare Configuration
            strategy_name = config.get("strategy_name")
            symbol = config.get("symbol")
            timeframe = config.get("timeframe")
            # start_date/end_date handling (if engine supports filtering, otherwise it uses full CSV)

            # Resolve data file path
            data_file = self._resolve_data_path(config.get("data_file"))
            if not os.path.exists(data_file):
                return {"error": f"Data file not found: {data_file}"}

            # Prepare config for engine (strategy loader expects 'strategy' key)
            engine_config = copy.deepcopy(config)
            engine_config["strategy"] = strategy_name
            engine_config["symbols"] = [symbol]
            if "backtest" not in engine_config:
                 engine_config["backtest"] = {}
            if "initial_balance" not in engine_config["backtest"]:
                 engine_config["backtest"]["initial_balance"] = 10000

            initial_balance = engine_config["backtest"]["initial_balance"]

            # 2. Run Engine
            strategy_class = load_strategy(engine_config)
            engine = BacktestEngine(
                data_path=data_file,
                strategy_class=strategy_class,
                config=engine_config
            )

            # Set initial balance on exchange
            engine.exchange.initial_balance = Decimal(str(initial_balance))
            engine.exchange.balance = Decimal(str(initial_balance))

            engine.run()

            # 3. Generate Report / Metrics
            reporter = BacktestReporter(
                engine.exchange,
                engine_config,
                initial_balance=float(initial_balance),
                symbol=symbol,
                timeframe=timeframe,
                strategy_name=strategy_name
            )

            trades_df = pd.DataFrame(engine.exchange.trade_history)
            round_trips = reporter._build_round_trips(trades_df)
            metrics = reporter._calculate_metrics(round_trips)
            drawdown = reporter._calculate_drawdown(round_trips)
            risk_metrics = reporter._calculate_risk_metrics(round_trips, drawdown)

            # 4. Save to Database
            repo = BacktestRepository()

            run_data = {
                "strategy_name": strategy_name,
                "symbol": symbol,
                "timeframe": timeframe,
                "start_date": config.get("start_date", ""),
                "end_date": config.get("end_date", ""),
                "created_at": datetime.now().isoformat(),
                "config_json": json.dumps(config)
            }
            run_id = repo.save_run(run_data)

            # Combine metrics for storage
            combined_metrics = {
                **metrics,
                **risk_metrics,
                "total_profit": float(round_trips['pnl'].sum()) if not round_trips.empty else 0.0,
                "max_drawdown": drawdown.get("max_drawdown_pct", 0.0)
            }
            repo.save_run_results(run_id, combined_metrics)

            # Save trades
            if not trades_df.empty:
                trades_list = []
                for _, t in trades_df.iterrows():
                    trades_list.append({
                        "entry_time": t.get("time"), # timestamp is usually 'time' in engine
                        "exit_time": t.get("time"),  # Simplified; engine tracks this differently if needed
                        "entry_price": float(t.get("price", 0)),
                        "exit_price": float(t.get("price", 0)), # Placeholder if single trade log
                        "quantity": float(t.get("amount", 0)),
                        "side": t.get("side"),
                        "pnl": float(t.get("pnl", 0)),
                        "exit_reason": t.get("info", {}).get("exit_reason", "")
                    })
                # Note: Repo expects specific trade format. The engine's trade_history is raw orders.
                # Round trips are better for 'trades' list if schema supports it.
                # However, repo.save_trades expects raw trade objects or similar.
                # For now, let's skip complex trade saving or use round_trips if compatible.
                pass

            # Save timeseries
            repo.save_timeseries(
                run_id,
                drawdown.get("equity_curve", []),
                drawdown.get("drawdown_curve", [])
            )

            return {
                "run_id": run_id,
                "metrics": combined_metrics,
                "equity_preview": drawdown.get("equity_curve", [])[:100]
            }

        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"error": str(e)}

    def get_run_history(self, filters: dict = None) -> list[dict]:
        """Get history of runs."""
        repo = BacktestRepository()
        runs = repo.get_all_runs()

        summary = []
        for run in runs:
            results = repo.get_run_results(run["id"])
            if results:
                # Calculate net profit pct if available, else 0
                profit = results.get("total_profit", 0)
                # We need initial balance to calc pct, but it might not be stored directly in results
                # Assuming standard 10000 or stored in config
                # simplified for now
                net_profit_pct = 0.0
                if "metrics_json" in results and results["metrics_json"]:
                     # Try to parse from saved metrics json
                     m = results["metrics_json"]
                     if isinstance(m, dict):
                         net_profit_pct = m.get("profit_pct", 0.0)

                summary.append({
                    "run_id": run["id"],
                    "strategy_name": run["strategy_name"],
                    "symbol": run["symbol"],
                    "timeframe": run["timeframe"],
                    "created_at": run["created_at"],
                    "net_profit_pct": net_profit_pct,
                    "win_rate": float(results["win_rate"]) if results["win_rate"] is not None else 0.0,
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
            data_file=self._resolve_data_path(config["data_file"]),
            param_grid=config["param_grid"],
            base_config=config.get("base_config", {})
        )

    def run_walk_forward(self, config: dict) -> dict:
        """Run walk-forward analysis."""
        return run_walk_forward(
            strategy_name=config["strategy_name"],
            symbol=config["symbol"],
            data_file=self._resolve_data_path(config["data_file"]),
            config_overrides=config.get("config", {}),
            train_days=config.get("train_days", 90),
            test_days=config.get("test_days", 30),
            step_days=config.get("step_days", 30)
        )

    def run_sensitivity(self, config: dict) -> dict:
        """Run sensitivity analysis."""
        return run_sensitivity(
            strategy_name=config["strategy_name"],
            symbol=config["symbol"],
            data_file=self._resolve_data_path(config["data_file"]),
            base_config=config.get("base_config", {}),
            param_name=config["param_name"],
            param_range=config["param_range"],
            metric=config.get("metric", "profit")
        )

    def compare_runs(self, run_id_1: int, run_id_2: int) -> dict:
        """Compare two runs."""
        run1 = self._get_run_data(run_id_1)
        run2 = self._get_run_data(run_id_2)
        return compare_runs(run1, run2)

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

    def _resolve_data_path(self, filename: str) -> str:
        """Convert data file name to absolute path."""
        import os
        if os.path.isabs(filename):
            return filename

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        return os.path.join(project_root, "app", "backtest", "data", filename)

    def _get_run_data(self, run_id: int) -> dict:
        repo = BacktestRepository()
        run = repo.get_run(run_id)
        results = repo.get_run_results(run_id)

        if not run or not results:
            return {}

        data = {
            "id": run["id"],
            "strategy_name": run["strategy_name"],
            "symbol": run["symbol"],
            "timeframe": run["timeframe"],
            **results
        }

        # Map keys for compare.py
        data["profit"] = float(data.get("total_profit", 0))
        # Metrics json might hold more details
        metrics_json = data.get("metrics_json", {})
        if "profit_pct" in metrics_json:
             data["profit_pct"] = metrics_json["profit_pct"]
        elif "net_profit_pct" in metrics_json:
             data["profit_pct"] = metrics_json["net_profit_pct"]

        return data
