"""
Run Comparison Module
=====================
Logic for comparing multiple backtest runs side-by-side.
"""

from typing import List, Dict, Any
import json
from app.db.connection import get_cursor
from app.db.repositories.runs import RunsRepository

class RunComparison:
    def __init__(self):
        self.runs_repo = RunsRepository()

    def compare(self, run_ids: List[int]) -> Dict[str, Any]:
        """
        Compare multiple runs by ID.
        
        Args:
            run_ids: List of run IDs to compare.
            
        Returns:
            Dict containing comparison data structured for UI consumption.
        """
        if not run_ids:
            return {"error": "No run IDs provided"}

        comparison_data = []

        with get_cursor() as cursor:
            for run_id in run_ids:
                # Fetch run details
                run_details = self.runs_repo.get_run_details(cursor, run_id)
                if not run_details:
                    continue
                
                # Fetch config
                config_row = cursor.execute(
                    "SELECT params FROM run_configs WHERE run_id = ?", (run_id,)
                ).fetchone()
                config = json.loads(config_row[0]) if config_row else {}

                # Fetch results
                results_row = cursor.execute(
                    """
                    SELECT net_profit_pct, win_rate, max_drawdown_pct, sharpe_ratio, total_trades
                    FROM run_results WHERE run_id = ?
                    """,
                    (run_id,)
                ).fetchone()

                metrics = {}
                if results_row:
                    metrics = {
                        "net_profit_pct": results_row[0],
                        "win_rate": results_row[1],
                        "max_drawdown_pct": results_row[2],
                        "sharpe_ratio": results_row[3],
                        "total_trades": results_row[4]
                    }

                comparison_data.append({
                    "id": run_id,
                    "strategy": run_details["strategy"],
                    "status": run_details["status"],
                    "created_at": run_details["created_at"],
                    "config": config,
                    "metrics": metrics
                })

        return {
            "runs": comparison_data,
            "count": len(comparison_data)
        }
