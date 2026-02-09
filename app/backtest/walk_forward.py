"""
Walk-Forward Optimization Module
================================
Implements sliding window backtesting for robust strategy validation.
"""

from datetime import datetime, timedelta
import pandas as pd
from typing import Dict, List, Any, Optional
import json

from app.backtest.engine import BacktestEngine
from app.db.connection import get_cursor
from app.db.repositories.runs import RunsRepository

class WalkForwardOptimization:
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
        periods: int = 5,
        train_ratio: float = 0.7,  # 70% In-Sample, 30% Out-of-Sample
        overlap: bool = False      # Rolling vs Anchored (Simplified to Rolling for now)
    ) -> Dict[str, Any]:
        """
        Run Walk-Forward Analysis.
        
        Splits data into `periods` segments. For each segment:
        1. Optimize parameters on In-Sample (IS) data. (Skipped for MVP - uses base config)
        2. Test best params on Out-of-Sample (OOS) data.
        
        Args:
            periods: Number of walk-forward windows.
            train_ratio: Portion of window used for optimization (IS).
            
        Returns:
            Dict detailed results for IS and OOS phases.
        """
        
        # Load full dataset to determine ranges
        engine = BacktestEngine(self.data_path, self.strategy_class, self.base_config)
        full_df = engine.load_data()
        
        if full_df.empty:
            return {"error": "No data available"}
            
        total_rows = len(full_df)
        window_size = total_rows // periods
        
        # Create Parent Run
        parent_id = self._create_parent_run(periods)
        
        is_results = []
        oos_results = []
        
        for i in range(periods):
            start_idx = i * window_size
            end_idx = start_idx + window_size
            
            # Split window into IS and OOS
            window_df = full_df.iloc[start_idx:end_idx]
            split_idx = int(len(window_df) * train_ratio)
            
            is_data = window_df.iloc[:split_idx]
            oos_data = window_df.iloc[split_idx:]
            
            # In-Sample Run (Optimization Simulated)
            # In a full version, we'd run Grid Search here. 
            # For now, we run the base config to establish baseline.
            is_metrics = self._run_segment(is_data, "IS", i+1, parent_id)
            is_results.append(is_metrics)
            
            # Out-of-Sample Run (Validation)
            # Run with "Optimized" params (base config in this MVP)
            oos_metrics = self._run_segment(oos_data, "OOS", i+1, parent_id)
            oos_results.append(oos_metrics)
            
        # Aggregate Results
        summary = self._calculate_summary(oos_results)
        self._update_parent_run(parent_id, summary)
        
        return {
            "parent_run_id": parent_id,
            "is_results": is_results,
            "oos_results": oos_results,
            "summary": summary
        }

    def _run_segment(
        self, 
        data: pd.DataFrame, 
        phase: str, 
        window: int, 
        parent_id: int
    ) -> Dict[str, Any]:
        """Execute backtest on a specific data segment."""
        if data.empty:
            return {}
            
        # Temporary engine with sliced data
        # We inject the sliced dataframe directly or save to temp CSV
        # For performance/simplicity in this MVP, we'll modify engine to accept DF
        
        # Hack: Save slice to temp CSV is safer for current Engine architecture
        import tempfile
        import os
        
        fd, temp_path = tempfile.mkstemp(suffix='.csv')
        try:
            os.close(fd)
            data.to_csv(temp_path)
            
            engine = BacktestEngine(
                data_path=temp_path,
                strategy_class=self.strategy_class,
                config=self.base_config
            )
            engine.run()
            
            metrics = engine.results
            metrics["window"] = window
            metrics["phase"] = phase
            metrics["start_date"] = data.index[0].isoformat()
            metrics["end_date"] = data.index[-1].isoformat()
            
            # Save to DB as child run
            self._save_child_run(parent_id, metrics, self.base_config, phase, window)
            
            return metrics
            
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def _create_parent_run(self, periods: int) -> int:
        """Create parent run entry."""
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
                    "walk_forward": True,
                    "periods": periods
                })
            ))
            return parent_id

    def _save_child_run(
        self, 
        parent_id: int, 
        metrics: Dict, 
        config: Dict,
        phase: str,
        window: int
    ):
        with get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO runs (strategy_id, status, created_at)
                VALUES (
                    (SELECT id FROM strategies WHERE name = ? LIMIT 1),
                    'completed',
                    CURRENT_TIMESTAMP
                )
            """, (config.get("strategy", "unknown"),))
            run_id = cursor.lastrowid
            
            params = {
                "parent_run_id": parent_id,
                "wf_phase": phase,
                "wf_window": window
            }
            
            cursor.execute("""
                INSERT INTO run_configs (
                    run_id, symbol, timeframe, start_date, end_date,
                    initial_capital, risk_per_trade_pct, params
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id,
                config.get("symbol", "UNKNOWN"),
                config.get("timeframe", "UNKNOWN"),
                metrics.get("start_date"),
                metrics.get("end_date"),
                str(config.get("backtest", {}).get("initial_balance", 10000)),
                "0.02",
                json.dumps(params)
            ))
            
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

    def _calculate_summary(self, results: List[Dict]) -> Dict:
        """Calculate aggregated OOS statistics."""
        if not results:
            return {}
            
        total_profit = sum(r.get("net_profit_pct", 0) for r in results)
        avg_profit = total_profit / len(results)
        
        return {
            "total_profit_pct": total_profit,
            "avg_window_profit_pct": avg_profit,
            "consistency": len([r for r in results if r.get("net_profit_pct", 0) > 0]) / len(results)
        }

    def _update_parent_run(self, parent_id: int, summary: Dict):
        with get_cursor() as cursor:
            cursor.execute("""
                UPDATE runs 
                SET status = 'completed', completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (parent_id,))
            
            cursor.execute("""
                INSERT INTO run_results (
                    run_id, net_profit, net_profit_pct, win_rate,
                    max_drawdown_pct, sharpe_ratio, total_trades, exit_reasons
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                parent_id,
                "0",
                summary.get("total_profit_pct", 0),
                summary.get("consistency", 0) * 100, # Treat consistency as win rate
                0, 0, 0,
                json.dumps(summary)
            ))
