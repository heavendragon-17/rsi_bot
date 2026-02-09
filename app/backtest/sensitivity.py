"""
Sensitivity Analysis Module
===========================
Analyzes how robust a strategy is to small changes in parameters.
"""

from typing import Dict, List, Any
import numpy as np
from app.backtest.engine import BacktestEngine
from app.db.connection import get_cursor

class SensitivityAnalysis:
    def __init__(self, data_path: str, strategy_class, base_config: Dict[str, Any]):
        self.data_path = data_path
        self.strategy_class = strategy_class
        self.base_config = base_config

    def run(self, param_name: str, center_value: float, step: float, steps_count: int = 5) -> Dict[str, Any]:
        """
        Run sensitivity analysis centered around a parameter value.
        
        Args:
            param_name: Name of the parameter to vary.
            center_value: The base value.
            step: Step size for variation.
            steps_count: Number of steps on EACH side of center.
            
        Returns:
            Dict containing sensitivity data (parameter values vs metrics).
        """
        
        # Determine parameter type (int or float) based on center_value
        is_int = isinstance(center_value, int)
        
        results = []
        
        # Generate range: center - (step*count) to center + (step*count)
        for i in range(-steps_count, steps_count + 1):
            val = center_value + (i * step)
            if is_int:
                val = int(round(val))
            
            # Avoid duplicate values if step is small and rounding happens
            if results and results[-1]['param_value'] == val:
                continue
                
            # Create config override
            run_config = self.base_config.copy()
            if 'strategy_params' not in run_config:
                run_config['strategy_params'] = {}
            run_config['strategy_params'][param_name] = val
            
            # Run backtest
            try:
                engine = BacktestEngine(self.data_path, self.strategy_class, run_config)
                engine.run()
                metrics = engine.results
                
                results.append({
                    "param_value": val,
                    "net_profit_pct": metrics.get("net_profit_pct", 0),
                    "win_rate": metrics.get("win_rate", 0),
                    "drawdown": metrics.get("max_drawdown_pct", 0),
                    "sharpe": metrics.get("sharpe_ratio", 0)
                })
            except Exception as e:
                import traceback
                traceback.print_exc()
                results.append({
                    "param_value": val,
                    "error": str(e)
                })

        return {
            "parameter": param_name,
            "center": center_value,
            "data": results
        }
