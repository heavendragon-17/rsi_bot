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
from typing import Any, Dict, List, Optional, Type

from app.core.interfaces import IFuturesExchange, IStrategy
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

    Startup sequence:
    1. Set leverage for all symbols
    2. Close orphan positions from previous run
    3. Start stream and threads
    """

    def __init__(
        self,
        config: Dict[str, Any],
        strategy_class: Type[IStrategy],
        exchange: IFuturesExchange,
        telegram=None,
    ):
        """
        Initialize the multi-symbol runner.

        Args:
            config: Application configuration dict
            strategy_class: Strategy class to instantiate per symbol
            exchange: Shared IFuturesExchange instance (already created by factory)
            telegram: Optional TelegramBot for notifications
        """
        self.config = config
        self.strategy_class = strategy_class
        self.symbols = config.get('symbols', [])
        self.timeframe = config.get('timeframe', '15m')

        # Shared exchange (thread-safe)
        self.exchange = exchange
        self.telegram = telegram
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
        self._cleanup_on_startup()

        # 3. Start market data stream
        self._start_stream()

        # Wait for initial data
        time.sleep(2)

        # 4. Spawn a thread for each symbol
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

    def _cleanup_on_startup(self) -> None:
        """Close all open positions and cancel all orders from previous run."""
        try:
            positions = self.exchange.fetch_positions()
        except Exception as e:
            logger.error(f"Failed to fetch positions on startup: {e}")
            return

        if not positions:
            logger.info("No orphan positions found on startup.")
            return

        logger.warning(f"Found {len(positions)} orphan positions. Closing all...")

        from decimal import Decimal
        for pos in positions:
            symbol = pos["symbol"]
            amount = Decimal(str(pos.get("contracts", 0)))
            side = "SELL" if pos.get("side") == "long" else "BUY"

            # Cancel all orders first
            try:
                self.exchange.cancel_all_orders(symbol)
            except Exception as e:
                logger.error(f"Failed to cancel orders for {symbol}: {e}")

            # Market close with reduceOnly
            try:
                self.exchange.create_order(
                    symbol=symbol,
                    order_type="market",
                    side=side,
                    amount=amount,
                    params={"reduceOnly": True},
                )
                logger.info(f"Closed orphan position: {symbol} {side} {amount}")
            except Exception as e:
                logger.error(f"Failed to close orphan position {symbol}: {e}")

        # Telegram alert
        if self.telegram:
            try:
                self.telegram.send_message(
                    f"⚠️ Bot restarted. Closed {len(positions)} orphan positions."
                )
            except Exception:
                pass

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
                    logger.info(f"[{symbol}] Signal: {signal_event.signal_type} @ {signal_event.price}")
                    portfolio.on_signal(signal_event)

                # After processing candle, sync TP fills from exchange
                if symbol in portfolio.positions:
                    portfolio.sync_tp_fills(symbol)

                # Sync TP hit status from Portfolio back to Strategy's meta
                # This prevents Strategy from repeatedly emitting TP signals (Ghost TP bug)
                if (hasattr(strategy, 'context') and 
                    strategy.context and 
                    symbol in portfolio.positions and
                    symbol in strategy.context.active_trades):
                    pos = portfolio.positions[symbol]
                    trade = strategy.context.active_trades[symbol]
                    if trade.meta:
                        # Sync all flags that could change during trade management
                        trade.meta["tp1_hit"] = pos.tp1_hit
                        trade.meta["tp2_hit"] = pos.tp2_hit
                        trade.meta["tp3_hit"] = pos.tp3_hit
                        # Also sync SL if it was moved (e.g., to breakeven)
                        if pos.sl_price is not None:
                            trade.meta["sl_price"] = pos.sl_price
                        if hasattr(pos, 'lock_profit_price') and pos.lock_profit_price is not None:
                            trade.meta["lock_profit_price"] = pos.lock_profit_price
                
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
