from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

# =================================================
# State machine phases for each (symbol, timeframe)
# =================================================
SCANNING = "SCANNING"
RETESTING = "RETESTING"
CONFIRMING = "CONFIRMING"


def _to_epoch_seconds(ts: Any | None) -> float:
    """
    Convert datetime / pandas Timestamp / epoch / None -> epoch seconds (float).
    If ts is None, fall back to time.time().
    """
    if ts is None:
        return time.time()

    # datetime / pandas Timestamp
    if hasattr(ts, "timestamp"):
        try:
            return float(ts.timestamp())
        except Exception:
            pass

    # numeric
    try:
        return float(ts)
    except Exception:
        return time.time()


@dataclass
class SymbolState:
    """
    Holds the state machine data for one (symbol, timeframe).
    Example key: "BTC/USDT:1h"
    """

    phase: str = SCANNING
    last_transition_ts: float = 0.0
    retest_touched_ts: Any | None = None
    last_reason: str = ""


@dataclass
class ActiveTrade:
    """
    Represents an active trade/position for a symbol.
    Used only to prevent duplicate entries while a trade is open.
    """

    symbol: str
    timeframe: str
    side: str
    entry_ts: float
    entry_price: float | None = None
    qty: float | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyContext:
    """
    Holds:
      - State machines for all symbols
      - Active trades information
    """

    states: dict[str, SymbolState] = field(default_factory=dict)
    active_trades: dict[str, ActiveTrade] = field(default_factory=dict)

    def get_state(self, key: str) -> SymbolState:
        if key not in self.states:
            self.states[key] = SymbolState()
        return self.states[key]

    def transition(self, key: str, new_phase: str, reason: str = "", now_ts: Any | None = None) -> None:
        st = self.get_state(key)
        if st.phase != new_phase:
            st.phase = new_phase
            st.last_transition_ts = _to_epoch_seconds(now_ts)
            st.last_reason = reason
            if new_phase == SCANNING:
                st.retest_touched_ts = None

    def has_active_trade(self, symbol: str) -> bool:
        return symbol in self.active_trades

    def open_trade(
        self,
        symbol: str,
        timeframe: str,
        side: str,
        entry_price: float | None = None,
        qty: float | None = None,
        meta: dict[str, Any] | None = None,
        now_ts: Any | None = None,
    ) -> None:
        self.active_trades[symbol] = ActiveTrade(
            symbol=symbol,
            timeframe=timeframe,
            side=side,
            entry_ts=_to_epoch_seconds(now_ts),
            entry_price=entry_price,
            qty=qty,
            meta=meta or {},
        )

    def close_trade(self, symbol: str) -> None:
        self.active_trades.pop(symbol, None)

    def get_trade(self, symbol: str) -> ActiveTrade | None:
        return self.active_trades.get(symbol)
