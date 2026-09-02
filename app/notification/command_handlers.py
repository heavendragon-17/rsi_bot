# app/notification/command_handlers.py
"""
Telegram slash command handlers.

Each handler receives the exchange, prefix, send function, and chat_id.
Extracted from TelegramNotifier to keep file sizes under 400 lines.
"""

from __future__ import annotations

import time
from decimal import Decimal
from html import escape

import structlog

from app.core.interfaces import IExchange
from app.notification.formatting import fmt_duration, fmt_pnl, mono, row

logger = structlog.get_logger(__name__)

# Start time recorded at module load for session uptime
_SESSION_START = time.time()


def handle_status(exchange: IExchange, prefix: str, send, chat_id: str) -> None:
    """Full status: session summary + position cards with SL/TP levels."""
    balance_data = exchange.fetch_balance()
    usdt_total = balance_data.get("total", {}).get("USDT", 0.0)
    positions = exchange.fetch_positions()

    running_status = "⏸ PAUSED" if getattr(exchange, "is_paused", lambda: False)() else "▶️ RUNNING"

    # Session P&L
    state = getattr(exchange, "state", None)
    initial_bal = float(getattr(state, "initial_balance", usdt_total)) if state else usdt_total
    session_pnl = usdt_total - initial_bal
    session_pct = (session_pnl / initial_bal * 100) if initial_bal else 0.0
    uptime = time.time() - _SESSION_START

    lines = [
        f"{prefix} | 📊 STATUS",
        "",
        row("Bot State:", running_status),
        row("Balance:", f"${usdt_total:,.2f}"),
        row("Session P&L:", f"{fmt_pnl(Decimal(str(session_pnl)))} ({session_pct:+.2f}%)"),
        row("Uptime:", fmt_duration(uptime)),
        row("Positions:", f"{len(positions)} open"),
    ]

    if positions and state:
        for p in positions:
            sym = p["symbol"]
            entry_price = p.get("entryPrice", 0.0)
            contracts = p.get("contracts", 0.0)
            upnl = p.get("unrealizedPnl", 0.0)
            emoji = "🟢" if upnl >= 0 else "🔴"

            lines += ["", f"── {sym} LONG ──────────"]
            lines.append(row("Entry:", f"${entry_price:,.2f}"))
            lines.append(row("Size:", f"{contracts:.4f}  (${entry_price * contracts:,.2f})"))
            lines.append(row("uPnL:", f"{emoji} {fmt_pnl(Decimal(str(upnl)))}"))

            # Hold duration from SimPosition
            sim_pos = state.positions.get(sym) if hasattr(state, "positions") else None
            if sim_pos and getattr(sim_pos, "opened_at", 0) > 0:
                hold = time.time() - sim_pos.opened_at
                lines.append(row("Hold:", fmt_duration(hold)))

            # SL/TP levels from pending orders
            sim = getattr(exchange, "_sim", None)
            if sim:
                for o in sim.get_pending_orders(sym):
                    if o.side == "SELL":
                        if o.order_type == "stop_market" and o.trigger_price:
                            sl_pct = (float(o.trigger_price) - entry_price) / entry_price * 100 if entry_price else 0
                            lines.append(row("SL (Hard):", f"${float(o.trigger_price):,.2f}  ({sl_pct:+.2f}%)"))

                # TP levels with hit/pending status
                if sim_pos:
                    tp_orders: dict[str, Decimal] = {}
                    for o in sim.get_pending_orders(sym):
                        if o.side == "SELL" and o.order_type == "limit" and o.price:
                            tp_orders[f"TP{len(tp_orders) + 1}"] = o.price

                    tp_hit_map = {"TP1": getattr(sim_pos, "tp1_hit", False), "TP2": getattr(sim_pos, "tp2_hit", False)}
                    for label in ("TP1", "TP2", "TP3"):
                        tp_p = tp_orders.get(label)
                        is_hit = tp_hit_map.get(label, False)
                        if tp_p:
                            tp_pct = (float(tp_p) - entry_price) / entry_price * 100 if entry_price else 0
                            marker = "✅" if is_hit else "⏳"
                            lines.append(row(f"{marker} {label}:", f"${float(tp_p):,.2f}  ({tp_pct:+.2f}%)"))
    elif positions:
        # Fallback for non-sim exchanges
        for p in positions:
            upnl = p.get("unrealizedPnl", 0.0)
            emoji = "🟢" if upnl >= 0 else "🔴"
            lines.append(
                f"{emoji} {p['symbol']} | Size: {p['contracts']:.4f} | PnL: {fmt_pnl(Decimal(str(upnl)))}"
            )

    send(mono("\n".join(lines)), chat_id=chat_id)


def handle_history(exchange: IExchange, prefix: str, send, chat_id: str) -> None:
    """Last 10 trades: dense single-line with PnL, R-multiple, entry→exit prices."""
    state = getattr(exchange, "state", None)
    if not state:
        return

    trades = state.closed_trades[-10:]

    if not trades:
        send(mono(f"{prefix} | 📜 HISTORY\n\nNo closed trades yet."), chat_id=chat_id)
        return

    lines = [f"{prefix} | 📜 HISTORY (Last {len(trades)})", ""]
    for t in reversed(trades):
        emoji = "🟢" if t.pnl_net >= 0 else "🔴"
        r_str = f"{float(t.r_multiple):+.1f}R" if t.r_multiple else ""
        entry_s = f"{float(t.entry_price):,.0f}"
        exit_s = f"{float(t.exit_price):,.0f}"
        lines.append(
            f"{emoji} {t.symbol} | {fmt_pnl(t.pnl_net)} ({r_str}) | {entry_s}→{exit_s} ({t.exit_reason})"
        )

    send(mono("\n".join(lines)), chat_id=chat_id)


def handle_report(exchange: IExchange, prefix: str, send, chat_id: str) -> None:
    """Full performance dashboard with win rate, risk metrics, exit breakdown."""
    state = getattr(exchange, "state", None)
    if not state:
        return

    trades = state.closed_trades
    total = len(trades)

    if total == 0:
        send(mono(f"{prefix} | 📈 REPORT\n\nNo trades yet."), chat_id=chat_id)
        return

    # Core stats
    wins = [t for t in trades if t.pnl_net > 0]
    losses = [t for t in trades if t.pnl_net <= 0]
    win_count = len(wins)
    loss_count = len(losses)
    winrate = (win_count / total) * 100

    total_pnl = sum(t.pnl_net for t in trades)
    gross_pnl = sum(t.pnl_gross for t in trades)
    total_fees = sum(t.fees_paid for t in trades)
    total_funding: Decimal = sum((t.funding_paid for t in trades), Decimal("0"))

    initial_bal = getattr(state, "initial_balance", Decimal("10000"))
    return_pct = (total_pnl / initial_bal * 100) if initial_bal else Decimal("0")

    # Risk metrics
    gross_wins = sum(t.pnl_net for t in wins) if wins else Decimal("0")
    gross_losses = abs(sum(t.pnl_net for t in losses)) if losses else Decimal("0")
    profit_factor = (gross_wins / gross_losses) if gross_losses else Decimal("0")

    r_values = [t.r_multiple for t in trades if t.r_multiple]
    avg_r = sum(r_values) / len(r_values) if r_values else Decimal("0")
    expectancy = total_pnl / total if total else Decimal("0")

    best = max(trades, key=lambda t: t.pnl_net)
    worst = min(trades, key=lambda t: t.pnl_net)

    # Exit breakdown
    exit_counts: dict[str, int] = {}
    for t in trades:
        exit_counts[t.exit_reason] = exit_counts.get(t.exit_reason, 0) + 1

    # Time analytics
    hold_times = [t.closed_at - t.opened_at for t in trades if t.opened_at > 0 and t.closed_at > t.opened_at]
    avg_hold = sum(hold_times) / len(hold_times) if hold_times else 0.0

    # Message 1: Performance + Costs
    msg1 = [
        f"{prefix} | 📈 REPORT (1/2)",
        "",
        "── Performance ─────────────",
        row("Trades:", str(total)),
        row("Win Rate:", f"{winrate:.1f}%  ({win_count}W / {loss_count}L)"),
        row("Net P&L:", fmt_pnl(total_pnl)),
        row("Gross P&L:", fmt_pnl(gross_pnl)),
        row("Return:", f"{float(return_pct):+.2f}%"),
        "",
        "── Costs ───────────────────",
        row("Total Fees:", fmt_pnl(-total_fees)),
    ]
    if total_funding != Decimal("0"):
        msg1.append(row("Funding:", fmt_pnl(-total_funding)))

    send(mono("\n".join(msg1)), chat_id=chat_id)

    # Message 2: Risk + Exits + Time
    msg2 = [
        f"{prefix} | 📈 REPORT (2/2)",
        "",
        "── Risk ────────────────────",
        row("Profit Factor:", f"{float(profit_factor):.2f}" if profit_factor else "N/A"),
        row("Avg R:", f"{float(avg_r):+.2f}R"),
        row("Expectancy:", f"{fmt_pnl(expectancy)} / trade"),
        row("Best Trade:", fmt_pnl(best.pnl_net)),
        row("Worst Trade:", fmt_pnl(worst.pnl_net)),
        "",
        "── Exits ───────────────────",
    ]

    # Group exits: TPs first, then SLs, then others
    tp_keys = sorted(k for k in exit_counts if k.startswith("TP"))
    sl_keys = sorted(k for k in exit_counts if "SL" in k)
    other_keys = sorted(k for k in exit_counts if k not in tp_keys and k not in sl_keys)

    exit_parts = [f"{k}: {exit_counts[k]}" for k in tp_keys + sl_keys + other_keys]
    for i in range(0, len(exit_parts), 3):
        msg2.append("  ".join(exit_parts[i : i + 3]))

    if avg_hold > 0:
        msg2 += ["", row("Avg Hold:", fmt_duration(avg_hold))]

    send(mono("\n".join(msg2)), chat_id=chat_id)


def handle_reset(exchange: IExchange, prefix: str, send, chat_id: str) -> None:
    """Reset balance and trades (sim mode only)."""
    if hasattr(exchange, "state") and hasattr(exchange.state, "reset"):
        exchange.state.reset()
        send(
            mono(f"{prefix} | 🔄 RESET\n\nBot state (balance and trades) has been reset."),
            chat_id=chat_id,
        )
    else:
        send(
            mono(f"{prefix} | ⚠️ RESET FAILED\n\nReset not supported in current mode."),
            chat_id=chat_id,
        )


def handle_help(prefix: str, send, chat_id: str) -> None:
    """Show available commands."""
    lines = [
        f"{prefix} | ❓ HELP",
        "",
        "/status         Balance, positions, SL/TP levels",
        "/history        Last 10 closed trades",
        "/report         Full performance dashboard",
        "/reset          Reset balance & trades (sim)",
        "/topics         Full strategy/topic inventory (signal)",
        "",
        "/force_deploy   Trigger immediate deploy",
        "/deploy_status  Current deploy state",
        "/cancel_deploy  Cancel pending deploy",
        "/bot_version    Version, uptime, SHA",
        "",
        "/test_signal    Post a fake entry to every strategy topic (signal mode)",
    ]
    send(mono("\n".join(lines)), chat_id=chat_id)


def handle_topics(
    topics: list[tuple[str, int | None, str]], prefix: str, send, chat_id: str
) -> None:
    """Show the complete signal strategy/topic inventory."""
    lines = [
        f"{prefix} | 🗂 TOPICS",
        "",
        "Strategy/topic inventory:",
    ]
    if topics:
        for name, topic_id, status in topics:
            if topic_id is None:
                lines.append(f"• {escape(name)} — {escape(status)}")
            else:
                lines.append(
                    f"• {escape(name)} — topic ID: {topic_id} ({escape(status)})"
                )
    else:
        lines.append("No configured topics.")

    send(mono("\n".join(lines)), chat_id=chat_id)
