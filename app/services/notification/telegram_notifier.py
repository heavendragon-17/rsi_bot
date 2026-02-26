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

import logging
import os
from decimal import Decimal
from typing import Dict, Optional

from app.core.interfaces import INotifier
from app.services.notification.telegram_bot import TelegramBot

logger = logging.getLogger(__name__)

_MODE_PREFIX: Dict[str, str] = {
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
        self._chat_id: Optional[str] = os.getenv("TELEGRAM_CHAT_ID")
        self._prefix = _MODE_PREFIX.get(mode, "🤖 BOT")

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
        sl_price: Optional[Decimal] = None,
        tp_prices: Optional[Dict[str, Decimal]] = None,
        leverage: int = 1,
        balance: Optional[Decimal] = None,
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
            body.append(
                _row("SL (Hard):", f"{_fmt_price(sl_price)}  ({_fmt_pct(sl_pct)})  Risk: {_fmt_pnl(sl_risk)}")
            )

        if tp_prices:
            for label in ("TP1", "TP2", "TP3"):
                tp_p = tp_prices.get(label)
                if tp_p:
                    diff_pct = (tp_p - entry_price) / entry_price * 100
                    reward = abs(tp_p - entry_price) * amount
                    body.append(
                        _row(f"{label}:", f"{_fmt_price(tp_p)}  (+{float(diff_pct):.2f}%)  Reward: +{float(reward):,.2f}")
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
        pnl_gross: Optional[Decimal] = None,
        pnl_net: Optional[Decimal] = None,
        fees: Optional[Decimal] = None,
        r_multiple: Optional[Decimal] = None,
        remaining_amount: Optional[Decimal] = None,
        balance: Optional[Decimal] = None,
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
