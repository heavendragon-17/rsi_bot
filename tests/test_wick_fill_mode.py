"""Unit tests for WickFillMode trigger logic."""

from decimal import Decimal

from app.trading.exchange.fill_simulator import PendingOrder
from app.trading.exchange.wick_fill_mode import WickFillMode


def _order(side, order_type, trigger=None, limit=None, price=None, oid="o1"):
    return PendingOrder(
        id=oid,
        symbol="BTC",
        order_type=order_type,
        side=side,
        amount=Decimal("1"),
        price=Decimal(str(price)) if price is not None else None,
        trigger_price=Decimal(str(trigger)) if trigger is not None else None,
        limit_price=Decimal(str(limit)) if limit is not None else None,
    )


def _check(mode, orders, high, low):
    return mode.check_fills(orders, {"high": Decimal(str(high)), "low": Decimal(str(low))})


class TestWickFillPython:
    def setup_method(self):
        self.mode = WickFillMode()
        # Force python path by clearing JIT flag
        import app.trading.exchange.wick_fill_mode as mod
        self._orig = mod._HAS_JIT_FILLS
        mod._HAS_JIT_FILLS = False

    def teardown_method(self):
        import app.trading.exchange.wick_fill_mode as mod
        mod._HAS_JIT_FILLS = self._orig

    def test_empty_orders_returns_empty(self):
        assert self.mode.check_fills([], {"high": Decimal("1"), "low": Decimal("1")}) == []

    def test_sell_stop_market_triggered_when_low_hits(self):
        # SELL stop_market (SL for long): low <= trigger
        order = _order("SELL", "stop_market", trigger=100)
        fills = _check(self.mode, [order], high=110, low=99)
        assert len(fills) == 1
        assert fills[0][1] == Decimal("100")

    def test_sell_stop_market_not_triggered_when_low_high(self):
        order = _order("SELL", "stop_market", trigger=100)
        fills = _check(self.mode, [order], high=110, low=105)
        assert fills == []

    def test_sell_limit_triggered_when_high_hits(self):
        # SELL limit (TP for long): high >= price
        order = _order("SELL", "limit", price=120)
        fills = _check(self.mode, [order], high=125, low=110)
        assert len(fills) == 1
        assert fills[0][1] == Decimal("120")

    def test_sell_stop_limit_fills_at_limit_price(self):
        order = _order("SELL", "stop_limit", trigger=100, limit=95)
        fills = _check(self.mode, [order], high=110, low=99)
        assert fills[0][1] == Decimal("95")

    def test_buy_limit_triggered_when_low_hits(self):
        # BUY limit (TP for short): low <= price
        order = _order("BUY", "limit", price=80)
        fills = _check(self.mode, [order], high=100, low=79)
        assert len(fills) == 1

    def test_buy_stop_market_triggered_when_high_hits(self):
        # BUY stop_market (SL for short): high >= trigger
        order = _order("BUY", "stop_market", trigger=120)
        fills = _check(self.mode, [order], high=125, low=115)
        assert len(fills) == 1

    def test_missing_trigger_price_skipped(self):
        order = _order("SELL", "stop_market")
        fills = _check(self.mode, [order], high=10, low=1)
        assert fills == []


class TestTrailingStop:
    def setup_method(self):
        self.mode = WickFillMode()

    def test_trailing_stop_updates_peak_and_triggers(self):
        # callback_rate=10% ⇒ trigger_level = peak * 0.9
        order = PendingOrder(
            id="t",
            symbol="BTC",
            order_type="trailing_stop",
            side="SELL",
            amount=Decimal("1"),
            callback_rate=Decimal("10"),
            peak_price=Decimal("100"),
        )
        # High 120 makes peak=120, trigger_level=108, low 105 triggers
        fills = self.mode.check_fills([order], {"high": Decimal("120"), "low": Decimal("105")})
        assert len(fills) == 1
        assert order.peak_price == Decimal("120")

    def test_trailing_stop_no_trigger_when_low_above_level(self):
        order = PendingOrder(
            id="t",
            symbol="BTC",
            order_type="trailing_stop",
            side="SELL",
            amount=Decimal("1"),
            callback_rate=Decimal("10"),
            peak_price=Decimal("100"),
        )
        # peak stays 100, trigger_level=90, low 95 does not trigger
        fills = self.mode.check_fills([order], {"high": Decimal("95"), "low": Decimal("95")})
        assert fills == []

    def test_trailing_stop_default_peak_uses_high(self):
        order = PendingOrder(
            id="t",
            symbol="BTC",
            order_type="trailing_stop",
            side="SELL",
            amount=Decimal("1"),
            callback_rate=Decimal("10"),
        )
        # No peak_price set - uses high=100 as peak, trigger=90, low=85 triggers
        fills = self.mode.check_fills([order], {"high": Decimal("100"), "low": Decimal("85")})
        assert len(fills) == 1
