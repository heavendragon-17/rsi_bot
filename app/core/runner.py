# app/core/runner.py
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

import logging
import signal
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Type

from app.core.interfaces import IExchange, IStrategy
from app.core.portfolio import PortfolioManager
from app.services.market_data.store import MarketDataStore
from app.services.market_data.stream_manager import BinanceStreamManager

logger = logging.getLogger(__name__)


class MultiSymbolRunner:
    """
    Multi-symbol concurrent trading runner.
    
    Spawns a separate thread for each symbol, sharing a single
    thread-safe exchange instance. Each thread has its own
    Strategy and PortfolioManager instances.
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        strategy_class: Type[IStrategy],
        exchange_factory: Callable[[Dict], IExchange],
    ):
        """
        Initialize the multi-symbol runner.
        
        Args:
            config: Application configuration dict
            strategy_class: Strategy class to instantiate per symbol
            exchange_factory: Factory function to create exchange instance
        """
        self.config = config
        self.strategy_class = strategy_class
        self.symbols = config.get('symbols', [])
        self.timeframe = config.get('timeframe', '15m')
        
        # Create shared exchange (thread-safe)
        self.exchange = exchange_factory(config)
        logger.info(f"Created shared exchange: {type(self.exchange).__name__}")
        
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
        
        # Start market data stream
        self._start_stream()
        
        # Wait for initial data
        time.sleep(2)
        
        # Spawn a thread for each symbol
        for symbol in self.symbols:
            thread = threading.Thread(
                target=self._run_symbol_loop,
                args=(symbol,),
                name=f"Symbol-{symbol}",
                daemon=True
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
    
    def _run_symbol_loop(self, symbol: str) -> None:
        """
        Main trading loop for a single symbol.
        
        Each symbol runs in its own thread with:
        - Its own Strategy instance
        - Its own PortfolioManager instance
        - Shared Exchange (thread-safe)
        - Shared MarketDataStore (thread-safe)
        """
        # Create per-symbol components
        strategy = self.strategy_class(self.config)
        portfolio = PortfolioManager(self.exchange, self.config)
        
        # Store references for monitoring
        self.strategies[symbol] = strategy
        self.portfolios[symbol] = portfolio
        
        logger.info(f"[{symbol}] Strategy loop started")
        
        # Track last processed candle timestamp to avoid duplicate processing
        last_processed_ts = None
        
        while self.running.is_set():
            try:
                # Get latest candle data
                df = self.store.get_dataframe(symbol)
                
                if df is None or df.empty:
                    time.sleep(1)
                    continue
                
                # Get timestamp of latest candle
                current_ts = df.index[-1]
                
                # Check for pending entry (BLOCKING)
                # We check this frequently (throttled inside portfolio) to handle partial fills/timeouts
                if portfolio.has_pending_entry(symbol):
                    portfolio.check_pending_entry(symbol, current_ts)
                    time.sleep(1.0) # Sleep a bit to avoid hot loop, internal throttle handles the rest
                    continue

                # Skip if we already processed this candle
                if current_ts == last_processed_ts:
                    time.sleep(0.5)
                    continue
                
                # Only process closed candles
                last_row = df.iloc[-1]
                if not last_row.get('closed', False):
                    time.sleep(0.5)
                    continue
                
                # Analyze and generate signal
                signal_event = strategy.analyze(symbol, df)
                
                if signal_event:
                    logger.info(f"[{symbol}] Signal: {signal_event.side} @ {signal_event.price}")
                    portfolio.on_signal(signal_event)
                
                last_processed_ts = current_ts
                
                # Small sleep to prevent CPU spinning
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"[{symbol}] Error in trading loop: {e}", exc_info=True)
                time.sleep(5)  # Back off on error
        
        logger.info(f"[{symbol}] Strategy loop stopped")
    
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
        
        # Wait for threads to finish
        for thread in self.threads:
            thread.join(timeout=5)
            if thread.is_alive():
                logger.warning(f"Thread {thread.name} did not stop gracefully")
        
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
