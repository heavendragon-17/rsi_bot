# app/trading/runner.py
"""
Multi-Symbol Concurrent Trading Runner
======================================
Orchestrates multi-symbol trading with one thread per symbol.

Architecture:
- 1 Shared Exchange instance (thread-safe)
- N Threads, each running Strategy + PortfolioManager for one symbol
- Each thread has its own Strategy instance to avoid state conflicts
"""
from __future__ import annotations

import signal
import structlog
import threading
import time
from typing import Any, Dict, List, Optional, Type

from app.core.interfaces import IExchange, IStrategy
from app.trading.portfolio.manager import PortfolioManager
from app.data.store import MarketDataStore
from app.data.stream_manager import BinanceStreamManager
from app.data.normalizer import DataNormalizer
from app.core.snapshots import ContextSnapshot
from app.trading.runner_loop import (
    cleanup_on_startup,
    run_symbol_loop,
)

logger = structlog.get_logger()


class MultiSymbolRunner:
    """
    Multi-symbol concurrent trading runner.

    Spawns a separate thread for each symbol, sharing a single
    thread-safe exchange instance. Each thread has its own
    Strategy and PortfolioManager instances.

    Startup sequence:
    1. Set leverage for all symbols
    2. Close orphan positions from previous run
    3. Start stream and threads
    """

    def __init__(
        self,
        config: Dict[str, Any],
        strategy_class: Type[IStrategy],
        exchange: IExchange,
        notification_service=None,
        telegram=None,  # deprecated — use notification_service
    ):
        """
        Initialize the multi-symbol runner.

        Args:
            config: Application configuration dict
            strategy_class: Strategy class to instantiate per symbol
            exchange: Shared IExchange instance (already created by factory)
            notification_service: Optional NotificationService for trade events
            telegram: Deprecated — kept for backward compat, use notification_service
        """
        self.config = config
        self.strategy_class = strategy_class
        self.symbols = config.get('symbols', [])
        self.timeframe = config.get('timeframe', '15m')

        # Shared exchange (thread-safe)
        self.exchange = exchange
        self._notification_service = notification_service
        self.telegram = notification_service  # backward compat alias
        logger.info(f"Using shared exchange: {type(self.exchange).__name__}")

        # Market data store (already thread-safe)
        self.store = MarketDataStore()

        # Stream manager for real-time data
        self.stream: Optional[BinanceStreamManager] = None

        # Thread management
        self.threads: List[threading.Thread] = []
        self.running = threading.Event()
        self.running.set()  # Start in running state

        # Per-symbol components (created when threads start)
        self.strategies: Dict[str, IStrategy] = {}
        self.portfolios: Dict[str, PortfolioManager] = {}
        self.contexts: Dict[str, ContextSnapshot] = {}

        # Map config symbol (e.g. "BTC/USDT") → store key (e.g. "BTC")
        # DataNormalizer strips the quote asset before storing in MarketDataStore
        self._store_keys: Dict[str, str] = {
            s: DataNormalizer._normalize_symbol(s) for s in self.symbols
        }

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        self.stop()

    def start(self) -> None:
        """Start the multi-symbol trading runner."""
        if not self.symbols:
            logger.warning("No symbols configured, nothing to run")
            return

        logger.info(f"Starting multi-symbol runner for {len(self.symbols)} symbols: {self.symbols}")

        # 1. Set leverage for all symbols
        leverage = self.config.get("risk", {}).get("leverage", 1)
        for symbol in self.symbols:
            try:
                self.exchange.set_leverage(leverage, symbol)
            except Exception as e:
                logger.warning(f"Failed to set leverage for {symbol}: {e}")

        # 2. Close orphan positions from previous run
        cleanup_on_startup(self.exchange, self._notification_service)

        # 3. Start market data stream
        self._start_stream()

        # 3b. Sim mode: start aggTrade tick stream + funding scheduler
        self._sim_stream = None
        self._funding_scheduler = None
        if self.config.get("bot", {}).get("mode") == "sim":
            from app.trading.exchange.sim.sim_stream import SimTradeStreamManager
            from app.trading.exchange.sim.sim_funding import SimFundingScheduler
            self._sim_stream = SimTradeStreamManager(
                symbols=self.symbols,
                sim_exchange=self.exchange,
            )
            self._sim_stream.start()
            self._funding_scheduler = SimFundingScheduler(
                state=self.exchange.state,
                notification_service=self._notification_service,
            )
            self._funding_scheduler.start()

        # Wait for initial data
        time.sleep(2)

        # 4. Spawn a thread for each symbol
        for symbol in self.symbols:
            strategy = self.strategy_class(self.config)
            portfolio = PortfolioManager(
                self.exchange, self.config,
                notification_service=self._notification_service,
            )
            self.strategies[symbol] = strategy
            self.portfolios[symbol] = portfolio

            store_key = self._store_keys.get(symbol, symbol)
            thread = threading.Thread(
                target=run_symbol_loop,
                args=(
                    symbol,
                    self.config,
                    strategy,
                    portfolio,
                    self.exchange,
                    self.store,
                    store_key,
                    self.contexts,
                    self.running,
                ),
                name=f"Symbol-{symbol}",
                daemon=True,
            )
            self.threads.append(thread)
            thread.start()
            logger.info(f"Started thread for {symbol}")

        logger.info(f"All {len(self.threads)} symbol threads started")

    def _start_stream(self) -> None:
        """Start the market data stream."""
        self.stream = BinanceStreamManager(
            symbols=self.symbols,
            timeframe=self.timeframe,
            store=self.store,
            history_limit=300,
            enable_history=True
        )
        self.stream.start()
        logger.info(f"Market data stream started for {self.symbols}")

    def wait(self) -> None:
        """Block until stopped (for main thread)."""
        try:
            while self.running.is_set():
                time.sleep(1)
                # Heartbeat log
                if int(time.time()) % 60 == 0:
                    self._log_status()
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            self.stop()

    def _log_status(self) -> None:
        """Log current status of all running threads."""
        active_threads = [t.name for t in self.threads if t.is_alive()]
        balance = self.exchange.fetch_balance()
        usdt_balance = balance.get('free', {}).get('USDT', 0)
        logger.info(f"Status: {len(active_threads)}/{len(self.threads)} threads active, Balance: {usdt_balance}")

    def stop(self) -> None:
        """Gracefully stop the runner."""
        logger.info("Stopping multi-symbol runner...")

        # Signal all threads to stop
        self.running.clear()

        # Stop market data stream
        if self.stream:
            self.stream.stop()

        # Stop sim-mode infrastructure
        if getattr(self, "_sim_stream", None):
            self._sim_stream.stop()
        if getattr(self, "_funding_scheduler", None):
            self._funding_scheduler.stop()

        # Wait for threads to finish
        for thread in self.threads:
            thread.join(timeout=5)
            if thread.is_alive():
                logger.warning(f"Thread {thread.name} did not stop gracefully")

        # Drain notification queue
        if self._notification_service and hasattr(self._notification_service, "stop"):
            self._notification_service.stop()

        logger.info("Multi-symbol runner stopped")

    def get_status(self) -> Dict[str, Any]:
        """Get current status of the runner."""
        balance = self.exchange.fetch_balance()
        positions = self.exchange.fetch_positions()

        return {
            "running": self.running.is_set(),
            "symbols": self.symbols,
            "active_threads": [t.name for t in self.threads if t.is_alive()],
            "balance": balance,
            "positions": positions,
        }
