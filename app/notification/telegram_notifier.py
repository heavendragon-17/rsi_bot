"""
TelegramNotifier
================
Implements INotifier with rich HTML-formatted Telegram messages.
Mode-agnostic: prefix adapts to the mode passed at construction.

Mode prefixes:
  live    → 🤖 LIVE
  paper   → 🧪 TESTNET
  sim     → 📄 SIM
  mock    → 🔬 BACKTEST

All methods use scalar parameters only — no exchange-specific state objects.
"""

from __future__ import annotations

import os
from decimal import Decimal

import structlog

from app.core.interfaces import IExchange, INotifier
from app.notification.deploy_commands import (
    handle_bot_version,
    handle_cancel_deploy,
    handle_deploy_status,
    handle_force_deploy,
)
from app.notification.telegram_bot import TelegramBot

logger = structlog.get_logger(__name__)

_MODE_PREFIX: dict[str, str] = {
    "live": "🤖 LIVE",
    "paper": "🧪 TESTNET",
    "sim": "📄 SIM",
    "mock": "🔬 BACKTEST",
}


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _mono(text: str) -> str:
    return f"<pre>{text}</pre>"


def _fmt_price(p: Decimal) -> str:
    return f"${float(p):,.2f}"


def _fmt_pct(p: Decimal) -> str:
    sign = "+" if p >= 0 else ""
    return f"{sign}{float(p):.2f}%"


def _fmt_pnl(p: Decimal) -> str:
    sign = "+" if p >= 0 else ""
    return f"{sign}{float(p):,.2f}"


def _row(label: str, value: str, width: int = 14) -> str:
    return f"{label:<{width}} {value}"


# ---------------------------------------------------------------------------
# TelegramNotifier
# ---------------------------------------------------------------------------


class TelegramNotifier(INotifier):
    """
    Formats and dispatches trade events to Telegram.

    Constructor reads TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID from env.
    """

    def __init__(self, mode: str = "sim"):
        self._bot = TelegramBot(
            token_env="TELEGRAM_BOT_TOKEN",
            chat_id_env="TELEGRAM_CHAT_ID",
        )
        self._chat_id: str | None = os.getenv("TELEGRAM_CHAT_ID")
        self._prefix = _MODE_PREFIX.get(mode, "🤖 BOT")
        self._exchange: IExchange | None = None

    def attach_exchange(self, exchange: IExchange) -> None:
        """Store a reference to the exchange for handling commands."""
        self._exchange = exchange

    def start_command_polling(self) -> None:
        """Start the Telegram polling loop and register commands."""
        send = self._bot.send_message
        callbacks = {
            "/status": self._handle_status_cmd,
            "/history": self._handle_history_cmd,
            "/winrate": self._handle_winrate_cmd,
            "/report": self._handle_report_cmd,
            "/reset": self._handle_reset_cmd,
            "/force_deploy": lambda cid: handle_force_deploy(send, cid),
            "/deploy_status": lambda cid: handle_deploy_status(send, cid),
            "/cancel_deploy": lambda cid: handle_cancel_deploy(send, cid),
            "/bot_version": lambda cid: handle_bot_version(send, cid),
        }
        self._bot.start_polling(callbacks)  # type: ignore[arg-type]

    def _verify_chat_id(self, chat_id: str) -> bool:
        if self._chat_id and str(chat_id) != str(self._chat_id):
            logger.warning(f"Unauthorized command attempt from chat {chat_id}")
            return False
        return True

    def _handle_status_cmd(self, chat_id: str) -> None:
        if not self._verify_chat_id(chat_id):
            return
        if not self._exchange:
            return

        balance = self._exchange.fetch_balance()
        usdt_total = balance.get("total", {}).get("USDT", 0.0)
        positions = self._exchange.fetch_positions()

        running_status = "⏸ PAUSED" if getattr(self._exchange, "is_paused", lambda: False)() else "▶️ RUNNING"

        lines = [
            f"{self._prefix} | 📊 STATUS",
            "",
            _row("Bot State:", running_status),
            _row("Balance:", f"${usdt_total:,.2f}"),
            _row("Positions:", f"{len(positions)} open"),
        ]

        if positions:
            lines.append("")
            for p in positions:
                upnl = p.get("unrealizedPnl", 0.0)
                emoji = "🟢" if upnl >= 0 else "🔴"
                lines.append(
                    f"{emoji} {p['symbol']} | Size: {p['contracts']:.4f} | PnL: {_fmt_pnl(Decimal(str(upnl)))}"
                )

        msg = "\n".join(lines)
        self._bot.send_message(_mono(msg), chat_id=chat_id)

    def _handle_history_cmd(self, chat_id: str) -> None:
        if not self._verify_chat_id(chat_id):
            return
        if not self._exchange or not hasattr(self._exchange, "state"):
            return

        state = self._exchange.state
        trades = state.closed_trades[-10:]  # last 10

        if not trades:
            self._bot.send_message(_mono(f"{self._prefix} | 📜 HISTORY\n\nNo closed trades yet."), chat_id=chat_id)
            return

        lines = [f"{self._prefix} | 📜 HISTORY (Last {len(trades)})", ""]
        for t in reversed(trades):
            emoji = "🟢" if t.pnl_net >= 0 else "🔴"
            lines.append(f"{emoji} {t.symbol} | {_fmt_pnl(t.pnl_net)} ({t.exit_reason}) | {float(t.amount):.4f}")

        self._bot.send_message(_mono("\n".join(lines)), chat_id=chat_id)

    def _handle_winrate_cmd(self, chat_id: str) -> None:
        if not self._verify_chat_id(chat_id):
            return
        if not self._exchange or not hasattr(self._exchange, "state"):
            return

        trades = self._exchange.state.closed_trades
        total = len(trades)
        if total == 0:
            self._bot.send_message(_mono(f"{self._prefix} | 🎯 WINRATE\n\nNo trades yet."), chat_id=chat_id)
            return

        wins = sum(1 for t in trades if t.pnl_net > 0)
        losses = sum(1 for t in trades if t.pnl_net <= 0)
        winrate = (wins / total) * 100

        lines = [
            f"{self._prefix} | 🎯 WINRATE",
            "",
            _row("Total Trades:", str(total)),
            _row("Wins:", str(wins)),
            _row("Losses:", str(losses)),
            _row("Win Rate:", f"{winrate:.1f}%"),
        ]
        self._bot.send_message(_mono("\n".join(lines)), chat_id=chat_id)

    def _handle_report_cmd(self, chat_id: str) -> None:
        if not self._verify_chat_id(chat_id):
            return
        if not self._exchange or not hasattr(self._exchange, "state"):
            return

        state = self._exchange.state
        trades = state.closed_trades

        total_pnl = sum(t.pnl_net for t in trades)
        gross_pnl = sum(t.pnl_gross for t in trades)
        total_fees = sum(t.fees_paid for t in trades)
        total_funding = sum(getattr(t, "funding_paid", Decimal("0")) for t in trades)

        lines = [
            f"{self._prefix} | 📈 REPORT",
            "",
            _row("Trades:", str(len(trades))),
            _row("Net P&L:", _fmt_pnl(total_pnl)),
            _row("Gross P&L:", _fmt_pnl(gross_pnl)),
            _row("Total Fees:", _fmt_pnl(-total_fees)),
        ]
        if total_funding != Decimal("0"):
            lines.append(_row("Funding:", _fmt_pnl(-total_funding)))  # type: ignore[arg-type]

        self._bot.send_message(_mono("\n".join(lines)), chat_id=chat_id)

    def _handle_reset_cmd(self, chat_id: str) -> None:
        if not self._verify_chat_id(chat_id):
            return
        if not self._exchange:
            return

        if hasattr(self._exchange, "state") and hasattr(self._exchange.state, "reset"):
            self._exchange.state.reset()
            self._bot.send_message(
                _mono(f"{self._prefix} | 🔄 RESET\n\nBot state (balance and trades) has been reset."), chat_id=chat_id
            )
        else:
            self._bot.send_message(
                _mono(f"{self._prefix} | ⚠️ RESET FAILED\n\nReset not supported in current mode."), chat_id=chat_id
            )

    # ------------------------------------------------------------------
    # INotifier
    # ------------------------------------------------------------------

    def send_message(self, message: str) -> None:
        self._send(message)

    def on_entry(
        self,
        symbol: str,
        side: str,
        entry_price: Decimal,
        amount: Decimal,
        sl_price: Decimal | None = None,
        tp_prices: dict[str, Decimal] | None = None,
        leverage: int = 1,
        balance: Decimal | None = None,
    ) -> None:
        notional = entry_price * amount
        margin = notional / Decimal(str(leverage)) if leverage else notional

        side_label = "LONG" if side.upper() in ("BUY", "LONG") else "SHORT"
        emoji = "🟢" if side_label == "LONG" else "🔴"

        lines = [f"{self._prefix} | {emoji} {side_label} ENTERED — {symbol}", ""]
        body = [
            _row("Symbol:", symbol),
            _row("Side:", side_label),
            _row("Entry:", _fmt_price(entry_price)),
            _row("Size:", f"{float(amount):.4f}  ({_fmt_price(notional)})"),
            _row("Leverage:", f"{leverage}x  (Margin: {_fmt_price(margin)})"),
            "",
        ]

        if sl_price:
            sl_pct = (sl_price - entry_price) / entry_price * 100
            sl_risk = abs(entry_price - sl_price) * amount
            body.append(_row("SL (Hard):", f"{_fmt_price(sl_price)}  ({_fmt_pct(sl_pct)})  Risk: {_fmt_pnl(sl_risk)}"))

        if tp_prices:
            for label in ("TP1", "TP2", "TP3"):
                tp_p = tp_prices.get(label)
                if tp_p:
                    diff_pct = (tp_p - entry_price) / entry_price * 100
                    reward = abs(tp_p - entry_price) * amount
                    body.append(
                        _row(
                            f"{label}:", f"{_fmt_price(tp_p)}  (+{float(diff_pct):.2f}%)  Reward: +{float(reward):,.2f}"
                        )
                    )

        if balance is not None:
            body += ["", _row("Balance:", f"{_fmt_price(balance)}")]

        lines.append(_mono("\n".join(body)))
        self._send("\n".join(lines))

    def on_fill(
        self,
        symbol: str,
        exit_reason: str,
        fill_price: Decimal,
        amount: Decimal,
        pnl_gross: Decimal | None = None,
        pnl_net: Decimal | None = None,
        fees: Decimal | None = None,
        r_multiple: Decimal | None = None,
        remaining_amount: Decimal | None = None,
        balance: Decimal | None = None,
    ) -> None:
        reason_upper = exit_reason.upper()
        is_sl = "SL" in reason_upper or reason_upper in ("STOP_LOSS", "BREAKEVEN", "LOCK_PROFIT")
        is_tp = reason_upper.startswith("TP")
        is_partial = (remaining_amount is not None) and remaining_amount > Decimal("0")

        if is_sl:
            emoji = "🛑" if "HARD" in reason_upper else "🟡"
            header = f"{emoji} {exit_reason.replace('_', ' ')} HIT — {symbol} LONG"
        elif is_tp:
            status = " (partial)" if is_partial else " (CLOSED)"
            header = f"✅ {exit_reason} HIT — {symbol} LONG{status}"
        else:
            header = f"📤 EXIT — {symbol}  ({exit_reason})"

        lines = [f"{self._prefix} | {header}", ""]
        body = [
            _row("Fill:", _fmt_price(fill_price)),
            _row("Closed:", f"{float(amount):.4f}  ({_fmt_price(fill_price * amount)})"),
        ]

        if pnl_gross is not None:
            body.append(_row("Gross P&L:", _fmt_pnl(pnl_gross)))
        if fees is not None:
            fee_label = "Fee (maker):" if is_tp else "Fee (taker):"
            body.append(_row(fee_label, f"{_fmt_pnl(-fees)}"))
        if pnl_net is not None:
            body.append(_row("Net P&L:", _fmt_pnl(pnl_net)))

        if not is_partial and pnl_net is not None and r_multiple is not None:
            body += [
                "",
                "─" * 33,
                _row("Trade P&L:", f"{_fmt_pnl(pnl_net)}  ({float(r_multiple):.2f}R)"),
            ]

        if is_partial and remaining_amount is not None:
            body += ["", _row("Remaining:", f"{float(remaining_amount):.4f} contracts")]

        if balance is not None:
            body += ["", _row("Balance:", _fmt_price(balance))]

        lines.append(_mono("\n".join(body)))
        self._send("\n".join(lines))

    def on_error(self, context: str, error: str) -> None:
        msg = f"{self._prefix} | ⚠️ ERROR\n<pre>{context}: {error}</pre>"
        self._send(msg)

    def on_funding(
        self,
        symbol: str,
        rate: Decimal,
        payment: Decimal,
        balance: Decimal,
    ) -> None:
        rate_pct = rate * 100
        lines = [f"{self._prefix} | 💸 FUNDING — {symbol}", ""]
        body = [
            _row("Rate:", f"{_fmt_pct(rate_pct)}  (longs pay)"),
            _row("Payment:", f"{_fmt_pnl(-payment)}"),
            "",
            _row("Balance:", _fmt_price(balance)),
        ]
        lines.append(_mono("\n".join(body)))
        self._send("\n".join(lines))

    def on_toggle(self, is_paused: bool) -> None:
        if is_paused:
            msg = (
                f"{self._prefix} | ⏸ PAUSED\n"
                "Signal execution suspended. Open positions still monitored.\n"
                "Use /toggle to resume."
            )
        else:
            msg = f"{self._prefix} | ▶️ RESUMED\nSignal execution active."
        self._send(msg)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _send(self, message: str) -> None:
        try:
            self._bot.send_message(message, chat_id=self._chat_id)
        except Exception:
            logger.exception("TelegramNotifier: failed to send message")
