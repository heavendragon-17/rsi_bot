"""
Simulation Engine — Master Orchestrator
========================================
Ties all 4 simulation methods together into a single entry point.

Instead of calling each method individually, you:
  1. Create a SimulationEngine with your real OHLCV data.
  2. Call run_all() to fit models and generate paths from all 4 methods.
  3. Use paths_to_ohlcv() to convert any path to a DataFrame your
     BacktestEngine can consume.

The engine does NOT run your strategy — that's the backtest engine's job.
This engine only produces simulated data. The workflow is:

  Real OHLCV data → SimulationEngine → simulated OHLCV CSVs → BacktestEngine

Usage:
  from app.backtest.simulation.engine import SimulationEngine

  engine = SimulationEngine.from_csv("app/backtest/data/BTCUSDT_5m.csv")
  results = engine.run_all(num_paths=1000, path_length=252)

  # results is a dict with keys: 'historical', 'bootstrap', 'garch', 'regime'
  # Each contains a numpy array of price paths (path_length x num_paths).

  # Convert one path to OHLCV for backtesting:
  ohlcv_df = engine.path_to_ohlcv(results['bootstrap'][:, 0])
  ohlcv_df.to_csv("simulated_path.csv", index=False)
"""

from __future__ import annotations

import structlog
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.core.constants import (
    SIM_BLOCK_BOOTSTRAP_SIZE,
    SIM_DEFAULT_NUM_PATHS,
    SIM_DEFAULT_PATH_LENGTH,
)

from app.backtest.simulation.block_bootstrap import BlockBootstrap
from app.backtest.simulation.garch_simulation import GarchSimulation
from app.backtest.simulation.historical_replay import HistoricalReplay, Scenario
from app.backtest.simulation.ohlcv_builder import OHLCVBuilder
from app.backtest.simulation.regime_switching import RegimeSwitching

logger = structlog.get_logger()


@dataclass
class SimulationResults:
    """Container for all simulation outputs.

    Attributes:
        historical:      List of Scenario objects (real crash replays).
        bootstrap_paths: numpy array (path_length x num_paths) from block bootstrap.
        garch_paths:     numpy array (path_length x num_paths) from GARCH simulation.
        regime_paths:    numpy array (path_length x num_paths) from regime switching.
        garch_summary:   Human-readable GARCH fit summary.
        regime_summary:  Human-readable regime fit summary.
        metadata:        Dict with run parameters (num_paths, path_length, etc.).
    """

    historical: list[Scenario] = field(default_factory=list)
    bootstrap_paths: np.ndarray | None = None
    garch_paths: np.ndarray | None = None
    regime_paths: np.ndarray | None = None
    garch_summary: str = ""
    regime_summary: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def all_paths(self) -> dict[str, np.ndarray]:
        """All synthetic price path arrays keyed by method name."""
        paths = {}
        if self.bootstrap_paths is not None:
            paths["bootstrap"] = self.bootstrap_paths
        if self.garch_paths is not None:
            paths["garch"] = self.garch_paths
        if self.regime_paths is not None:
            paths["regime"] = self.regime_paths
        return paths


class SimulationEngine:
    """Master orchestrator for all 4 simulation methods.

    Workflow:
      1. Load real OHLCV data (from CSV or DataFrame).
      2. Compute log-returns from close prices.
      3. Learn candle shapes for OHLCV reconstruction.
      4. Run all simulation methods.
    """

    def __init__(self, df: pd.DataFrame) -> None:
        """Initialize from a real OHLCV DataFrame.

        Args:
            df: DataFrame with at least 'close' column.
                Should also have 'open', 'high', 'low', 'volume' for
                the OHLCV builder to learn candle shapes.
        """
        self._df = df.copy()
        self._closes = df["close"].values.astype(np.float64)

        # Compute log-returns: r_t = ln(close_t / close_{t-1}).
        # First return is NaN (no previous close), so we drop it.
        log_returns = np.diff(np.log(self._closes))
        self._returns = pd.Series(log_returns, name="log_returns")

        # Learn candle shapes from real data.
        required_cols = {"open", "high", "low", "close"}
        if required_cols.issubset(df.columns):
            self._ohlcv_builder = OHLCVBuilder.from_real_data(df)
        else:
            self._ohlcv_builder = None

        logger.info(
            "simulation_engine_init",
            candles=len(df),
            returns=len(self._returns),
            mean_return=f"{float(self._returns.mean()):.6f}",
            std_return=f"{float(self._returns.std()):.6f}",
        )

    @classmethod
    def from_csv(cls, path: str) -> SimulationEngine:
        """Create engine from a CSV file (same format as your backtest data).

        Args:
            path: Path to CSV with columns: timestamp, open, high, low, close, volume.

        Returns:
            SimulationEngine instance ready to run simulations.
        """
        df = pd.read_csv(path)
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
        return cls(df)

    def run_all(
        self,
        num_paths: int = SIM_DEFAULT_NUM_PATHS,
        path_length: int = SIM_DEFAULT_PATH_LENGTH,
        block_size: int = SIM_BLOCK_BOOTSTRAP_SIZE,
        seed: int | None = 42,
        methods: list[str] | None = None,
    ) -> SimulationResults:
        """Run all 4 simulation methods and return combined results.

        Args:
            num_paths:   Simulated paths per method (default 1000).
            path_length: Days per path (default 252).
            block_size:  Block size for bootstrap (default 20).
            seed:        Master random seed (None = random).
            methods:     Which methods to run. Default None = all four.
                         Options: ["historical", "bootstrap", "garch", "regime"].

        Returns:
            SimulationResults containing all outputs.
        """
        if methods is None:
            methods = ["historical", "bootstrap", "garch", "regime"]

        results = SimulationResults(
            metadata={
                "num_paths": num_paths,
                "path_length": path_length,
                "block_size": block_size,
                "seed": seed,
                "methods": methods,
                "source_candles": len(self._df),
                "source_returns": len(self._returns),
            }
        )

        # ── Method 1: Historical Replay ──────────────────────────────
        if "historical" in methods:
            logger.info("simulation_method", method="historical_replay")
            replay = HistoricalReplay(self._returns)
            results.historical = replay.find_scenarios(top_n=5, min_window=20)
            results.historical.extend(replay.find_sharp_crashes(top_n=3, window=5))
            logger.info(
                "historical_replay_done",
                scenarios=len(results.historical),
            )

        # ── Method 2: Block Bootstrap ────────────────────────────────
        if "bootstrap" in methods:
            logger.info("simulation_method", method="block_bootstrap", block_size=block_size)
            bs = BlockBootstrap(self._returns, block_size=block_size)
            results.bootstrap_paths = bs.simulate(
                num_paths=num_paths,
                path_length=path_length,
                seed=seed,
            )
            logger.info(
                "block_bootstrap_done",
                shape=results.bootstrap_paths.shape,
            )

        # ── Method 3: GARCH(1,1) ────────────────────────────────────
        if "garch" in methods:
            logger.info("simulation_method", method="garch_skewt")
            garch = GarchSimulation(self._returns)
            garch.fit()
            results.garch_paths = garch.simulate(
                num_paths=num_paths,
                path_length=path_length,
                seed=seed,
            )
            results.garch_summary = garch.summary()
            logger.info(
                "garch_done",
                shape=results.garch_paths.shape,
                persistence=f"{garch.fit_result.persistence:.4f}",
            )

        # ── Method 4: Regime Switching ───────────────────────────────
        if "regime" in methods:
            logger.info("simulation_method", method="regime_switching")
            rs = RegimeSwitching(self._returns)
            rs.fit()
            results.regime_paths = rs.simulate(
                num_paths=num_paths,
                path_length=path_length,
                seed=seed,
            )
            results.regime_summary = rs.summary()
            logger.info(
                "regime_switching_done",
                shape=results.regime_paths.shape,
            )

        return results

    def path_to_ohlcv(
        self,
        price_path: np.ndarray,
        start_price: float | None = None,
        start_date: str = "2024-01-01",
        timeframe: str = "5m",
        seed: int | None = None,
    ) -> pd.DataFrame:
        """Convert a single simulated price path to an OHLCV DataFrame.

        This is the bridge between simulation output and your BacktestEngine.
        The returned DataFrame has the exact same format as your historical
        CSV files, so you can save it and pass it to BacktestEngine.

        Args:
            price_path:  1D array of simulated prices (from any method).
            start_price: Scale the path so it starts at this price.
                         If None, uses the last real close price.
            start_date:  Starting timestamp for the generated candles.
            timeframe:   Candle interval (must match your strategy's timeframe).
            seed:        Random seed for candle shape sampling.

        Returns:
            pandas DataFrame with columns: timestamp, open, high, low,
            close, volume — ready for BacktestEngine.

        Raises:
            RuntimeError: if real data didn't have OHLCV columns for
                          the builder to learn from.
        """
        if self._ohlcv_builder is None:
            raise RuntimeError(
                "OHLCV builder not available — real data must include "
                "open, high, low, close columns."
            )

        # Scale the path to start at the desired price.
        if start_price is None:
            start_price = float(self._closes[-1])

        # Simulated paths start at ~1.0 (they're relative).
        # Scale: absolute_price = path_value * start_price
        scaled_path = price_path * start_price

        return self._ohlcv_builder.build(
            price_path=scaled_path,
            start_date=start_date,
            timeframe=timeframe,
            seed=seed,
        )

    @property
    def returns(self) -> pd.Series:
        """The log-return series computed from real close prices."""
        return self._returns

    @property
    def real_data(self) -> pd.DataFrame:
        """The original real OHLCV DataFrame."""
        return self._df
