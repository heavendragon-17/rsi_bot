"""TelegramNotifier — INotifier impl with HTML-formatted trade messages."""

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
    fmt_duration,
    fmt_pct,
    fmt_pnl,
    fmt_price,
    fmt_price_auto,
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


class TelegramNotifier(INotifier):
    """
    Formats and dispatches trade events to Telegram.

    Constructor reads TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID from env.
    """

    def __init__(self, mode: str = "sim", *, chat_id_override: str | int | None = None):
        self._bot = TelegramBot(
            token_env="TELEGRAM_BOT_TOKEN",
            chat_id_env="TELEGRAM_CHAT_ID",
        )
        # Signal mode supplies telegram.group_id so topic-targeted sends use
        # the supergroup that hosts the topics, not TELEGRAM_CHAT_ID.
        if chat_id_override is not None:
            self._chat_id: str | None = str(chat_id_override)
        else:
            self._chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self._prefix = _MODE_PREFIX.get(mode, "🤖 BOT")
        self._exchange: IExchange | None = None

    def attach_exchange(self, exchange: IExchange) -> None:
        """Store a reference to the exchange for handling commands."""
        self._exchange = exchange

    def start_command_polling(
        self,
        extra_callbacks: dict | None = None,
    ) -> None:
        """Start the Telegram polling loop and register commands.

        ``extra_callbacks`` lets callers (e.g. the signal-mode runner) inject
        commands depending on runtime state the notifier doesn't own. Each
        callback receives ``chat_id`` and must run its own auth check via
        ``verify_chat_id``.
        """
        send = self._bot.send_message
        verify = self._verify_chat_id
        ex = self._exchange
        pfx = self._prefix

        def _exchange_cmd(fn):
            """Wrap an exchange-scoped command so signal mode replies clearly."""
            def cb(cid):
                if not verify(cid):
                    return
                if ex is None:
                    send("ℹ️ Not available in signal mode.", chat_id=cid)
                    return
                fn(ex, pfx, send, cid)
            return cb

        callbacks = {
            "/status": _exchange_cmd(handle_status),
            "/history": _exchange_cmd(handle_history),
            "/report": _exchange_cmd(handle_report),
            "/winrate": _exchange_cmd(handle_report),
            "/reset": _exchange_cmd(handle_reset),
            "/help": lambda cid: handle_help(pfx, send, cid) if verify(cid) else None,
            "/force_deploy": lambda cid: handle_force_deploy(send, cid) if verify(cid) else None,
            "/deploy_status": lambda cid: handle_deploy_status(send, cid) if verify(cid) else None,
            "/cancel_deploy": lambda cid: handle_cancel_deploy(send, cid) if verify(cid) else None,
            "/bot_version": lambda cid: handle_bot_version(send, cid) if verify(cid) else None,
        }
        if extra_callbacks:
            callbacks.update(extra_callbacks)
        self._bot.start_polling(callbacks)  # type: ignore[arg-type]

    def verify_chat_id(self, chat_id: str) -> bool:
        """Public wrapper around :meth:`_verify_chat_id` for extension callbacks."""
        return self._verify_chat_id(chat_id)

    def _verify_chat_id(self, chat_id: str) -> bool:
        if self._chat_id and str(chat_id) != str(self._chat_id):
            logger.warning(f"Unauthorized command attempt from chat {chat_id}")
            return False
        return True

    def send_message(self, message: str, *, topic_id: int | None = None) -> None:
        self._send(message, topic_id=topic_id)

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
        reason: str | None = None,
        soft_sl_price: Decimal | None = None,
        lock_profit_price: Decimal | None = None,
        tp_allocations: dict[str, float] | None = None,
        signal_class: int | None = None,
        risk_per_trade_pct: Decimal | None = None,
    ) -> None:
        notional = entry_price * amount
        margin = notional / Decimal(str(leverage)) if leverage else notional

        side_label = "LONG" if side.upper() in ("BUY", "LONG") else "SHORT"
        emoji = "🟢" if side_label == "LONG" else "🔴"
        is_long = side_label == "LONG"
        direction = Decimal("1") if is_long else Decimal("-1")

        header = f"{self._prefix} | {emoji} {side_label} ENTERED — {symbol}"
        if signal_class is not None:
            quality = "Optimal" if signal_class == 1 else "Acceptable"
            header += f"  [{quality} · Class {signal_class}]"
        lines = [header, ""]

        body = [
            row("Symbol:", symbol),
            row("Side:", f"{side_label} ({'BUY' if is_long else 'SELL'} to open)"),
            row("Entry:", fmt_price_auto(entry_price)),
            row("Size:", f"{fmt_amount_auto(amount, entry_price)}  ({fmt_price(notional)})"),
            row("Leverage:", f"{leverage}x  (Margin: {fmt_price(margin)})"),
        ]

        risk_lines: list[str] = []
        sl_distance: Decimal | None = None
        if sl_price:
            sl_pct = (sl_price - entry_price) / entry_price * 100 * direction
            sl_distance = abs(entry_price - sl_price)
            sl_risk = sl_distance * amount
            risk_pct_of_account = (sl_risk / balance * 100) if balance and balance > 0 else None
            risk_suffix = (
                f"  ({float(risk_pct_of_account):.2f}% of acct)" if risk_pct_of_account is not None else ""
            )
            risk_lines.append(
                row(
                    "SL (Hard):",
                    f"{fmt_price_auto(sl_price)}  ({fmt_pct(sl_pct)})  "
                    f"Risk: {fmt_pnl(-sl_risk)}{risk_suffix}",
                )
            )

        if soft_sl_price is not None and soft_sl_price != sl_price:
            soft_pct = (soft_sl_price - entry_price) / entry_price * 100 * direction
            risk_lines.append(
                row("SL (Soft):", f"{fmt_price_auto(soft_sl_price)}  ({fmt_pct(soft_pct)})  candle-close exit")
            )

        if lock_profit_price is not None:
            lock_pct = (lock_profit_price - entry_price) / entry_price * 100 * direction
            risk_lines.append(
                row(
                    "Lock Profit:",
                    f"{fmt_price_auto(lock_profit_price)}  ({fmt_pct(lock_pct)})  → SL moves here after TP1",
                )
            )

        if risk_lines:
            body += ["", *risk_lines]

        if tp_prices:
            tp_lines: list[str] = []
            total_expected_reward = Decimal("0")
            remaining_alloc = Decimal("1")
            for label in ("TP1", "TP2", "TP3"):
                tp_p = tp_prices.get(label)
                if not tp_p:
                    continue
                diff_pct = (tp_p - entry_price) / entry_price * 100 * direction
                gross_reward = abs(tp_p - entry_price) * amount
                rr = (abs(tp_p - entry_price) / sl_distance) if sl_distance else None

                alloc_frac: Decimal | None = None
                if tp_allocations:
                    raw = tp_allocations.get(label)
                    if raw is not None:
                        alloc_frac = Decimal(str(raw))

                # Allocation is % of *remaining* contracts per the partial close model
                alloc_of_initial: Decimal | None = None
                if alloc_frac is not None:
                    alloc_of_initial = remaining_alloc * alloc_frac
                    remaining_alloc -= alloc_of_initial
                    total_expected_reward += gross_reward * alloc_of_initial

                parts = [fmt_price_auto(tp_p), f"({fmt_pct(diff_pct)})"]
                if rr is not None:
                    parts.append(f"{float(rr):.2f}R")
                if alloc_of_initial is not None:
                    parts.append(f"close {float(alloc_of_initial) * 100:.0f}%")
                parts.append(f"+{float(gross_reward):,.2f}")

                tp_lines.append(row(f"{label}:", "  ".join(parts)))

            if tp_lines:
                body += ["", *tp_lines]

            if total_expected_reward > 0 and sl_distance:
                expected_risk = sl_distance * amount
                rr_weighted = (
                    total_expected_reward / expected_risk if expected_risk > 0 else None
                )
                suffix = f"  ({float(rr_weighted):.2f}R weighted)" if rr_weighted else ""
                body.append(
                    row(
                        "Exp. Reward:",
                        f"+{float(total_expected_reward):,.2f}{suffix}",
                    )
                )

        if reason:
            body += ["", row("Reason:", reason)]

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

        if risk_per_trade_pct is not None:
            body += ["", row("Risk/Trade:", f"{float(risk_per_trade_pct) * 100:.2f}%")]

        if entry_fee is not None:
            body.append(row("Entry Fee:", f"{fmt_pnl(-entry_fee)}"))

        if balance is not None:
            body.append(row("Balance:", f"{fmt_price(balance)}"))

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
            # total_fees is pro-rated (entry_fee_slice + exit_fee), so partial
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
        lines = [f"{self._prefix} | 💸 FUNDING — {symbol}", ""]
        body = [
            row("Rate:", f"{fmt_pct(rate * 100)}  (longs pay)"),
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

    def _send(self, message: str, *, topic_id: int | None = None) -> None:
        try:
            self._bot.send_message(message, chat_id=self._chat_id, message_thread_id=topic_id)
        except Exception:
            logger.exception("TelegramNotifier: failed to send message")
