# app/trading/runner_loop.py
"""
Symbol Trading Loop & Startup Helpers
======================================
Extracted from MultiSymbolRunner to keep files under 400 lines.

Contains:
- run_symbol_loop()    — main per-symbol trading loop (one per thread)
- action_to_signal()   — convert OpenPosition action → SignalEvent
- cleanup_on_startup() — close orphan positions from previous run
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from decimal import Decimal
from typing import Any

import structlog

from app.core.actions import (
    ClosePosition,
    MoveSL,
    OpenPosition,
    PartialClose,
    SendAlert,
)
from app.core.events import SignalEvent
from app.core.interfaces import IExchange, IStrategy
from app.core.snapshots import ContextSnapshot
from app.data.store import MarketDataStore
from app.trading.portfolio.manager import PortfolioManager

logger = structlog.get_logger()


def action_to_signal(action: OpenPosition) -> SignalEvent:
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
        indicators=action.indicators,
    )


def cleanup_on_startup(
    exchange: IExchange,
    notification_service: Any = None,
) -> None:
    """
    Close all open positions and cancel all orders from previous run.

    Args:
        exchange: The exchange instance to clean up.
        notification_service: Optional notification service for alerts.
    """
    try:
        positions = exchange.fetch_positions()
    except Exception as e:
        logger.error(f"Failed to fetch positions on startup: {e}")
        return

    if not positions:
        logger.info("No orphan positions found on startup.")
        return

    logger.warning(f"Found {len(positions)} orphan positions. Closing all...")

    for pos in positions:
        symbol = pos["symbol"]
        amount = Decimal(str(pos.get("contracts", 0)))
        side = "SELL" if pos.get("side") == "long" else "BUY"

        # Cancel all orders first
        try:
            exchange.cancel_all_orders(symbol)
        except Exception as e:
            logger.error(f"Failed to cancel orders for {symbol}: {e}")

        # Market close with reduceOnly
        try:
            exchange.create_order(
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
    if notification_service:
        try:
            notification_service.send_message(f"\u26a0\ufe0f Bot restarted. Closed {len(positions)} orphan positions.")
        except Exception:
            pass


def run_symbol_loop(
    symbol: str,
    config: dict[str, Any],
    strategy: IStrategy,
    portfolio: PortfolioManager,
    exchange: IExchange,
    store: MarketDataStore,
    store_key: str,
    contexts: dict[str, ContextSnapshot],
    running: threading.Event,
    notification_service: Any = None,
) -> None:
    """
    Main trading loop for a single symbol.

    Each symbol runs in its own thread with:
    - Its own Strategy instance
    - Its own PortfolioManager instance
    - Shared Exchange (thread-safe)
    - Shared MarketDataStore (thread-safe)

    Args:
        symbol: Trading pair (e.g. "BTC/USDT").
        config: Application configuration dict.
        strategy: Strategy instance for this symbol.
        portfolio: PortfolioManager instance for this symbol.
        exchange: Shared exchange instance.
        store: Shared MarketDataStore instance.
        store_key: Normalized key for the store (e.g. "BTC").
        contexts: Shared dict of ContextSnapshots, keyed by symbol.
        running: Threading event — loop runs while this is set.
    """

    logger.info(f"[{symbol}] Strategy loop started")

    # Track last processed candle timestamp to avoid duplicate processing
    last_processed_ts = None

    # Tick-mode strategies (e.g. rsi_alert) evaluate on every iteration using
    # the full DataFrame (including the in-progress candle) instead of waiting
    # for candle close. They must only emit SendAlert / DoNothing actions.
    tick_mode = bool(getattr(strategy, "tick_mode", False))

    while running.is_set():
        try:
            # Get latest candle data using normalized store key
            df = store.get_dataframe(store_key)

            if df is None or df.empty:
                logger.debug(f"[{symbol}] No data yet (store_key={store_key})")
                time.sleep(1)
                continue

            # Get timestamp of latest candle
            current_ts = df.index[-1]

            if tick_mode:
                ctx = contexts.get(symbol, ContextSnapshot(state="SCANNING"))
                position = portfolio.get_position_snapshot(symbol)
                result = strategy.analyze(symbol, df, position=position, context=ctx)
                contexts[symbol] = result.new_context
                for action in result.actions:
                    if isinstance(action, SendAlert):
                        logger.info(
                            f"[{symbol}] ALERT ({action.tier or 'n/a'}): {action.message}"
                        )
                        if notification_service:
                            try:
                                notification_service.send_message(action.message)
                            except Exception as e:
                                logger.error(f"[{symbol}] Alert dispatch failed: {e}")
                time.sleep(1)
                continue

            # Find the most recently closed candle
            closed_candles = df[df["closed"]]

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
            if config.get("bot", {}).get("mode") == "sim" and hasattr(exchange, "on_kline_open"):
                # Use the open price of the exact next unclosed candle if available
                open_price = Decimal(str(df_to_analyze.iloc[-1].get("close", 0)))
                if current_ts > last_closed_ts:
                    open_price = Decimal(str(df.loc[current_ts, "open"]))
                exchange.on_kline_open(symbol, open_price)

            # Build stateless inputs for strategy
            position = portfolio.get_position_snapshot(symbol)
            ctx = contexts.get(symbol, ContextSnapshot(state="SCANNING"))

            # Analyze candle — returns typed actions + new context
            result = strategy.analyze(symbol, df_to_analyze, position=position, context=ctx)

            # Persist new context for next candle
            contexts[symbol] = result.new_context

            # Dispatch actions
            # IMPORTANT: Never send Telegram notifications synchronously here.
            # All notifications go through NotificationService (async queue).
            # Synchronous calls block this thread and delay other symbol processing.
            for action in result.actions:
                if isinstance(action, OpenPosition):
                    signal = action_to_signal(action)
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
                elif isinstance(action, SendAlert):
                    logger.info(f"[{symbol}] ALERT ({action.tier or 'n/a'}): {action.message}")
                    if notification_service:
                        try:
                            notification_service.send_message(action.message)
                        except Exception as e:
                            logger.error(f"[{symbol}] Alert dispatch failed: {e}")
                # DoNothing: no-op

            # Sync TP fills from exchange (limit TP orders that filled on exchange)
            if symbol in portfolio.positions:
                portfolio.sync_tp_fills(symbol)

            # Reconcile against the exchange so a hard SL fill (or any out-of-band
            # close) doesn't leave a phantom entry in the in-memory dict — that
            # would block the deploy pipeline.
            portfolio.sync_from_exchange()

            last_processed_ts = last_closed_ts

            # Small sleep to prevent CPU spinning
            time.sleep(0.1)

        except Exception as e:
            logger.error(f"[{symbol}] Error in trading loop: {e}", exc_info=True)
            time.sleep(5)  # Back off on error

    logger.info(f"[{symbol}] Strategy loop stopped")
