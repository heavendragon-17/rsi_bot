"""Virtual positions + in-memory store for the signal bot.

A :class:`VirtualPosition` is the signal bot's equivalent of a live position:
it records the entry/SL/TP levels the strategy emitted so the exit monitor
can advise on closes. No capital is committed; only messages are produced.

The store is thread-safe and holds **one VP per (strategy_name, symbol)**
per spec §6. State transitions return new frozen records so callers can
safely share references.
"""

from __future__ import annotations

import dataclasses
import threading
from dataclasses import dataclass, field
from decimal import Decimal


class VPNotFoundError(LookupError):
    """Raised when a VP lookup fails in the store."""


@dataclass(frozen=True)
class VirtualPosition:
    """Snapshot of a virtual position. Immutable — mutators return new records."""

    signal_id: str
    strategy_name: str
    symbol: str
    side: str  # "LONG" | "SHORT"
    entry_price: Decimal
    sl_price: Decimal
    tp_levels: tuple[Decimal, ...]
    tp_close_pcts: tuple[float, ...]
    opened_at_candle_ts: int  # unix ms of the candle the entry fired on
    timeframe: str
    tp_hits: frozenset[int] = field(default_factory=frozenset)


def derive_id_prefix(strategy_name: str) -> str:
    """Derive a short human-readable prefix for signal ids.

    Rule (v1): strip underscores, uppercase, take first 4 chars. 4 (not 3)
    because every current ``STRATEGY_MAP`` entry starts with ``rsi_``; a
    3-char prefix would collapse them all to ``RSI``. Explicit per-strategy
    override is tracked in spec §15 for a future slice.
    """
    return strategy_name.replace("_", "").upper()[:4]


class VirtualPositionStore:
    """Thread-safe in-memory VP store, scoped per strategy via strategy_name.

    **Concurrency contract (v1):** one writer per ``strategy_name`` —
    spec §16 pins thread-per-strategy, so every write for a given strategy
    originates from a single worker thread. Individual operations are
    atomic under ``self._lock``, but callers MUST NOT interleave reads and
    writes for the same key across threads (there is no CAS primitive).
    Cross-strategy concurrent access (e.g. the shutdown broadcaster
    reading ``all_open_by_strategy`` while workers mutate) is safe.
    """

    def __init__(self) -> None:
        self._vps: dict[tuple[str, str], VirtualPosition] = {}
        self._counters: dict[str, int] = {}
        self._lock = threading.Lock()

    def next_signal_id(self, strategy_name: str) -> str:
        """Return the next monotonic signal id for ``strategy_name``."""
        prefix = derive_id_prefix(strategy_name)
        with self._lock:
            count = self._counters.get(strategy_name, 0) + 1
            self._counters[strategy_name] = count
        return f"{prefix}#{count:03d}"

    def open(self, vp: VirtualPosition) -> None:
        """Register a new VP. Raises ``ValueError`` if one is already open
        for ``(strategy_name, symbol)``."""
        key = (vp.strategy_name, vp.symbol)
        with self._lock:
            if key in self._vps:
                raise ValueError(
                    f"VP already open for strategy={vp.strategy_name} symbol={vp.symbol}; "
                    "one VP per (strategy, symbol) in v1"
                )
            self._vps[key] = vp

    def close(self, strategy_name: str, symbol: str) -> VirtualPosition | None:
        """Remove and return the VP. Returns ``None`` when none is open."""
        key = (strategy_name, symbol)
        with self._lock:
            return self._vps.pop(key, None)

    def update_sl(
        self, strategy_name: str, symbol: str, new_sl: Decimal
    ) -> VirtualPosition:
        """Replace the stored VP with an SL-updated copy; return the copy.

        Raises ``KeyError`` if no VP is open.
        """
        key = (strategy_name, symbol)
        with self._lock:
            existing = self._vps.get(key)
            if existing is None:
                raise VPNotFoundError(
                    f"no open VP for strategy={strategy_name} symbol={symbol}"
                )
            updated = dataclasses.replace(existing, sl_price=new_sl)
            self._vps[key] = updated
            return updated

    def mark_tp_hit(
        self, strategy_name: str, symbol: str, tp_index: int
    ) -> VirtualPosition:
        """Record that ``tp_index`` has been hit; return the updated VP.

        Raises ``KeyError`` if no VP is open. No-op (but still returns the VP)
        if ``tp_index`` was already in ``tp_hits``.
        """
        key = (strategy_name, symbol)
        with self._lock:
            existing = self._vps.get(key)
            if existing is None:
                raise VPNotFoundError(
                    f"no open VP for strategy={strategy_name} symbol={symbol}"
                )
            updated = dataclasses.replace(
                existing, tp_hits=existing.tp_hits | {tp_index}
            )
            self._vps[key] = updated
            return updated

    def get_for_symbol(
        self, strategy_name: str, symbol: str
    ) -> VirtualPosition | None:
        with self._lock:
            return self._vps.get((strategy_name, symbol))

    def all_open(self, strategy_name: str) -> list[VirtualPosition]:
        with self._lock:
            return [vp for (s, _), vp in self._vps.items() if s == strategy_name]

    def all_open_by_strategy(self) -> dict[str, list[VirtualPosition]]:
        """Snapshot of all open VPs grouped by strategy — for shutdown broadcast."""
        grouped: dict[str, list[VirtualPosition]] = {}
        with self._lock:
            for (strategy_name, _), vp in self._vps.items():
                grouped.setdefault(strategy_name, []).append(vp)
        return grouped
