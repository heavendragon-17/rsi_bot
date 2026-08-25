"""Locked configuration and instrument universe for Core V2.1.

The strategy specification deliberately has no runtime-tunable signal
parameters.  Keeping these values in an immutable object makes drift between
live evaluation and historical replay visible instead of silently accepting a
different strategy under the same name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Final

STRATEGY_VERSION: Final[str] = "2.1"
CONFIG_VERSION: Final[str] = "core-v2.1-locked-2026-08-20"


class Venue(StrEnum):
    """Market-data venue used by a Core V2.1 instrument."""

    BINANCE_FUTURES = "BINANCE_FUTURES"
    HYPERLIQUID_PERP = "HYPERLIQUID_PERP"


@dataclass(frozen=True, slots=True)
class InstrumentSpec:
    """Canonical strategy identity and its venue-specific market symbol."""

    strategy_symbol: str
    venue: Venue
    venue_symbol: str


TRADE_CANDIDATES: Final[tuple[str, ...]] = (
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "LINKUSDT",
    "AVAXUSDT",
    "SUIUSDT",
    "HYPEUSDT",
    "ZECUSDT",
    "LITUSDT",
    "PUMP",
    "AAVEUSDT",
    "NEARUSDT",
    "XMRUSDT",
    "TAOUSDT",
    "ENAUSDT",
    "WLDUSDT",
    "FARTCOINUSDT",
    "JTOUSDT",
    "INJUSDT",
    "UNIUSDT",
    "ONDOUSDT",
    "GRASSUSDT",
)

BENCHMARK_SYMBOL: Final[str] = "BTCUSDT"


def _binance_instrument(symbol: str) -> InstrumentSpec:
    base = symbol.removesuffix("USDT")
    return InstrumentSpec(
        strategy_symbol=symbol,
        venue=Venue.BINANCE_FUTURES,
        venue_symbol=f"{base}/USDT:USDT",
    )


_INSTRUMENTS = {
    symbol: _binance_instrument(symbol)
    for symbol in TRADE_CANDIDATES
    if symbol != "PUMP"
}
_INSTRUMENTS["PUMP"] = InstrumentSpec(
    strategy_symbol="PUMP",
    venue=Venue.HYPERLIQUID_PERP,
    venue_symbol="PUMP/USDC:USDC",
)

INSTRUMENTS: Final = MappingProxyType(_INSTRUMENTS)
VENUE_BY_SYMBOL: Final = MappingProxyType(
    {symbol: spec.venue for symbol, spec in _INSTRUMENTS.items()}
)
BINANCE_TRADE_CANDIDATES: Final[tuple[str, ...]] = tuple(
    symbol for symbol in TRADE_CANDIDATES if VENUE_BY_SYMBOL[symbol] is Venue.BINANCE_FUTURES
)
HYPERLIQUID_TRADE_CANDIDATES: Final[tuple[str, ...]] = ("PUMP",)
BTC_BENCHMARK: Final[InstrumentSpec] = _binance_instrument(BENCHMARK_SYMBOL)


def instrument_for_symbol(symbol: str) -> InstrumentSpec:
    """Return the locked venue identity for a trade candidate.

    The lookup is intentionally exact and case-sensitive.  Normalizing symbols
    at this layer could conflate a strategy symbol with a venue instrument.
    """

    try:
        return INSTRUMENTS[symbol]
    except KeyError as exc:
        raise ValueError(f"{symbol!r} is not a Core V2.1 trade candidate") from exc


@dataclass(frozen=True, slots=True)
class CoreV21Config:
    """Non-overridable Core V2.1 signal parameters."""

    signal_timeframe: str = field(default="15m", init=False)
    alt_confirmation_timeframe: str = field(default="1h", init=False)
    btc_regime_timeframe: str = field(default="1h", init=False)
    btc_alignment_timeframe: str = field(default="4h", init=False)
    price_ema_period: int = field(default=21, init=False)
    trend_ema_period: int = field(default=200, init=False)
    ema_slope_lookback: int = field(default=3, init=False)
    atr_period: int = field(default=14, init=False)
    rsi_period: int = field(default=21, init=False)
    rsi_fast_ema_period: int = field(default=9, init=False)
    rsi_slow_wma_period: int = field(default=45, init=False)
    rsi_threshold: Decimal = field(default=Decimal("50"), init=False)
    maximum_distance_atr: Decimal = field(default=Decimal("1.0"), init=False)
    maximum_signal_range_atr: Decimal = field(default=Decimal("1.5"), init=False)
    pullback_atr_fraction: Decimal = field(default=Decimal("0.25"), init=False)
    wait_candles: int = field(default=4, init=False)
    stop_atr_fraction: Decimal = field(default=Decimal("0.25"), init=False)
    take_profit_r_multiples: tuple[Decimal, Decimal, Decimal] = field(
        default=(Decimal("1"), Decimal("2"), Decimal("3")),
        init=False,
    )


LOCKED_CONFIG: Final[CoreV21Config] = CoreV21Config()
