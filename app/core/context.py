from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Any
from datetime import datetime


# =================================================
# State machine phases for each (symbol, timeframe)
# =================================================
SCANNING = "SCANNING"
RETESTING = "RETESTING"
CONFIRMING = "CONFIRMING"
WAITING = "WAITING"


def _to_epoch_seconds(now_ts: Optional[Any]) -> float:
    """
    Convert now_ts into epoch seconds.

    Accepts:
      - None -> real time (live trading)
      - datetime -> convert to epoch seconds
      - pandas.Timestamp -> convert to datetime (via .to_pydatetime())
      - int/float epoch seconds
      - int epoch milliseconds (13 digits)
    """
    if now_ts is None:
        return time.time()

    # pandas.Timestamp -> datetime
    try:
        import pandas as pd
        if isinstance(now_ts, pd.Timestamp):
            now_ts = now_ts.to_pydatetime()
    except Exception:
        pass

    if isinstance(now_ts, datetime):
        return now_ts.timestamp()

    if isinstance(now_ts, (int, float)):
        v = float(now_ts)
        if v > 10_000_000_000:  # likely ms
            return v / 1000.0
        return v

    try:
        v = float(now_ts)
        if v > 10_000_000_000:
            return v / 1000.0
        return v
    except Exception:
        return time.time()


def timeframe_to_seconds(tf: str) -> int:
    """
    Convert timeframe string like '5m', '1h' to seconds.
    """
    tf = (tf or "").strip().lower()
    if not tf:
        return 60

    unit = tf[-1]
    try:
        value = int(tf[:-1])
    except Exception:
        return 60

    if unit == "m":
        return value * 60
    if unit == "h":
        return value * 3600
    if unit == "d":
        return value * 86400

    # fallback
    return 60


@dataclass
class SymbolState:
    """
    Holds the state machine data for one (symbol, timeframe).
    Example key: "BTC/USDT:5m"
    """
    phase: str = SCANNING

    # Cooldown / anti-spam (uses epoch seconds from candle time in backtests)
    last_alert_ts: float = 0.0

    # Debug / tracking
    last_transition_ts: float = 0.0
    retest_touched_ts: Optional[Any] = None  # keep as Any to support datetime/int

    # WAITING (cooldown between signals)
    waiting_until_ts: float = 0.0

    # SL lock (prevents immediate re-entry after stoploss)
    sl_lock_until_ts: float = 0.0

    last_reason: str = ""


@dataclass
class ActiveTrade:
    """
    Represents an active trade/position for a symbol.
    """
    symbol: str
    timeframe: str
    side: str
    entry_ts: float
    entry_price: Optional[float] = None
    qty: Optional[float] = None
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyContext:
    """
    Holds:
      - State machines for all symbols
      - Active trades information
    """
    states: Dict[str, SymbolState] = field(default_factory=dict)
    active_trades: Dict[str, ActiveTrade] = field(default_factory=dict)

    def get_state(self, key: str) -> SymbolState:
        if key not in self.states:
            self.states[key] = SymbolState()
        return self.states[key]

    def transition(self, key: str, new_phase: str, reason: str = "", now_ts: Optional[Any] = None) -> None:
        st = self.get_state(key)

        if st.phase != new_phase:
            st.phase = new_phase
            st.last_transition_ts = _to_epoch_seconds(now_ts)
            st.last_reason = reason

            # Reset per-cycle data when restarting the scan
            if new_phase == SCANNING:
                st.retest_touched_ts = None
                st.waiting_until_ts = 0.0
                # NOTE: we do NOT clear sl_lock here. SL lock must expire by time.

    # --------------------------
    # WAITING (cooldown)
    # --------------------------
    def set_waiting(self, key: str, seconds: int, reason: str = "", now_ts: Optional[Any] = None) -> None:
        st = self.get_state(key)
        now = _to_epoch_seconds(now_ts)
        st.waiting_until_ts = now + max(0, int(seconds))
        self.transition(key, WAITING, reason=reason or f"Waiting {seconds}s", now_ts=now_ts)

    def is_waiting(self, key: str, now_ts: Optional[Any] = None) -> bool:
        st = self.get_state(key)
        now = _to_epoch_seconds(now_ts)
        return st.phase == WAITING and now < st.waiting_until_ts

    def clear_waiting(self, key: str, now_ts: Optional[Any] = None) -> None:
        st = self.get_state(key)
        st.waiting_until_ts = 0.0
        self.transition(key, SCANNING, reason="Waiting finished", now_ts=now_ts)

    # --------------------------
    # COOLDOWN (anti-spam)
    # --------------------------
    def can_alert(self, key: str, cooldown_sec: int, now_ts: Optional[Any] = None) -> bool:
        st = self.get_state(key)
        now = _to_epoch_seconds(now_ts)
        return (now - st.last_alert_ts) >= int(cooldown_sec)

    def mark_alerted(self, key: str, now_ts: Optional[Any] = None) -> None:
        st = self.get_state(key)
        st.last_alert_ts = _to_epoch_seconds(now_ts)

    # --------------------------
    # SL LOCK (anti-chop re-entry)
    # --------------------------
    def set_sl_lock(self, key: str, timeframe: str, candles: int, now_ts: Optional[Any] = None) -> None:
        """
        Lock entries for `candles` candles after an SL.
        For 5m, candles=12 => 60 minutes lock.
        """
        st = self.get_state(key)
        now = _to_epoch_seconds(now_ts)
        tf_sec = timeframe_to_seconds(timeframe)
        st.sl_lock_until_ts = now + max(0, int(candles)) * tf_sec

    def is_sl_locked(self, key: str, now_ts: Optional[Any] = None) -> bool:
        st = self.get_state(key)
        now = _to_epoch_seconds(now_ts)
        return now < st.sl_lock_until_ts

    def clear_sl_lock(self, key: str) -> None:
        st = self.get_state(key)
        st.sl_lock_until_ts = 0.0

    # --------------------------
    # ACTIVE TRADES
    # --------------------------
    def has_active_trade(self, symbol: str) -> bool:
        return symbol in self.active_trades

    def open_trade(
        self,
        symbol: str,
        timeframe: str,
        side: str,
        entry_price: Optional[float] = None,
        qty: Optional[float] = None,
        meta: Optional[Dict[str, Any]] = None,
        now_ts: Optional[Any] = None,
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

    def get_trade(self, symbol: str) -> Optional[ActiveTrade]:
        return self.active_trades.get(symbol)
