"""
Grid Search Module
==================
Parameter sweep across multiple combinations for optimization.
"""

from itertools import product
from typing import Dict, List, Any, Optional
from datetime import datetime
from decimal import Decimal
import json

from app.backtest.engine import BacktestEngine
from app.db.connection import get_cursor
from app.db.repositories.runs import RunsRepository


class GridSearch:
    """
    Grid search optimizer for backtesting strategies.
    
    Runs backtests across all parameter combinations and stores
    results for heatmap visualization.
    """
    
    def __init__(
        self,
        data_path: str,
        strategy_class,
        base_config: Dict[str, Any]
    ):
        self.data_path = data_path
        self.strategy_class = strategy_class
        self.base_config = base_config
        self.runs_repo = RunsRepository()
    
    def run(
        self,
        param_grid: Dict[str, List[Any]],
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Run grid search across parameter combinations.
        
        Args:
            param_grid: Parameter ranges to test, e.g.:
                {
                    "rsi_period": [14, 21, 28],
                    "rsi_wma_length": [30, 45, 60]
                }
            progress_callback: Optional callback(current, total) for progress updates
        
        Returns:
            {
                "parent_run_id": int,
                "total_combinations": int,
                "results": [...],
                "best_params": {...},
                "heatmap_data": {...}
            }
        """
        combinations = self._generate_combinations(param_grid)
        total = len(combinations)
        
        if total == 0:
            return {"error": "No parameter combinations generated"}
        
        # Create parent run in database
        parent_run_id = self._create_parent_run(param_grid, total)
        
        results = []
        best_result = None
        best_metric = float('-inf')
        
        for i, params in enumerate(combinations):
            # Merge parameters
            run_config = self._merge_config(params)
            
            # Execute single backtest
            try:
                engine = BacktestEngine(
                    data_path=self.data_path,
                    strategy_class=self.strategy_class,
                    config=run_config
                )
                engine.run()
                metrics = engine.results
            except Exception as e:
                metrics = {"error": str(e), "net_profit_pct": 0}
            
            # Save child run
            child_run_id = self._save_child_run(
                parent_id=parent_run_id,
                params=params,
                metrics=metrics,
                config=run_config
            )
            
            result = {
                "run_id": child_run_id,
                "params": params,
                "metrics": metrics
            }
            results.append(result)
            
            # Track best
            metric_value = metrics.get("net_profit_pct", 0)
            if metric_value > best_metric:
                best_metric = metric_value
                best_result = result
            
            # Progress callback
            if progress_callback:
                progress_callback(i + 1, total)
        
        # Update parent with summary
        self._update_parent_summary(parent_run_id, results, best_result)
        
        # Generate heatmap data
        heatmap_data = self._generate_heatmap_data(param_grid, results)
        
        return {
            "parent_run_id": parent_run_id,
            "total_combinations": total,
            "completed": len(results),
            "results": results,
            "best_params": best_result["params"] if best_result else None,
            "best_metrics": best_result["metrics"] if best_result else None,
            "heatmap_data": heatmap_data
        }
    
    def _generate_combinations(self, grid: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
        """Generate all parameter combinations from grid."""
        if not grid:
            return []
        
        keys = list(grid.keys())
        values = [grid[k] for k in keys]
        
        return [dict(zip(keys, combo)) for combo in product(*values)]
    
    def _merge_config(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Merge override params into base config."""
        merged = {**self.base_config}
        
        # Handle nested strategy_params
        if "strategy_params" in merged:
            merged["strategy_params"] = {**merged["strategy_params"], **params}
        else:
            merged["strategy_params"] = params
        
        return merged
    
    def _create_parent_run(self, param_grid: Dict, total: int) -> int:
        """Create parent run entry for grid search."""
        with get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO runs (strategy_id, status, created_at)
                VALUES (
                    (SELECT id FROM strategies WHERE name = ? LIMIT 1),
                    'running',
                    CURRENT_TIMESTAMP
                )
            """, (self.base_config.get("strategy", "unknown"),))
            parent_id = cursor.lastrowid
            
            # Store grid search metadata in run_configs
            cursor.execute("""
                INSERT INTO run_configs (
                    run_id, symbol, timeframe, start_date, end_date,
                    initial_capital, risk_per_trade_pct, params
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                parent_id,
                self.base_config.get("symbol", "UNKNOWN"),
                self.base_config.get("timeframe", "UNKNOWN"),
                datetime.now().isoformat(),
                datetime.now().isoformat(),
                str(self.base_config.get("backtest", {}).get("initial_balance", 10000)),
                "0.02",
                json.dumps({
                    "grid_search": True,
                    "param_grid": param_grid,
                    "total_combinations": total
                })
            ))
            
            return parent_id
    
    def _save_child_run(
        self,
        parent_id: int,
        params: Dict[str, Any],
        metrics: Dict[str, Any],
        config: Dict[str, Any]
    ) -> int:
        """Save individual grid search run."""
        with get_cursor() as cursor:
            # Create child run
            cursor.execute("""
                INSERT INTO runs (strategy_id, status, created_at)
                VALUES (
                    (SELECT id FROM strategies WHERE name = ? LIMIT 1),
                    'completed',
                    CURRENT_TIMESTAMP
                )
            """, (config.get("strategy", "unknown"),))
            run_id = cursor.lastrowid
            
            # Save config
            cursor.execute("""
                INSERT INTO run_configs (
                    run_id, symbol, timeframe, start_date, end_date,
                    initial_capital, risk_per_trade_pct, params
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id,
                config.get("symbol", "UNKNOWN"),
                config.get("timeframe", "UNKNOWN"),
                datetime.now().isoformat(),
                datetime.now().isoformat(),
                str(config.get("backtest", {}).get("initial_balance", 10000)),
                "0.02",
                json.dumps({
                    "parent_run_id": parent_id,
                    "grid_params": params
                })
            ))
            
            # Save results
            if "error" not in metrics:
                cursor.execute("""
                    INSERT INTO run_results (
                        run_id, net_profit, net_profit_pct, win_rate,
                        max_drawdown_pct, sharpe_ratio, total_trades, exit_reasons
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    run_id,
                    str(metrics.get("net_profit", 0)),
                    metrics.get("net_profit_pct", 0),
                    metrics.get("win_rate", 0),
                    metrics.get("max_drawdown_pct", 0),
                    metrics.get("sharpe_ratio", 0),
                    metrics.get("total_trades", 0),
                    json.dumps({})
                ))
            
            return run_id
    
    def _update_parent_summary(
        self,
        parent_id: int,
        results: List[Dict],
        best: Optional[Dict]
    ):
        """Update parent run with summary data."""
        with get_cursor() as cursor:
            cursor.execute("""
                UPDATE runs 
                SET status = 'completed', completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (parent_id,))
            
            # Store aggregate results
            if best:
                cursor.execute("""
                    INSERT INTO run_results (
                        run_id, net_profit, net_profit_pct, win_rate,
                        max_drawdown_pct, sharpe_ratio, total_trades, exit_reasons
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    parent_id,
                    str(best["metrics"].get("net_profit", 0)),
                    best["metrics"].get("net_profit_pct", 0),
                    best["metrics"].get("win_rate", 0),
                    best["metrics"].get("max_drawdown_pct", 0),
                    best["metrics"].get("sharpe_ratio", 0),
                    len(results),  # Total combinations as "trades"
                    json.dumps({"best_params": best["params"]})
                ))
    
    def _generate_heatmap_data(
        self,
        param_grid: Dict[str, List[Any]],
        results: List[Dict]
    ) -> Dict[str, Any]:
        """Generate data for heatmap visualization."""
        keys = list(param_grid.keys())
        
        if len(keys) < 2:
            # 1D grid: return as line chart data
            return {
                "type": "line",
                "x_param": keys[0] if keys else None,
                "x_values": param_grid.get(keys[0], []) if keys else [],
                "metrics": [r["metrics"].get("net_profit_pct", 0) for r in results]
            }
        
        # 2D grid: return as heatmap
        x_param = keys[0]
        y_param = keys[1]
        x_values = param_grid[x_param]
        y_values = param_grid[y_param]
        
        # Build 2D matrix
        data = []
        for r in results:
            x_idx = x_values.index(r["params"][x_param])
            y_idx = y_values.index(r["params"][y_param])
            data.append([x_idx, y_idx, r["metrics"].get("net_profit_pct", 0)])
        
        return {
            "type": "heatmap",
            "x_param": x_param,
            "y_param": y_param,
            "x_values": x_values,
            "y_values": y_values,
            "data": data,
            "metric": "net_profit_pct"
        }
