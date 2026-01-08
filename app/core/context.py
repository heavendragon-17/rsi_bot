from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Any

# =================================================
# State machine phases for each (symbol, timeframe)
# =================================================
SCANNING = "SCANNING"        # Waiting for initial setup conditions
RETESTING = "RETESTING"      # Waiting for RSI to retest WMA45 without breaking RSI floor
CONFIRMING = "CONFIRMING"    # Waiting for candle close confirmation
WAITING = "WAITING"          # Signal/trade already triggered -> pause scanning


@dataclass
class SymbolState:
    """
    Holds the state machine data for one (symbol, timeframe).

    Example key:
        "BTC/USDT:1m"
    """

    # Current phase of the state machine
    phase: str = SCANNING

    # Timestamp of the last alert (used for cooldown)
    last_alert_ts: float = 0.0

    # Timestamp of the last state transition (useful for debugging / timeouts)
    last_transition_ts: float = 0.0

    # Candle timestamp when RSI touched the WMA45 zone
    # Used for debugging or advanced confirmation rules
    retest_touched_ts: Optional[int] = None

    # If in WAITING state, scanning is paused until this timestamp
    waiting_until_ts: float = 0.0

    # Optional reason for the last transition (debugging/logging)
    last_reason: str = ""


@dataclass
class ActiveTrade:
    """
    Represents an active trade/position for a symbol.

    Used to:
      - Prevent duplicate alerts
      - Lock a symbol while a trade is active
      - Track TP/SL levels for trade management
    """

    symbol: str
    timeframe: str
    side: str                    # "LONG" only (LONG only strategy)
    entry_ts: float              # time.time() when trade opened
    entry_price: Optional[float] = None
    qty: Optional[float] = None
    meta: Dict[str, Any] = field(default_factory=dict)
    
    # TP/SL prices from signal
    tp1_price: Optional[float] = None
    tp2_price: Optional[float] = None
    tp3_price: Optional[float] = None
    sl_price: Optional[float] = None


@dataclass
class StrategyContext:
    """
    Holds:
      - State machines for all symbols
      - Active trades information

    states:
        key   -> "BTC/USDT:1m"
        value -> SymbolState

    active_trades:
        key   -> "BTC/USDT"
        value -> ActiveTrade
    """

    states: Dict[str, SymbolState] = field(default_factory=dict)
    active_trades: Dict[str, ActiveTrade] = field(default_factory=dict)

    def get_state(self, key: str) -> SymbolState:
        """
        Get the state for a symbol.
        If it does not exist yet, create a new one in SCANNING phase.
        """
        if key not in self.states:
            self.states[key] = SymbolState()
        return self.states[key]

    def transition(self, key: str, new_phase: str, reason: str = "") -> None:
        """
        Transition a symbol to a new phase.
        Records transition time and optional reason.
        """
        st = self.get_state(key)

        if st.phase != new_phase:
            st.phase = new_phase
            st.last_transition_ts = time.time()
            st.last_reason = reason

            # Reset per-cycle data when restarting the scan
            if new_phase == SCANNING:
                st.retest_touched_ts = None
                st.waiting_until_ts = 0.0

    def set_waiting(self, key: str, seconds: int, reason: str = "") -> None:
        """
        Put a symbol into WAITING state for a fixed duration.
        During WAITING, the strategy should not scan or trigger signals.
        """
        st = self.get_state(key)
        st.waiting_until_ts = time.time() + max(0, int(seconds))
        self.transition(key, WAITING, reason=reason or f"Waiting {seconds}s")

    def is_waiting(self, key: str) -> bool:
        """
        Returns True if the symbol is currently in WAITING state
        and the waiting time has not expired yet.
        """
        st = self.get_state(key)
        return st.phase == WAITING and time.time() < st.waiting_until_ts

    def clear_waiting(self, key: str) -> None:
        """
        Exit WAITING state and resume scanning.
        """
        st = self.get_state(key)
        st.waiting_until_ts = 0.0
        self.transition(key, SCANNING, reason="Waiting finished")

    def can_alert(self, key: str, cooldown_sec: int) -> bool:
        """
        Returns True if enough time has passed since the last alert.
        Used to prevent alert spam.
        """
        st = self.get_state(key)
        return (time.time() - st.last_alert_ts) >= int(cooldown_sec)

    def mark_alerted(self, key: str) -> None:
        """
        Mark the symbol as having triggered an alert.
        """
        st = self.get_state(key)
        st.last_alert_ts = time.time()

    def has_active_trade(self, symbol: str) -> bool:
        """
        Check whether a symbol currently has an active trade.
        """
        return symbol in self.active_trades

    def open_trade(
        self,
        symbol: str,
        timeframe: str,
        side: str,
        entry_price: Optional[float] = None,
        qty: Optional[float] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Register a new active trade for a symbol.
        """
        self.active_trades[symbol] = ActiveTrade(
            symbol=symbol,
            timeframe=timeframe,
            side=side,
            entry_ts=time.time(),
            entry_price=entry_price,
            qty=qty,
            meta=meta or {},
        )

    def close_trade(self, symbol: str) -> None:
        """
        Remove an active trade (called when the trade is closed).
        """
        if symbol in self.active_trades:
            del self.active_trades[symbol]

    def get_trade(self, symbol: str) -> Optional[ActiveTrade]:
        """
        Get the active trade for a symbol, if any.
        """
        return self.active_trades.get(symbol)
