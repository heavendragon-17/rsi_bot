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

import signal
import structlog
import threading
import time
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Type

from app.core.interfaces import IExchange, IStrategy
from app.trading.portfolio.manager import PortfolioManager
from app.services.market_data.store import MarketDataStore
from app.services.market_data.stream_manager import BinanceStreamManager
from app.services.market_data.normalizer import DataNormalizer
from app.core.snapshots import ContextSnapshot
from app.core.actions import OpenPosition, ClosePosition, MoveSL, PartialClose, DoNothing
from app.core.events import SignalEvent

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
        self._cleanup_on_startup()

        # 3. Start market data stream
        self._start_stream()

        # 3b. Sim mode: start aggTrade tick stream + funding scheduler
        self._sim_stream = None
        self._funding_scheduler = None
        if self.config.get("bot", {}).get("mode") == "sim":
            from app.sim.stream_manager import SimTradeStreamManager
            from app.sim.funding import SimFundingScheduler
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

    def _action_to_signal(self, action: OpenPosition) -> SignalEvent:
        """Convert an OpenPosition action to a SignalEvent for PortfolioManager."""
        tp_prices = action.tp_prices or []
        return SignalEvent(
            symbol=action.symbol,
            signal_type="BUY",
            price=action.entry_price,
            timestamp=datetime.now(),
            reason=action.reason,
            sl_price=action.sl_price,
            soft_sl_price=action.soft_sl_price,
            tp1_price=tp_prices[0] if len(tp_prices) > 0 else None,
            tp2_price=tp_prices[1] if len(tp_prices) > 1 else None,
            tp3_price=tp_prices[2] if len(tp_prices) > 2 else None,
            signal_class=action.signal_class,
            lock_profit_price=action.lock_profit_price,
            tp_allocations=action.tp_allocations,
        )

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
        portfolio = PortfolioManager(self.exchange, self.config, notification_service=self._notification_service)

        # Store references for monitoring
        self.strategies[symbol] = strategy
        self.portfolios[symbol] = portfolio

        logger.info(f"[{symbol}] Strategy loop started")

        # Track last processed candle timestamp to avoid duplicate processing
        last_processed_ts = None

        while self.running.is_set():
            try:
                # Get latest candle data using normalized store key
                store_key = self._store_keys.get(symbol, symbol)
                df = self.store.get_dataframe(store_key)

                if df is None or df.empty:
                    logger.debug(f"[{symbol}] No data yet (store_key={store_key})")
                    time.sleep(1)
                    continue

                # Get timestamp of latest candle
                current_ts = df.index[-1]

                # Find the most recently closed candle
                closed_candles = df[df['closed'] == True]
                
                if closed_candles.empty:
                    time.sleep(0.5)
                    continue

                # Get the timestamp of the last closed candle
                last_closed_ts = closed_candles.index[-1]

                # Skip if we already processed this closed candle
                if last_closed_ts == last_processed_ts:
                    time.sleep(0.5)
                    continue

                # Slice df up to the last closed candle to prevent strategy
                # from computing signals on incomplete data
                df_to_analyze = df.loc[:last_closed_ts].copy()

                # Sim mode: forward new candle open to SimExchange so pending_open
                # entry orders fill at realistic open price (not signal time price).
                if self.config.get("bot", {}).get("mode") == "sim" and hasattr(self.exchange, "on_kline_open"):
                    # Use the open price of the exact next unclosed candle if available
                    open_price = Decimal(str(df_to_analyze.iloc[-1].get("close", 0)))
                    if current_ts > last_closed_ts:
                        open_price = Decimal(str(df.loc[current_ts, "open"]))
                    self.exchange.on_kline_open(symbol, open_price)

                # Build stateless inputs for strategy
                position = portfolio.get_position_snapshot(symbol)
                ctx = self.contexts.get(symbol, ContextSnapshot(state="SCANNING"))

                # Analyze candle — returns typed actions + new context
                result = strategy.analyze(symbol, df_to_analyze, position=position, context=ctx)

                # Persist new context for next candle
                self.contexts[symbol] = result.new_context

                # Dispatch actions
                # IMPORTANT: Never send Telegram notifications synchronously here.
                # All notifications go through NotificationService (async queue).
                # Synchronous calls block this thread and delay other symbol processing.
                for action in result.actions:
                    if isinstance(action, OpenPosition):
                        signal = self._action_to_signal(action)
                        logger.info(f"[{symbol}] SIGNAL: {signal.signal_type} | {action.reason}")
                        order = portfolio.on_signal(signal)
                        if order:
                            logger.info(f"[{symbol}] Order placed successfully")
                        else:
                            logger.warning(f"[{symbol}] Signal processed but no order placed")
                    elif isinstance(action, ClosePosition):
                        logger.info(f"[{symbol}] ClosePosition: {action.reason}")
                        portfolio.close_position(action.symbol, reason=action.reason, price=action.price)
                    elif isinstance(action, MoveSL):
                        logger.info(f"[{symbol}] MoveSL -> {action.new_sl_price}: {action.reason}")
                        portfolio.move_stop_loss(action.symbol, action.new_sl_price)
                    elif isinstance(action, PartialClose):
                        logger.info(f"[{symbol}] PartialClose {action.tp_level} @ {action.price}: {action.reason}")
                        portfolio.execute_partial_close(action.symbol, action.tp_level, new_sl_price=action.new_sl_price)
                    # DoNothing: no-op

                # Sync TP fills from exchange (limit TP orders that filled on exchange)
                if symbol in portfolio.positions:
                    portfolio.sync_tp_fills(symbol)

                last_processed_ts = last_closed_ts

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
