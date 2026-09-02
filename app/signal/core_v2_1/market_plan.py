"""Canonical Core V2.1 trigger/dependency subscription plan."""

from __future__ import annotations

from datetime import timedelta

from app.signal.core_v2_1.models import (
    BundleRequirement,
    MarketKey,
    MarketPlan,
    TriggerPlan,
)
from app.trading.strategy.core_v2_1.config import (
    BINANCE_TRADE_CANDIDATES,
    BTC_BENCHMARK,
    INSTRUMENTS,
    TRADE_CANDIDATES,
)
from app.trading.strategy.core_v2_1.indicators import (
    M15_EVALUATION_MINIMUM_CANDLES,
    RSI_BUNDLE_MINIMUM_CANDLES,
)

BINANCE_STRATEGY_SYMBOLS: tuple[str, ...] = BINANCE_TRADE_CANDIDATES


def build_core_v2_1_market_plan(
    *,
    m15_history: int = M15_EVALUATION_MINIMUM_CANDLES,
    h1_history: int = RSI_BUNDLE_MINIMUM_CANDLES,
    h4_history: int = RSI_BUNDLE_MINIMUM_CANDLES,
) -> MarketPlan:
    """Build the locked 25-symbol Core V2.1 public-data graph.

    The strategy symbol ``PUMP`` intentionally maps to the structurally
    distinct Hyperliquid source pair ``PUMP/USDC:USDC``.  It is never aliased
    to a Binance-style ``PUMP/USDT:USDT`` market.
    """

    btc_h1 = MarketKey(BTC_BENCHMARK.venue, BTC_BENCHMARK.venue_symbol, "1h")
    btc_h4 = MarketKey(BTC_BENCHMARK.venue, BTC_BENCHMARK.venue_symbol, "4h")
    trigger_routes = [
        (
            strategy_symbol,
            INSTRUMENTS[strategy_symbol].venue,
            INSTRUMENTS[strategy_symbol].venue_symbol,
        )
        for strategy_symbol in TRADE_CANDIDATES
    ]

    plans: list[TriggerPlan] = []
    for strategy_symbol, venue, instrument in trigger_routes:
        trigger = MarketKey(venue, instrument, "15m")
        alt_h1 = MarketKey(venue, instrument, "1h")
        requirements = (
            BundleRequirement(
                key=trigger,
                minimum_candles=m15_history,
                max_staleness=timedelta(0),
            ),
            BundleRequirement(
                key=alt_h1,
                minimum_candles=h1_history,
                max_staleness=timedelta(minutes=45),
            ),
            BundleRequirement(
                key=btc_h1,
                minimum_candles=h1_history,
                max_staleness=timedelta(minutes=45),
            ),
            BundleRequirement(
                key=btc_h4,
                minimum_candles=h4_history,
                max_staleness=timedelta(hours=3, minutes=45),
            ),
        )
        plans.append(
            TriggerPlan(
                strategy_symbol=strategy_symbol,
                trigger=trigger,
                requirements=requirements,
            )
        )

    return MarketPlan(triggers=tuple(plans))
