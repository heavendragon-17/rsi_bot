"""Tests for TelegramNotifier formatting + dispatch paths."""

from decimal import Decimal
from unittest.mock import MagicMock, patch


def _mk_notifier(mode="sim"):
    with patch("app.notification.telegram_notifier.TelegramBot") as MockBot, \
         patch.dict("os.environ", {"TELEGRAM_CHAT_ID": "chat-xyz"}):
        mock_bot_instance = MagicMock()
        MockBot.return_value = mock_bot_instance
        from app.notification.telegram_notifier import TelegramNotifier
        notifier = TelegramNotifier(mode=mode)
        return notifier, mock_bot_instance


class TestVerifyChatId:
    def test_mismatched_chat_rejected(self):
        notifier, _ = _mk_notifier()
        assert notifier._verify_chat_id("different") is False

    def test_matching_chat_accepted(self):
        notifier, _ = _mk_notifier()
        assert notifier._verify_chat_id("chat-xyz") is True

    def test_no_env_chat_accepts_all(self):
        with patch("app.notification.telegram_notifier.TelegramBot"), \
             patch.dict("os.environ", {}, clear=True):
            from app.notification.telegram_notifier import TelegramNotifier
            notifier = TelegramNotifier(mode="sim")
            assert notifier._verify_chat_id("anything") is True


class TestAttachAndCommands:
    def test_attach_exchange(self):
        notifier, _ = _mk_notifier()
        exchange = MagicMock()
        notifier.attach_exchange(exchange)
        assert notifier._exchange is exchange

    def test_start_command_polling_registers_callbacks(self):
        notifier, bot = _mk_notifier()
        notifier.attach_exchange(MagicMock())
        notifier.start_command_polling()
        bot.start_polling.assert_called_once()
        callbacks = bot.start_polling.call_args[0][0]
        assert "/status" in callbacks
        assert "/help" in callbacks
        assert "/force_deploy" in callbacks


class TestSendMessage:
    def test_sends_through_bot(self):
        notifier, bot = _mk_notifier()
        notifier.send_message("hi")
        bot.send_message.assert_called_once()
        # Legacy callers default to no topic → message_thread_id=None.
        assert bot.send_message.call_args.kwargs.get("message_thread_id") is None

    def test_send_forwards_topic_id_to_bot(self):
        notifier, bot = _mk_notifier()
        notifier.send_message("hi", topic_id=99)
        assert bot.send_message.call_args.kwargs["message_thread_id"] == 99

    def test_send_swallows_exception(self):
        notifier, bot = _mk_notifier()
        bot.send_message.side_effect = RuntimeError("boom")
        # _send should swallow the exception
        notifier._send("x")


class TestOnEntry:
    def test_long_entry_minimal(self):
        notifier, bot = _mk_notifier()
        notifier.on_entry(
            symbol="BTC",
            side="BUY",
            entry_price=Decimal("100"),
            amount=Decimal("1"),
        )
        bot.send_message.assert_called_once()
        msg = bot.send_message.call_args[0][0]
        assert "LONG ENTERED" in msg
        assert "BTC" in msg

    def test_entry_with_sl_tp_and_risk(self):
        notifier, bot = _mk_notifier()
        notifier.on_entry(
            symbol="BTC",
            side="BUY",
            entry_price=Decimal("100"),
            amount=Decimal("1"),
            sl_price=Decimal("95"),
            tp_prices={"TP1": Decimal("105"), "TP2": Decimal("110"), "TP3": Decimal("120")},
            leverage=5,
            balance=Decimal("1000"),
            entry_fee=Decimal("0.05"),
            indicators={"rsi_ema9": 30.0, "rsi_wma45": 40.0, "spread": 10.0, "above_ema21": 2},
            reason="Momentum down",
            soft_sl_price=Decimal("96"),
            lock_profit_price=Decimal("101"),
            tp_allocations={"TP1": 0.5, "TP2": 0.5, "TP3": 1.0},
            signal_class=1,
            risk_per_trade_pct=Decimal("0.02"),
        )
        msg = bot.send_message.call_args[0][0]
        assert "TP1:" in msg
        assert "TP2:" in msg
        assert "SL (Hard):" in msg
        assert "SL (Soft):" in msg
        assert "Lock Profit:" in msg
        assert "Momentum down" in msg
        assert "RSI EMA9" in msg
        assert "Optimal" in msg

    def test_short_entry(self):
        notifier, bot = _mk_notifier()
        notifier.on_entry(
            symbol="BTC",
            side="SELL",
            entry_price=Decimal("100"),
            amount=Decimal("1"),
            sl_price=Decimal("105"),
            tp_prices={"TP1": Decimal("95")},
        )
        msg = bot.send_message.call_args[0][0]
        assert "SHORT ENTERED" in msg


class TestOnFill:
    def test_tp_fill(self):
        notifier, bot = _mk_notifier()
        notifier.on_fill(
            symbol="BTC",
            exit_reason="TP1",
            fill_price=Decimal("105"),
            amount=Decimal("0.5"),
            pnl_gross=Decimal("2.5"),
            pnl_net=Decimal("2.4"),
            fees=Decimal("0.1"),
            total_fees=Decimal("0.2"),
            r_multiple=Decimal("1.2"),
            remaining_amount=Decimal("0.5"),
            balance=Decimal("1002"),
            entry_price=Decimal("100"),
            hold_duration=3600,
        )
        msg = bot.send_message.call_args[0][0]
        assert "TP1 HIT" in msg
        assert "partial" in msg
        assert "Entry" in msg
        assert "Exit" in msg

    def test_sl_fill(self):
        notifier, bot = _mk_notifier()
        notifier.on_fill(
            symbol="BTC",
            exit_reason="SL",
            fill_price=Decimal("95"),
            amount=Decimal("1"),
            pnl_net=Decimal("-5"),
            r_multiple=Decimal("-1"),
            balance=Decimal("995"),
            entry_price=Decimal("100"),
            hold_duration=300,
        )
        msg = bot.send_message.call_args[0][0]
        assert "SL" in msg and "HIT" in msg

    def test_generic_exit(self):
        notifier, bot = _mk_notifier()
        notifier.on_fill(
            symbol="ETH",
            exit_reason="MANUAL",
            fill_price=Decimal("200"),
            amount=Decimal("1"),
            fees=Decimal("0.1"),
        )
        msg = bot.send_message.call_args[0][0]
        assert "EXIT" in msg
        assert "MANUAL" in msg


class TestOnError:
    def test_formatted(self):
        notifier, bot = _mk_notifier()
        notifier.on_error("ctx", "msg")
        msg = bot.send_message.call_args[0][0]
        assert "ERROR" in msg
        assert "ctx" in msg
        assert "msg" in msg


class TestOnFunding:
    def test_funding_message(self):
        notifier, bot = _mk_notifier()
        notifier.on_funding(
            symbol="BTC",
            rate=Decimal("0.0001"),
            payment=Decimal("-0.5"),
            balance=Decimal("1000"),
        )
        msg = bot.send_message.call_args[0][0]
        assert "FUNDING" in msg
        assert "BTC" in msg


class TestOnToggle:
    def test_paused(self):
        notifier, bot = _mk_notifier()
        notifier.on_toggle(True)
        msg = bot.send_message.call_args[0][0]
        assert "PAUSED" in msg

    def test_resumed(self):
        notifier, bot = _mk_notifier()
        notifier.on_toggle(False)
        msg = bot.send_message.call_args[0][0]
        assert "RESUMED" in msg
