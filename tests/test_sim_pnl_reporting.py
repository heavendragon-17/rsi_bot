# tests/test_sim_pnl_reporting.py
"""
Regression tests for sim-mode PnL/SL reporting bugs observed in live Telegram
logs (ChatExport 2026-04-19):

* ``initial_risk`` was computed against the *disaster* stop_market trigger
  rather than the soft-SL the position was actually sized for, making every
  TP R-multiple ~1/3 of the real value.
* ``exit_reason`` returned ``HARD_SL`` for any stop_market fill, even when the
  SL had been moved to lock-profit above entry — so a trailing-profit exit
  was mislabelled as a stop-out.
* No liquidation check in sim: adverse leveraged moves drove balance below
  zero and the bot kept opening new orders.
"""

from __future__ import annotations

import time
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.trading.exchange.sim.sim_exchange import SimExchange
from app.trading.exchange.sim.sim_state import SimTradeState


def _config(balance: float = 10_000) -> dict:
    return {
        "bot": {"mode": "sim"},
        "sim": {"initial_balance": balance, "telegram_token": ""},
        "risk": {"leverage": 10},
    }


def _make_exchange(balance: float = 10_000) -> SimExchange:
    ex = SimExchange.__new__(SimExchange)
    ex._config = _config(balance)
    ex._last_prices = {}
    ex._sim_time = None
    ex.state = SimTradeState(Decimal(str(balance)))
    ex._notification_service = MagicMock()
    return ex


def _open_long(ex: SimExchange, *, symbol: str, entry: str, amount: str) -> None:
    """Place and fill a market BUY at *entry*."""
    ex._last_prices[symbol] = Decimal(entry)
    ex.create_order(symbol, "market", "BUY", Decimal(amount))


def _place_hard_sl(
    ex: SimExchange,
    *,
    symbol: str,
    stop_price: str,
    amount: str,
    soft_sl_price: str | None = None,
) -> str:
    """Place the disaster stop_market SL and return its order id."""
    params: dict = {"stopPrice": Decimal(stop_price), "reduceOnly": True}
    if soft_sl_price is not None:
        params["soft_sl_price"] = Decimal(soft_sl_price)
    order = ex.create_order(symbol, "stop_market", "SELL", Decimal(amount), params=params)
    return order["id"]


def _place_tp(ex: SimExchange, *, symbol: str, price: str, amount: str) -> str:
    order = ex.create_order(
        symbol,
        "limit",
        "SELL",
        Decimal(amount),
        price=Decimal(price),
        params={"reduceOnly": True, "exit_reason": "TP1"},
    )
    return order["id"]


# ---------------------------------------------------------------------------
# 1. initial_risk must use the soft SL (sizing risk), not the disaster trigger
# ---------------------------------------------------------------------------


class TestInitialRiskReflectsSoftSL:
    def test_soft_sl_used_when_provided(self):
        """With a 1% soft SL and 3% disaster stop, initial_risk = |entry-soft_sl|×amount."""
        ex = _make_exchange()
        _open_long(ex, symbol="BTC/USDT", entry="100.0", amount="10")
        _place_hard_sl(
            ex,
            symbol="BTC/USDT",
            stop_price="97.0",  # 3% disaster SL
            amount="10",
            soft_sl_price="99.0",  # 1% soft SL
        )
        pos = ex.state.positions["BTC/USDT"]
        # Should reflect soft SL (1.0 * 10 = 10), not disaster (3.0 * 10 = 30)
        assert pos.initial_risk == Decimal("10.0")

    def test_falls_back_to_stop_price_without_soft_sl(self):
        """Single-SL strategies must still get a sensible initial_risk."""
        ex = _make_exchange()
        _open_long(ex, symbol="BTC/USDT", entry="100.0", amount="10")
        _place_hard_sl(ex, symbol="BTC/USDT", stop_price="98.0", amount="10")
        pos = ex.state.positions["BTC/USDT"]
        assert pos.initial_risk == Decimal("20.0")  # |100-98| * 10

    def test_r_multiple_at_tp_is_one_for_1to1(self):
        """
        Fee-aware TP price for rr=1.0 + soft SL at 1% below entry should report
        r_multiple very close to 1.0, with pnl_net equal to the true lifecycle
        net (gross − entry taker fee − exit maker fee).
        """
        from app.trading.strategy.rsi_no_retest_entry import compute_price_at_rr

        ex = _make_exchange()
        entry = Decimal("100.0")
        soft_sl = Decimal("99.0")
        amount = Decimal("100")  # risk = $100

        taker = Decimal("0.0005")
        maker = Decimal("0.0002")
        tp_price = compute_price_at_rr(entry, soft_sl, Decimal("1.0"), taker, maker, is_taker_exit=False)

        _open_long(ex, symbol="BTC/USDT", entry=str(entry), amount=str(amount))
        _place_hard_sl(
            ex,
            symbol="BTC/USDT",
            stop_price="97.0",
            amount=str(amount),
            soft_sl_price=str(soft_sl),
        )
        _place_tp(ex, symbol="BTC/USDT", price=str(tp_price), amount=str(amount))

        ex.on_tick("BTC/USDT", tp_price, time.time())

        trade = ex.state.closed_trades[-1]
        assert trade.exit_reason == "TP1"
        # True net profit at 1.0 R ≈ $100; R ≈ 1.0 exactly.
        assert abs(trade.pnl_net - Decimal("100")) < Decimal("0.05")
        assert abs(trade.r_multiple - Decimal("1.0")) < Decimal("0.005")


# ---------------------------------------------------------------------------
# 2. Moved SL must be distinguished from original HARD_SL
# ---------------------------------------------------------------------------


class TestMovedSLExitReason:
    def test_initial_hard_sl_hit_reports_hard_sl(self):
        ex = _make_exchange()
        _open_long(ex, symbol="BTC/USDT", entry="100.0", amount="10")
        _place_hard_sl(
            ex,
            symbol="BTC/USDT",
            stop_price="97.0",
            amount="10",
            soft_sl_price="99.0",
        )
        ex.on_tick("BTC/USDT", Decimal("97.0"), time.time())
        trade = ex.state.closed_trades[-1]
        assert trade.exit_reason == "HARD_SL"
        assert trade.pnl_gross < Decimal("0")

    def test_moved_sl_replaces_hard_sl_label(self):
        """Any stop_market fill after the SL has been relocated reports MOVED_SL.

        By construction the strategy only moves the SL to a lock-profit level,
        so such fills are always in profit — we don't need a separate label.
        """
        ex = _make_exchange()
        _open_long(ex, symbol="BTC/USDT", entry="100.0", amount="10")
        _place_hard_sl(
            ex,
            symbol="BTC/USDT",
            stop_price="97.0",
            amount="10",
            soft_sl_price="99.0",
        )
        # Simulate lock-profit: cancel old SL and place a new one above entry
        old_sl_id = ex.state.positions["BTC/USDT"].sl_order_id
        ex.cancel_order(old_sl_id, "BTC/USDT")
        _place_hard_sl(
            ex,
            symbol="BTC/USDT",
            stop_price="100.5",  # above entry — locks profit
            amount="10",
        )
        pos = ex.state.positions["BTC/USDT"]
        assert pos.moved_sl is True

        ex.on_tick("BTC/USDT", Decimal("100.5"), time.time())
        trade = ex.state.closed_trades[-1]
        assert trade.exit_reason == "MOVED_SL"
        assert trade.pnl_gross > Decimal("0")

    def test_moved_sl_at_0_2r_reports_close_to_0_2r(self):
        """
        Lock-profit SL priced by ``compute_price_at_rr(rr=0.2)`` — which targets
        0.2R *net of entry + exit taker fees* — must report ≈ 0.2R when it hits.
        Also locks the displayed ``pnl_net`` to the true lifecycle net, so the
        Telegram "Net P&L" line matches what the balance actually gained.
        """
        from app.trading.strategy.rsi_no_retest_entry import compute_price_at_rr

        ex = _make_exchange()
        entry = Decimal("100.0")
        soft_sl = Decimal("99.0")      # 1% soft SL; R-per-unit = $1
        disaster_sl = Decimal("97.0")  # 3× soft; where the original stop_market sits
        amount = Decimal("100")        # risk = 1 × 100 = $100 → 0.2R = $20

        taker = Decimal("0.0005")
        maker = Decimal("0.0002")
        lock_profit_price = compute_price_at_rr(
            entry, soft_sl, Decimal("0.2"), taker, maker, is_taker_exit=True
        )

        _open_long(ex, symbol="BTC/USDT", entry=str(entry), amount=str(amount))
        _place_hard_sl(
            ex,
            symbol="BTC/USDT",
            stop_price=str(disaster_sl),
            amount=str(amount),
            soft_sl_price=str(soft_sl),
        )
        # MoveSL: cancel disaster, place the fee-aware lock-profit stop
        old_sl_id = ex.state.positions["BTC/USDT"].sl_order_id
        ex.cancel_order(old_sl_id, "BTC/USDT")
        _place_hard_sl(
            ex,
            symbol="BTC/USDT",
            stop_price=str(lock_profit_price),
            amount=str(amount),
        )
        ex.on_tick("BTC/USDT", lock_profit_price, time.time())

        trade = ex.state.closed_trades[-1]
        # True net profit should be ~0.2 × $100 risk = $20, and R ≈ 0.20.
        assert trade.exit_reason == "MOVED_SL"
        assert abs(trade.pnl_net - Decimal("20")) < Decimal("0.05")
        assert abs(trade.r_multiple - Decimal("0.20")) < Decimal("0.005")

    def test_moved_sl_even_at_breakeven_uses_moved_sl_label(self):
        """Even the edge case of SL moved exactly to entry reports MOVED_SL."""
        ex = _make_exchange()
        _open_long(ex, symbol="BTC/USDT", entry="100.0", amount="10")
        _place_hard_sl(
            ex,
            symbol="BTC/USDT",
            stop_price="97.0",
            amount="10",
            soft_sl_price="99.0",
        )
        old_sl_id = ex.state.positions["BTC/USDT"].sl_order_id
        ex.cancel_order(old_sl_id, "BTC/USDT")
        _place_hard_sl(
            ex,
            symbol="BTC/USDT",
            stop_price="100.0",  # break-even
            amount="10",
        )
        ex.on_tick("BTC/USDT", Decimal("100.0"), time.time())
        trade = ex.state.closed_trades[-1]
        assert trade.exit_reason == "MOVED_SL"


# ---------------------------------------------------------------------------
# 3. Liquidation: force-close all positions when equity ≤ 0
# ---------------------------------------------------------------------------


class TestLiquidation:
    def test_equity_below_zero_triggers_force_close(self):
        """At 10× leverage, a ~10% adverse move wipes out a full balance."""
        ex = _make_exchange(100)  # tiny balance to liquidate quickly
        _open_long(ex, symbol="BTC/USDT", entry="100.0", amount="200")
        # Unrealized PnL = (50-100)*200 = -10_000 → equity = 100 - 10_000 ≪ 0
        ex.on_tick("BTC/USDT", Decimal("50.0"), time.time())
        assert "BTC/USDT" not in ex.state.positions
        assert ex.state.balance == Decimal("0")
        assert ex.state.is_paused is True

    def test_paused_exchange_rejects_new_entries(self):
        ex = _make_exchange(100)
        _open_long(ex, symbol="BTC/USDT", entry="100.0", amount="200")
        ex.on_tick("BTC/USDT", Decimal("50.0"), time.time())
        assert ex.state.is_paused is True
        # New entry attempts must be rejected
        order = ex.create_order("ETH/USDT", "market", "BUY", Decimal("1"))
        assert order is None


# ---------------------------------------------------------------------------
# 4. Zero-size / non-positive orders must be rejected
# ---------------------------------------------------------------------------


class TestDispatcherPassesBothSLs:
    """Dispatcher forwards hard and soft SL separately so the card can show both."""

    def _dispatch(self, signal, balance=Decimal("10000")):
        from unittest.mock import MagicMock

        from app.trading.portfolio.notification_dispatch import NotificationDispatcher

        notif = MagicMock()
        exchange = MagicMock()
        exchange._fires_entry_notification = False
        NotificationDispatcher(notif, exchange).notify_entry(
            symbol="BTC/USDT",
            entry_side="BUY",
            price=Decimal("100.0"),
            amount=Decimal("10"),
            signal=signal,
            leverage=10,
            balance=balance,
        )
        return notif.on_entry.call_args.kwargs

    def test_dual_sl_both_passed(self):
        from unittest.mock import MagicMock

        signal = MagicMock()
        signal.sl_price = Decimal("97.0")
        signal.soft_sl_price = Decimal("99.0")
        signal.tp1_price = Decimal("101.0")
        signal.tp2_price = None
        signal.tp3_price = None
        signal.indicators = None

        kwargs = self._dispatch(signal)
        assert kwargs["sl_price"] == Decimal("97.0")
        assert kwargs["soft_sl_price"] == Decimal("99.0")
        assert kwargs["tp_prices"] == {"TP1": Decimal("101.0")}

    def test_single_sl_only_hard(self):
        from unittest.mock import MagicMock

        signal = MagicMock()
        signal.sl_price = Decimal("97.0")
        signal.soft_sl_price = None
        signal.tp1_price = None
        signal.tp2_price = None
        signal.tp3_price = None
        signal.indicators = None

        kwargs = self._dispatch(signal)
        assert kwargs["sl_price"] == Decimal("97.0")
        assert kwargs["soft_sl_price"] is None


class TestZeroSizeGuards:
    def test_zero_amount_entry_rejected(self):
        ex = _make_exchange()
        ex._last_prices["BTC/USDT"] = Decimal("100")
        order = ex.create_order("BTC/USDT", "market", "BUY", Decimal("0"))
        assert order is None
        assert "BTC/USDT" not in ex.state.positions

    def test_negative_amount_entry_rejected(self):
        ex = _make_exchange()
        ex._last_prices["BTC/USDT"] = Decimal("100")
        order = ex.create_order("BTC/USDT", "market", "BUY", Decimal("-1"))
        assert order is None
