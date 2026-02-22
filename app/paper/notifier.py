# app/paper/notifier.py
"""
PaperTelegramNotifier
=====================
Sends rich paper trading messages to Telegram and handles /paper_* commands.

All messages are prefixed with "📄 PAPER" and use HTML parse mode
(bold header + monospace table) as specified in SPEC lines 1169–1323.

Command handlers (registered by runner via set_command_handler or polling):
  /paper_status   — balance, open positions, unrealized P&L
  /paper_reset    — 30-second confirmation flow, wipes state
  /paper_toggle   — pause / resume signal execution
  /paper_history  — last 20 closed trades
  /paper_winrate  — win rate, R-multiple, exit breakdown stats
"""
from __future__ import annotations

import logging
import os
import threading
import time
from decimal import Decimal
from typing import TYPE_CHECKING, Dict, Optional

if TYPE_CHECKING:
    from app.paper.state import ClosedTrade, PaperOrder, PaperPosition, PaperTradeState

logger = logging.getLogger(__name__)

_PREFIX = "📄 PAPER"


def _mono(text: str) -> str:
    return f"<pre>{text}</pre>"


def _bold(text: str) -> str:
    return f"<b>{text}</b>"


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


class PaperTelegramNotifier:
    """
    Formats and dispatches all paper trading Telegram messages.
    Also owns the /paper_* command dispatch loop (polling mode).
    """

    def __init__(self, config: dict):
        from app.services.notification.telegram_bot import TelegramBot

        paper_cfg = config.get("paper_sim", {})
        token_override = paper_cfg.get("telegram_token", "").strip()

        if token_override:
            os.environ.setdefault("PAPER_TELEGRAM_BOT_TOKEN", token_override)
            token_env = "PAPER_TELEGRAM_BOT_TOKEN"
        else:
            token_env = "TELEGRAM_BOT_TOKEN"

        self._bot = TelegramBot(token_env=token_env)
        self._config = config
        # Destination channel: paper_sim.chat_id in config, or None → falls back to TELEGRAM_CHAT_ID
        self._chat_id: Optional[str] = paper_cfg.get("chat_id", "").strip() or None
        # Used by /paper_reset confirmation flow
        self._pending_reset: Optional[float] = None  # timestamp of last /paper_reset
        self._reset_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Fill events
    # ------------------------------------------------------------------

    def on_entry(
        self,
        order: "PaperOrder",
        position: "PaperPosition",
        state: "PaperTradeState",
    ) -> None:
        leverage = self._config.get("risk", {}).get("leverage", 1)
        notional = position.entry_price * position.amount
        margin = notional / Decimal(str(leverage))
        sl_order = None
        tp_prices: Dict[str, Optional[Decimal]] = {}
        with state.lock:
            for oid in [position.sl_order_id]:
                if oid and oid in state.pending_orders:
                    sl_order = state.pending_orders[oid]
            for tp_label, tp_oid in position.tp_order_ids.items():
                if tp_oid in state.pending_orders:
                    o = state.pending_orders[tp_oid]
                    tp_prices[tp_label] = o.price

        sl_price = sl_order.stop_price if sl_order else None
        sl_pct = (
            ((sl_price - position.entry_price) / position.entry_price * 100)
            if sl_price
            else None
        )
        sl_risk = (
            abs(position.entry_price - sl_price) * position.amount if sl_price else None
        )

        lines = [
            f"{_PREFIX} | 🟢 LONG ENTERED — {order.symbol}",
            "",
        ]
        body_lines = [
            _row("Symbol:", order.symbol),
            _row("Side:", "LONG"),
            _row("Entry:", _fmt_price(position.entry_price)),
            _row("Size:", f"{float(position.amount):.4f}  ({_fmt_price(notional)})"),
            _row("Leverage:", f"{leverage}x  (Notional: {_fmt_price(notional)})"),
            "",
        ]
        if sl_price:
            body_lines.append(
                _row("SL (Hard):", f"{_fmt_price(sl_price)}  ({_fmt_pct(sl_pct)})  Risk: {_fmt_pnl(sl_risk)}")
            )
        for label in ("TP1", "TP2", "TP3"):
            tp_p = tp_prices.get(label)
            if tp_p:
                diff_pct = (tp_p - position.entry_price) / position.entry_price * 100
                reward = abs(tp_p - position.entry_price) * position.amount
                body_lines.append(
                    _row(f"{label}:", f"{_fmt_price(tp_p)}  (+{float(diff_pct):.2f}%)  Reward: +{float(reward):,.2f}")
                )
        if position.lock_profit_price:
            body_lines.append(
                _row("Lock Profit:", f"{_fmt_price(position.lock_profit_price)}  → SL moves to entry on tick hit")
            )
        body_lines += [
            "",
            _row("Balance:", f"{_fmt_price(state.balance)}  (margin used: {_fmt_price(margin)})"),
        ]
        lines.append(_mono("\n".join(body_lines)))
        self._send("\n".join(lines))

    def on_fill(
        self,
        order: "PaperOrder",
        position: Optional["PaperPosition"],
        trade: Optional["ClosedTrade"],
        state: "PaperTradeState",
    ) -> None:
        """Called after any SL/TP fill."""
        if order.order_type == "stop_market":
            self._send_sl_hit(order, trade, state)
        elif order.order_type in ("limit", "market") and order.reduce_only:
            self._send_tp_hit(order, position, trade, state)

    def _send_tp_hit(
        self,
        order: "PaperOrder",
        position: Optional["PaperPosition"],
        trade: Optional["ClosedTrade"],
        state: "PaperTradeState",
    ) -> None:
        exit_reason = trade.exit_reason if trade else "TP?"
        label = exit_reason  # TP1, TP2, TP3
        fill_p = order.fill_price or Decimal("0")

        is_final = trade is not None
        header = f"✅ {label} HIT — {order.symbol} LONG"
        if is_final:
            header += " (CLOSED)"

        lines = [f"{_PREFIX} | {header}", ""]
        body = [
            _row("Fill:", _fmt_price(fill_p)),
            _row("Closed:", f"{float(order.amount):.4f}  ({_fmt_price(fill_p * order.amount)})"),
        ]
        if trade:
            body += [
                _row("Gross P&L:", f"{_fmt_pnl(trade.pnl_gross)}"),
                _row("Fee (maker):", f"{_fmt_pnl(-trade.fees_paid)}  (0.02%)"),
                _row("Net P&L:", f"{_fmt_pnl(trade.pnl_net)}"),
            ]
        if is_final and trade:
            body += [
                "",
                "─" * 33,
                _row("Total Trade P&L:", f"{_fmt_pnl(trade.pnl_net)}  ({float(trade.r_multiple):.2f}R)"),
                _row("Fees Paid:", f"{_fmt_pnl(-trade.fees_paid)}"),
            ]

        session_pnl = state.session_pnl()
        body += [
            "",
            _row("Session P&L:", f"{_fmt_pnl(session_pnl)}  |  Balance: {_fmt_price(state.balance)}"),
        ]
        lines.append(_mono("\n".join(body)))
        self._send("\n".join(lines))

    def _send_sl_hit(
        self,
        order: "PaperOrder",
        trade: Optional["ClosedTrade"],
        state: "PaperTradeState",
    ) -> None:
        fill_p = order.fill_price or Decimal("0")
        exit_reason = (trade.exit_reason if trade else "HARD_SL").replace("_", " ")
        emoji = "🛑" if "HARD" in exit_reason else "🟡"

        lines = [f"{_PREFIX} | {emoji} {exit_reason} HIT — {order.symbol} LONG", ""]
        body = [
            _row("Fill:", _fmt_price(fill_p)),
            _row("Closed:", f"{float(order.amount):.4f}  ({_fmt_price(fill_p * order.amount)})"),
        ]
        if trade:
            body += [
                _row("Gross P&L:", f"{_fmt_pnl(trade.pnl_gross)}"),
                _row("Fee (taker):", f"{_fmt_pnl(-trade.fees_paid)}  (0.05%)"),
                _row("Net P&L:", f"{_fmt_pnl(trade.pnl_net)}"),
                "",
                "─" * 33,
                _row("Trade P&L:", f"{_fmt_pnl(trade.pnl_net)}  ({float(trade.r_multiple):.2f}R)"),
            ]
        session_pnl = state.session_pnl()
        body.append(_row("Session P&L:", f"{_fmt_pnl(session_pnl)}  |  Balance: {_fmt_price(state.balance)}"))
        lines.append(_mono("\n".join(body)))
        self._send("\n".join(lines))

    def on_funding(
        self,
        symbol: str,
        rate: Decimal,
        payment: Decimal,
        balance: Decimal,
    ) -> None:
        lines = [f"{_PREFIX} | 💸 FUNDING — {symbol}", ""]
        rate_pct = rate * 100
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
                f"{_PREFIX} | ⏸ PAUSED\n"
                "Signal execution suspended. Open positions still monitored.\n"
                "Use /paper_toggle to resume."
            )
        else:
            msg = f"{_PREFIX} | ▶️ RESUMED\nSignal execution active."
        self._send(msg)

    # ------------------------------------------------------------------
    # Command handlers (called externally by a Telegram polling loop
    # or webhook handler)
    # ------------------------------------------------------------------

    def handle_command(self, command: str, state: "PaperTradeState") -> None:
        """Dispatch a /paper_* command string to the appropriate handler."""
        cmd = command.strip().lower().split()[0]
        dispatch = {
            "/paper_status": self._cmd_status,
            "/paper_toggle": self._cmd_toggle,
            "/paper_history": self._cmd_history,
            "/paper_winrate": self._cmd_winrate,
            "/paper_reset": self._cmd_reset_init,
            "/paper_reset confirm": self._cmd_reset_confirm,
        }
        # Handle confirm variant
        if command.strip().lower().startswith("/paper_reset confirm"):
            handler = dispatch["/paper_reset confirm"]
        else:
            handler = dispatch.get(cmd)

        if handler:
            handler(state)
        else:
            logger.debug(f"Unknown paper command: {command!r}")

    def _cmd_status(self, state: "PaperTradeState") -> None:
        with state.lock:
            lines = [f"{_PREFIX} | SESSION STATUS", ""]
            body = [
                _row("Balance:", _fmt_price(state.balance)),
                _row("Session P&L:", _fmt_pnl(state.session_pnl())),
                _row("Paused:", "Yes" if state.is_paused else "No"),
                "",
            ]
            if state.positions:
                body.append("Open Positions:")
                for sym, pos in state.positions.items():
                    body.append(f"  {sym}  {float(pos.amount):.4f}  @ {_fmt_price(pos.entry_price)}")
            else:
                body.append("No open positions.")
            lines.append(_mono("\n".join(body)))
        self._send("\n".join(lines))

    def _cmd_toggle(self, state: "PaperTradeState") -> None:
        with state.lock:
            state.is_paused = not state.is_paused
            paused = state.is_paused
        self.on_toggle(paused)

    def _cmd_history(self, state: "PaperTradeState") -> None:
        with state.lock:
            trades = list(state.closed_trades)[-20:]
        if not trades:
            self._send(f"{_PREFIX} | No closed trades this session.")
            return
        lines = [f"{_PREFIX} | TRADE HISTORY (last {len(trades)})", ""]
        body = []
        for t in reversed(trades):
            pnl_str = _fmt_pnl(t.pnl_net)
            r_str = f"{float(t.r_multiple):.2f}R"
            body.append(f"{t.symbol}  {_fmt_price(t.entry_price)}→{_fmt_price(t.exit_price)}  {t.exit_reason}  {pnl_str}  {r_str}")
        lines.append(_mono("\n".join(body)))
        self._send("\n".join(lines))

    def _cmd_winrate(self, state: "PaperTradeState") -> None:
        with state.lock:
            trades = list(state.closed_trades)
            open_count = len(state.positions)
            balance = state.balance
            fees = state.total_fees_paid
            funding = state.total_funding_paid

        total = len(trades)
        if total == 0:
            self._send(f"{_PREFIX} | No closed trades yet.")
            return

        winners = [t for t in trades if t.pnl_net > 0]
        win_rate = len(winners) / total * 100
        avg_r = sum(t.r_multiple for t in trades) / total
        best = max(trades, key=lambda t: t.r_multiple)
        worst = min(trades, key=lambda t: t.r_multiple)

        from collections import Counter
        exit_counts = Counter(t.exit_reason for t in trades)

        gross_pnl = sum(t.pnl_net for t in trades) + fees + funding
        net_pnl = sum(t.pnl_net for t in trades)
        net_pct = net_pnl / state.initial_balance * 100

        lines = [f"{_PREFIX} | SESSION STATS", ""]
        body = [
            _row("Trades:", f"{total} closed  ({open_count} open)"),
            _row("Win Rate:", f"{win_rate:.1f}%  ({len(winners)}W / {total - len(winners)}L)"),
            "",
            "Exit Breakdown:",
        ]
        for reason, cnt in sorted(exit_counts.items()):
            pct = cnt / total * 100
            body.append(f"  {reason:<12} {cnt} trades  ({pct:.1f}%)")
        body += [
            "",
            _row("Avg R-multiple:", f"+{float(avg_r):.2f}R"),
            _row("Best trade:", f"+{float(best.r_multiple):.2f}R  ({best.symbol} {best.exit_reason})"),
            _row("Worst trade:", f"{float(worst.r_multiple):.2f}R  ({worst.symbol} {worst.exit_reason})"),
            "",
            _row("Session P&L:", f"{_fmt_pnl(gross_pnl)}  (gross)"),
            _row("Fees paid:", f"{_fmt_pnl(-fees)}"),
            _row("Funding paid:", f"{_fmt_pnl(-funding)}"),
            _row("Net P&L:", f"{_fmt_pnl(net_pnl)}  (+{float(net_pct):.2f}%)"),
            "",
            _row("Balance:", f"{_fmt_price(state.initial_balance)} → {_fmt_price(balance)}"),
        ]
        lines.append(_mono("\n".join(body)))
        self._send("\n".join(lines))

    def _cmd_reset_init(self, state: "PaperTradeState") -> None:
        with state.lock:
            trade_count = len(state.closed_trades)
            session_pnl = state.session_pnl()
            init_bal = state.initial_balance

        with self._reset_lock:
            self._pending_reset = time.time()

        msg = (
            f"⚠️ PAPER RESET CONFIRMATION\n"
            f"This will wipe all paper trades and reset balance to {_fmt_price(init_bal)}.\n"
            f"Current session: {trade_count} trades, Net P&L: {_fmt_pnl(session_pnl)}\n\n"
            f"Reply /paper_reset confirm within 30 seconds to proceed."
        )
        self._send(msg)

    def _cmd_reset_confirm(self, state: "PaperTradeState") -> None:
        with self._reset_lock:
            ts = self._pending_reset
            if ts is None or (time.time() - ts) > 30:
                self._pending_reset = None
                self._send("Reset cancelled (30-second window expired).")
                return
            self._pending_reset = None

        with state.lock:
            trade_count = len(state.closed_trades)
            net_pnl = state.session_pnl()
            total = len(state.closed_trades)
            winners = [t for t in state.closed_trades if t.pnl_net > 0]
            win_rate = (len(winners) / total * 100) if total else 0
            state.reset()
            init_bal = state.initial_balance

        msg = (
            f"✅ Paper account reset.\n"
            f"Session summary: {trade_count} trades | Net P&L: {_fmt_pnl(net_pnl)} | Win rate: {win_rate:.0f}%\n"
            f"Balance reset to {_fmt_price(init_bal)}. Fresh session started."
        )
        self._send(msg)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _send(self, message: str) -> None:
        try:
            self._bot.send_message(message, chat_id=self._chat_id)
        except Exception:
            logger.exception("PaperTelegramNotifier: failed to send message")
