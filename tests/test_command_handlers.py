"""Tests for Telegram /status, /history, /report, /reset, /help handlers."""

from decimal import Decimal
from unittest.mock import MagicMock

from app.notification.command_handlers import (
    handle_help,
    handle_history,
    handle_report,
    handle_reset,
    handle_status,
    handle_topics,
)


def _mk_exchange(positions=None, balance=1000.0, state=None, sim=None, is_paused=False):
    exchange = MagicMock()
    exchange.fetch_balance.return_value = {"total": {"USDT": balance}}
    exchange.fetch_positions.return_value = positions or []
    exchange.is_paused = lambda: is_paused
    exchange.state = state
    exchange._sim = sim
    return exchange


def _mk_trade(pnl_net=10, entry=100, exit=110, symbol="BTC", exit_reason="TP1",
              r_multiple=None, pnl_gross=None, fees_paid=Decimal("0"),
              funding_paid=Decimal("0"), opened_at=0, closed_at=0):
    trade = MagicMock()
    trade.pnl_net = Decimal(str(pnl_net))
    trade.pnl_gross = Decimal(str(pnl_gross if pnl_gross is not None else pnl_net))
    trade.entry_price = Decimal(str(entry))
    trade.exit_price = Decimal(str(exit))
    trade.symbol = symbol
    trade.exit_reason = exit_reason
    trade.r_multiple = Decimal(str(r_multiple)) if r_multiple is not None else None
    trade.fees_paid = fees_paid
    trade.funding_paid = funding_paid
    trade.opened_at = opened_at
    trade.closed_at = closed_at
    return trade


class TestHandleStatus:
    def test_no_positions(self):
        send = MagicMock()
        exchange = _mk_exchange()
        handle_status(exchange, "PREFIX", send, chat_id="cid")
        send.assert_called_once()
        msg = send.call_args[0][0]
        assert "STATUS" in msg
        assert "0 open" in msg

    def test_paused_status(self):
        send = MagicMock()
        exchange = _mk_exchange(is_paused=True)
        handle_status(exchange, "P", send, chat_id="c")
        assert "PAUSED" in send.call_args[0][0]

    def test_positions_non_sim(self):
        send = MagicMock()
        positions = [{
            "symbol": "BTC/USDT",
            "contracts": 0.5,
            "entryPrice": 50000,
            "unrealizedPnl": 100.0,
        }]
        exchange = _mk_exchange(positions=positions)
        handle_status(exchange, "P", send, chat_id="c")
        msg = send.call_args[0][0]
        assert "BTC/USDT" in msg

    def test_positions_with_sim_state(self):
        send = MagicMock()
        sim_pos = MagicMock()
        sim_pos.opened_at = 0  # no hold duration
        sim_pos.tp1_hit = False
        sim_pos.tp2_hit = False
        state = MagicMock()
        state.initial_balance = 1000.0
        state.positions = {"BTC": sim_pos}

        # pending orders: one SL, one TP
        sl_order = MagicMock()
        sl_order.side = "SELL"
        sl_order.order_type = "stop_market"
        sl_order.trigger_price = Decimal("95")
        sl_order.price = None
        tp_order = MagicMock()
        tp_order.side = "SELL"
        tp_order.order_type = "limit"
        tp_order.price = Decimal("110")
        sim = MagicMock()
        sim.get_pending_orders.return_value = [sl_order, tp_order]

        positions = [{"symbol": "BTC", "entryPrice": 100.0, "contracts": 1.0, "unrealizedPnl": 10.0}]
        exchange = _mk_exchange(positions=positions, state=state, sim=sim)
        handle_status(exchange, "P", send, chat_id="c")
        msg = send.call_args[0][0]
        assert "SL (Hard):" in msg
        assert "TP1:" in msg


class TestHandleHistory:
    def test_no_state(self):
        send = MagicMock()
        exchange = MagicMock()
        del exchange.state  # ensures getattr returns None
        exchange.state = None
        handle_history(exchange, "P", send, chat_id="c")
        send.assert_not_called()

    def test_empty_trades(self):
        send = MagicMock()
        state = MagicMock()
        state.closed_trades = []
        exchange = _mk_exchange(state=state)
        handle_history(exchange, "P", send, chat_id="c")
        assert "No closed trades" in send.call_args[0][0]

    def test_recent_trades(self):
        send = MagicMock()
        state = MagicMock()
        state.closed_trades = [
            _mk_trade(pnl_net=10, exit_reason="TP1", r_multiple=1.5),
            _mk_trade(pnl_net=-5, exit_reason="SL", r_multiple=-1.0),
        ]
        exchange = _mk_exchange(state=state)
        handle_history(exchange, "P", send, chat_id="c")
        msg = send.call_args[0][0]
        assert "TP1" in msg
        assert "SL" in msg


class TestHandleReport:
    def test_no_state(self):
        send = MagicMock()
        exchange = MagicMock()
        exchange.state = None
        handle_report(exchange, "P", send, chat_id="c")
        send.assert_not_called()

    def test_no_trades(self):
        send = MagicMock()
        state = MagicMock()
        state.closed_trades = []
        exchange = _mk_exchange(state=state)
        handle_report(exchange, "P", send, chat_id="c")
        assert "No trades" in send.call_args[0][0]

    def test_full_report_emits_two_messages(self):
        send = MagicMock()
        state = MagicMock()
        state.closed_trades = [
            _mk_trade(pnl_net=10, pnl_gross=10, exit_reason="TP1", r_multiple=1, opened_at=1, closed_at=100),
            _mk_trade(pnl_net=-5, pnl_gross=-5, exit_reason="SL", r_multiple=-1, opened_at=1, closed_at=100),
            _mk_trade(pnl_net=15, pnl_gross=15, exit_reason="TP2", r_multiple=2, opened_at=1, closed_at=100),
        ]
        state.initial_balance = Decimal("1000")
        exchange = _mk_exchange(state=state)
        handle_report(exchange, "P", send, chat_id="c")
        # Should send two messages (1/2 and 2/2)
        assert send.call_count == 2
        assert "REPORT (1/2)" in send.call_args_list[0][0][0]
        assert "REPORT (2/2)" in send.call_args_list[1][0][0]


class TestHandleReset:
    def test_success_in_sim_mode(self):
        send = MagicMock()
        state = MagicMock()
        state.reset = MagicMock()
        exchange = _mk_exchange(state=state)
        handle_reset(exchange, "P", send, chat_id="c")
        state.reset.assert_called_once()
        assert "RESET" in send.call_args[0][0]

    def test_reset_not_supported(self):
        send = MagicMock()
        exchange = MagicMock(spec=[])  # no state attribute
        handle_reset(exchange, "P", send, chat_id="c")
        assert "FAILED" in send.call_args[0][0]


class TestHandleHelp:
    def test_help_message(self):
        send = MagicMock()
        handle_help("P", send, chat_id="c")
        msg = send.call_args[0][0]
        assert "HELP" in msg
        assert "/status" in msg
        assert "/history" in msg
        assert "/report" in msg
        assert "/force_deploy" in msg
        assert "/topics" in msg


class TestHandleTopics:
    def test_lists_active_inactive_and_debug_topics(self):
        send = MagicMock()
        topics = [
            ("rsi_no_retest", 1003, "active"),
            ("rsi_wma_retest", 43, "inactive"),
            ("debug", 1006, "always"),
        ]

        handle_topics(topics, "P", send, chat_id="c")

        msg = send.call_args[0][0]
        assert "TOPICS" in msg
        assert "rsi_no_retest" in msg
        assert "topic ID: 1003 (active)" in msg
        assert "rsi_wma_retest" in msg
        assert "topic ID: 43 (inactive)" in msg
        assert "topic ID: 1006 (always)" in msg

    def test_escapes_topic_names_for_html(self):
        send = MagicMock()

        handle_topics([("<strategy>", 7, "active")], "P", send, chat_id="c")

        assert "&lt;strategy&gt;" in send.call_args[0][0]
