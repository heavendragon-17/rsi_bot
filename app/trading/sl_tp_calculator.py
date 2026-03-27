# app/core/sl_tp_calculator.py
"""
Modular SL/TP calculator — static utility module.

All methods are direction-aware (LONG/SHORT) via a `side` parameter.
Extracted and generalised from rsi_no_retest._compute_price_at_rr()
and PortfolioManager._calculate_position_size().
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd

from app.core.actions import SIDE_BUY


class SLTPCalculator:
    """Static utility class for SL/TP/sizing calculations."""

    @staticmethod
    def compute_soft_sl(
        df: pd.DataFrame,
        side: str,
        lookback: int = 30,
        mode: str = "swing",
        current_index: int | None = None,
    ) -> Decimal | None:
        """
        Compute the soft stop-loss price from recent price history.

        LONG  (BUY):  lowest low of the last `lookback` candles
        SHORT (SELL): highest high of the last `lookback` candles

        Args:
            df:            OHLCV DataFrame (must contain 'high' and 'low' columns).
            side:          "BUY" for long, "SELL" for short.
            lookback:      Number of candles to look back (default 30).
            mode:          "swing" uses high/low wicks; "close" uses close prices.
            current_index: Absolute row index (backtest). None = use last rows.

        Returns:
            SL price as Decimal, or None if insufficient data.
        """
        idx = current_index if current_index is not None else (len(df) - 1 if df is not None else -1)
        eff_len = idx + 1
        if df is None or eff_len < lookback:
            return None

        window = df.iloc[idx - lookback + 1 : idx + 1]

        try:
            if side.upper() == SIDE_BUY:
                if mode == "close":
                    val = window["close"].min()
                else:
                    val = window["low"].min()
            else:  # SELL / SHORT
                if mode == "close":
                    val = window["close"].max()
                else:
                    val = window["high"].max()

            if pd.isna(val):
                return None
            return Decimal(str(val))
        except (KeyError, TypeError, ValueError):
            return None

    @staticmethod
    def compute_disaster_sl(
        entry_price: Decimal,
        soft_sl_price: Decimal,
        side: str,
        multiplier: Decimal = Decimal("3.0"),
    ) -> Decimal:
        """
        Hard disaster SL placed further out than the soft SL.

        LONG  (BUY):  entry - (entry - soft_sl) * multiplier
        SHORT (SELL): entry + (soft_sl - entry) * multiplier

        Args:
            entry_price:   Trade entry price.
            soft_sl_price: The soft (candle-close) SL level.
            side:          "BUY" for long, "SELL" for short.
            multiplier:    How many times further the disaster SL sits (default 3×).

        Returns:
            Disaster SL price as Decimal.
        """
        if side.upper() == SIDE_BUY:
            distance = entry_price - soft_sl_price
            return entry_price - (distance * multiplier)
        else:
            distance = soft_sl_price - entry_price
            return entry_price + (distance * multiplier)

    @staticmethod
    def compute_tp_price(
        entry_price: Decimal,
        sl_price: Decimal,
        side: str,
        rr_ratio: Decimal,
        taker_fee: Decimal = Decimal("0"),
        exit_fee: Decimal = Decimal("0"),
    ) -> Decimal | None:
        """
        Fee-aware TP calculation.

        Derivation (using gross profit formula before fees):
          Net Profit = exit - entry - entry * taker_fee - exit * exit_fee
          Target net profit = rr_ratio * |entry - sl|
          exit * (1 - exit_fee) = entry * (1 + taker_fee) + rr_ratio * risk  (LONG)
          exit * (1 - exit_fee) = entry * (1 - taker_fee) - rr_ratio * risk  (SHORT)

        LONG  (BUY):  TP is above entry
        SHORT (SELL): TP is below entry

        Args:
            entry_price: Entry price.
            sl_price:    Stop-loss price (used to compute risk distance).
            side:        "BUY" for long, "SELL" for short.
            rr_ratio:    Risk:reward multiplier (e.g. Decimal("1.0") for 1:1).
            taker_fee:   Entry taker fee rate (e.g. Decimal("0.0005")).
            exit_fee:    Exit fee rate (maker for limit TP, taker for market).

        Returns:
            TP price as Decimal, or None if risk distance is zero.
        """
        risk = abs(entry_price - sl_price)
        if risk <= Decimal("0"):
            return None

        target_net = rr_ratio * risk
        denominator = Decimal("1") - exit_fee

        if side.upper() == SIDE_BUY:
            numerator = entry_price * (Decimal("1") + taker_fee) + target_net
        else:
            numerator = entry_price * (Decimal("1") - taker_fee) - target_net

        if denominator == Decimal("0"):
            return None

        return numerator / denominator

    @staticmethod
    def compute_lock_profit_price(
        entry_price: Decimal,
        soft_sl_price: Decimal,
        side: str,
        lock_profit_rr: Decimal,
        taker_fee: Decimal = Decimal("0"),
    ) -> Decimal | None:
        """
        Price at which to move the SL to lock-in profit after TP1 fills.

        LONG  (BUY):  SL moves above entry (locks profit if price drops back).
        SHORT (SELL): SL moves below entry (locks profit if price rises back).

        Args:
            entry_price:    Entry price.
            soft_sl_price:  Original soft SL (used as risk distance reference).
            side:           "BUY" for long, "SELL" for short.
            lock_profit_rr: R-multiple to lock in (e.g. Decimal("0.2") for 0.2R).
            taker_fee:      Fee rate for the SL trigger (stop_market → taker).

        Returns:
            Lock-profit SL price as Decimal, or None if risk is zero.
        """
        return SLTPCalculator.compute_tp_price(
            entry_price=entry_price,
            sl_price=soft_sl_price,
            side=side,
            rr_ratio=lock_profit_rr,
            taker_fee=taker_fee,
            exit_fee=taker_fee,  # stop_market fills as taker
        )

    @staticmethod
    def compute_position_size(
        entry_price: Decimal,
        sl_price: Decimal,
        risk_capital: Decimal,
        risk_per_trade_pct: Decimal,
        leverage: Decimal,
    ) -> Decimal:
        """
        Risk-based position sizing (direction-agnostic — uses absolute distance).

        Formula:
            risk_amount       = risk_capital * risk_per_trade_pct
            sl_distance_pct   = |entry - sl| / entry
            position_notional = risk_amount / sl_distance_pct
            position_size     = position_notional / entry_price

        Args:
            entry_price:       Entry price.
            sl_price:          Stop-loss price.
            risk_capital:      Capital base for risk calculation.
            risk_per_trade_pct: Fraction of capital to risk (e.g. Decimal("0.02")).
            leverage:          Exchange leverage multiplier (informational — not used
                               in size computation; caller must cap by margin).

        Returns:
            Position size (base units) as Decimal. Returns 0 if SL == entry.
        """
        sl_distance = abs(entry_price - sl_price)
        if sl_distance <= Decimal("0") or entry_price <= Decimal("0"):
            return Decimal("0")

        sl_distance_pct = sl_distance / entry_price
        risk_amount = risk_capital * risk_per_trade_pct
        position_notional = risk_amount / sl_distance_pct
        return position_notional / entry_price
