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
from app.notification.command_handlers import (
    handle_help,
    handle_history,
    handle_report,
    handle_reset,
    handle_status,
)
from app.notification.deploy_commands import (
    handle_bot_version,
    handle_cancel_deploy,
    handle_deploy_status,
    handle_force_deploy,
)
from app.notification.formatting import (
    fmt_amount_auto,
    fmt_amount_precise,
    fmt_duration,
    fmt_pct,
    fmt_pnl,
    fmt_price,
    fmt_price_auto,
    fmt_price_precise,
    mono,
    row,
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
        verify = self._verify_chat_id
        ex = self._exchange
        pfx = self._prefix
        callbacks = {
            "/status": lambda cid: handle_status(ex, pfx, send, cid) if verify(cid) and ex else None,
            "/history": lambda cid: handle_history(ex, pfx, send, cid) if verify(cid) and ex else None,
            "/report": lambda cid: handle_report(ex, pfx, send, cid) if verify(cid) and ex else None,
            "/winrate": lambda cid: handle_report(ex, pfx, send, cid) if verify(cid) and ex else None,
            "/reset": lambda cid: handle_reset(ex, pfx, send, cid) if verify(cid) and ex else None,
            "/help": lambda cid: handle_help(pfx, send, cid) if verify(cid) else None,
            "/force_deploy": lambda cid: handle_force_deploy(send, cid) if verify(cid) else None,
            "/deploy_status": lambda cid: handle_deploy_status(send, cid) if verify(cid) else None,
            "/cancel_deploy": lambda cid: handle_cancel_deploy(send, cid) if verify(cid) else None,
            "/bot_version": lambda cid: handle_bot_version(send, cid) if verify(cid) else None,
        }
        self._bot.start_polling(callbacks)  # type: ignore[arg-type]

    def _verify_chat_id(self, chat_id: str) -> bool:
        if self._chat_id and str(chat_id) != str(self._chat_id):
            logger.warning(f"Unauthorized command attempt from chat {chat_id}")
            return False
        return True

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
        indicators: dict[str, float] | None = None,
        entry_fee: Decimal | None = None,
    ) -> None:
        notional = entry_price * amount
        margin = notional / Decimal(str(leverage)) if leverage else notional

        side_label = "LONG" if side.upper() in ("BUY", "LONG") else "SHORT"
        emoji = "🟢" if side_label == "LONG" else "🔴"

        lines = [f"{self._prefix} | {emoji} {side_label} ENTERED — {symbol}", ""]
        body = [
            row("Symbol:", symbol),
            row("Side:", side_label),
            row("Entry:", fmt_price_auto(entry_price)),
            row("Size:", f"{fmt_amount_auto(amount, entry_price)}  ({fmt_price(notional)})"),
            row("Leverage:", f"{leverage}x  (Margin: {fmt_price(margin)})"),
            "",
        ]

        if sl_price:
            sl_pct = (sl_price - entry_price) / entry_price * 100
            sl_risk = abs(entry_price - sl_price) * amount
            body.append(
                row("SL:", f"{fmt_price_auto(sl_price)}  ({fmt_pct(sl_pct)})  Risk: {fmt_pnl(-sl_risk)}")
            )

        if tp_prices:
            for label in ("TP1", "TP2", "TP3"):
                tp_p = tp_prices.get(label)
                if tp_p:
                    diff_pct = (tp_p - entry_price) / entry_price * 100
                    reward = abs(tp_p - entry_price) * amount
                    body.append(
                        row(f"{label}:", f"{fmt_price_auto(tp_p)}  ({fmt_pct(diff_pct)})  +{float(reward):,.2f}")
                    )

        if indicators:
            body += ["", "─" * 28]
            if "rsi_ema9" in indicators:
                body.append(row("RSI EMA9:", f"{indicators['rsi_ema9']:.2f}"))
            if "rsi_wma45" in indicators:
                body.append(row("RSI WMA45:", f"{indicators['rsi_wma45']:.2f}"))
            if "spread" in indicators:
                body.append(row("Spread:", f"{indicators['spread']:.2f}"))
            if "above_ema21" in indicators:
                body.append(row("Above EMA21:", f"{int(indicators['above_ema21'])}"))

        if entry_fee is not None:
            body += ["", row("Entry Fee:", f"{fmt_pnl(-entry_fee)}")]

        if balance is not None:
            body += ["", row("Balance:", f"{fmt_price(balance)}")]

        lines.append(mono("\n".join(body)))
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
        entry_price: Decimal | None = None,
        total_fees: Decimal | None = None,
        hold_duration: float | None = None,
        return_pct: Decimal | None = None,
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
        body = []

        if entry_price is not None:
            body.append(row("Entry:", fmt_price_auto(entry_price)))
        body += [
            row("Exit:", fmt_price_auto(fill_price)),
            row("Closed:", f"{fmt_amount_auto(amount, fill_price)}  ({fmt_price(fill_price * amount)})"),
        ]

        if pnl_gross is not None:
            body.append(row("Gross P&L:", fmt_pnl(pnl_gross)))
        if total_fees is not None:
            # Show a single Total Fees line with the entry/exit breakdown inline.
            # ``total_fees`` is pro-rated (entry_fee_slice + exit_fee) so partial
            # closes reflect only the slice's share of the entry fee.
            if fees is not None:
                entry_slice = total_fees - fees
                leg_label = "maker" if is_tp else "taker"
                body.append(
                    row(
                        "Total Fees:",
                        f"{fmt_pnl(-total_fees)}  (entry {fmt_pnl(-entry_slice)}, exit {fmt_pnl(-fees)} {leg_label})",
                    )
                )
            else:
                body.append(row("Total Fees:", f"{fmt_pnl(-total_fees)}"))
        elif fees is not None:
            leg_label = "maker" if is_tp else "taker"
            body.append(row("Total Fees:", f"{fmt_pnl(-fees)}  (exit only, {leg_label})"))
        if pnl_net is not None:
            body.append(row("Net P&L:", fmt_pnl(pnl_net)))

        if not is_partial and pnl_net is not None and r_multiple is not None:
            body += [
                "",
                "─" * 33,
                row("Trade P&L:", f"{fmt_pnl(pnl_net)}  ({float(r_multiple):.2f}R)"),
            ]
        if return_pct is not None:
            body.append(row("Return:", fmt_pct(return_pct)))
        if hold_duration is not None and hold_duration > 0:
            body.append(row("Hold:", fmt_duration(hold_duration)))

        if is_partial and remaining_amount is not None:
            body += ["", row("Remaining:", f"{float(remaining_amount):.4f} contracts")]

        if balance is not None:
            body += ["", row("Balance:", fmt_price(balance))]

        lines.append(mono("\n".join(body)))
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
            row("Rate:", f"{fmt_pct(rate_pct)}  (longs pay)"),
            row("Payment:", f"{fmt_pnl(-payment)}"),
            "",
            row("Balance:", fmt_price(balance)),
        ]
        lines.append(mono("\n".join(body)))
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
