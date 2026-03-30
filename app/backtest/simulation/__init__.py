"""
Simulation & Validation Layer for Backtesting
==============================================
Generates synthetic crypto price paths using 4 complementary methods,
then validates that the simulations are realistic before using them
for strategy stress testing.

Quick start:
  from app.backtest.simulation import SimulationEngine

  engine = SimulationEngine.from_csv("app/backtest/data/BTCUSDT_5m.csv")
  results = engine.run_all(num_paths=1000, path_length=252)

  # Convert a simulated path to OHLCV for BacktestEngine:
  ohlcv_df = engine.path_to_ohlcv(results.bootstrap_paths[:, 0])
"""

from app.backtest.simulation.engine import SimulationEngine, SimulationResults

__all__ = ["SimulationEngine", "SimulationResults"]
