"""
Order execution and liquidation logic for MockExchange.
Extracted from MockExchange to keep file under 400 lines.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import structlog

from app.core.actions import EXIT_LIQUIDATION, EXIT_STOP_LOSS, SIDE_BUY, SIDE_SELL
from app.core.exceptions import InsufficientFundsError
from app.core.utils import to_decimal

logger = structlog.get_logger()


def execute_order(
    exc,
    symbol: str,
    side: str,
    amount: Decimal,
    exec_price: Decimal,
    timestamp: Any,
    order_type: str = "MARKET",
    exit_reason: str | None = None,
    fee_override: Decimal | None = None,
) -> dict | None:
    """Execute an order against the exchange state (position/margin/balance)."""
    side = (side or SIDE_BUY).upper()
    notional = exec_price * amount
    fee_rate = (
        fee_override
        if fee_override is not None
        else (exc.taker_fee if order_type.upper() in ("MARKET", "STOP_MARKET") else exc.maker_fee)
    )
    fee_cost = notional * fee_rate
    current_signed = exc.positions.get(symbol, Decimal("0"))

    entry_price = None
    hold_secs = None
    pnl = None
    pnl_pct = None
    margin_used = Decimal("0")

    is_opening = (side == "BUY" and current_signed >= 0) or (side == "SELL" and current_signed <= 0)
    if is_opening:
        margin = notional / exc.leverage
        if margin > exc.balance:
            raise InsufficientFundsError(
                f"Insufficient balance for {symbol}. Required: {margin:.2f}, Available: {exc.balance:.2f}"
            )
        exc.balance -= margin
        delta = amount if side == "BUY" else -amount
        exc.positions[symbol] = current_signed + delta
        exc.margin_used[symbol] = exc.margin_used.get(symbol, Decimal("0")) + margin
        exc.entry_times[symbol] = timestamp
        exc.entry_prices[symbol] = exec_price
        margin_used = margin
    else:
        pos_size = abs(current_signed)
        if amount > pos_size * Decimal("1.001"):
            raise InsufficientFundsError(f"Insufficient position for {symbol}: have {pos_size}, want {amount}")
        amount = min(amount, pos_size)
        entry_price = exc.entry_prices.get(symbol)
        entry_time = exc.entry_times.get(symbol)
        close_ratio = amount / pos_size if pos_size > 0 else Decimal("1")
        pos_margin = exc.margin_used.get(symbol, Decimal("0"))
        margin_to_return = pos_margin * close_ratio
        notional = exec_price * amount
        fee_cost = notional * fee_rate
        if entry_price is not None:
            if current_signed < 0:
                gross_pnl = (exec_price - entry_price) * current_signed
                pnl_pct = float((entry_price - exec_price) / entry_price * 100) if entry_price > 0 else 0.0
            else:
                gross_pnl = (exec_price - entry_price) * amount
                pnl_pct = float((exec_price - entry_price) / entry_price * 100) if entry_price > 0 else 0.0
            entry_fee = entry_price * amount * exc.taker_fee
            pnl = float(gross_pnl - entry_fee - fee_cost)
        else:
            pnl = 0.0
        exc.balance += margin_to_return + Decimal(str(pnl or 0))
        delta = amount if side == "BUY" else -amount
        exc.positions[symbol] = current_signed + delta
        exc.margin_used[symbol] = pos_margin - margin_to_return
        hold_secs = calc_hold_duration(entry_time, timestamp)
        if abs(exc.positions.get(symbol, Decimal("0"))) <= Decimal("1e-8"):
            for d in (exc.positions, exc.margin_used, exc.entry_times, exc.entry_prices):
                d.pop(symbol, None)
        margin_used = margin_to_return
        notional = exec_price * amount

    order_id = exc._sim.next_order_id(prefix="mock")
    order = {
        "id": order_id,
        "clientOrderId": f"client_{order_id}",
        "status": "closed",
        "type": order_type.lower(),
        "side": side,
        "symbol": symbol,
        "price": float(exec_price),
        "amount": float(amount),
        "filled": float(amount),
        "remaining": 0.0,
        "cost": float(notional),
        "average": float(exec_price),
        "fee": {"currency": "USDT", "cost": float(fee_cost), "rate": float(fee_rate)},
        "info": {"exit_reason": exit_reason or ""},
        "time": timestamp,
        "notional": float(notional),
        "margin": float(margin_used),
        "leverage": float(exc.leverage),
        "balance_after": float(exc.balance),
        "entry_price": float(entry_price) if entry_price is not None else None,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "hold_duration_seconds": hold_secs,
    }
    exc.trade_history.append(order)
    return order


def check_liquidation(exc, timestamp: Any) -> bool:
    """Check if portfolio should be liquidated and force-close if so."""
    if not exc.positions:
        return False
    used = sum(exc.margin_used.values())
    total_upnl = Decimal("0")
    for symbol, amt in exc.positions.items():
        if amt == 0:
            continue
        entry = exc.entry_prices.get(symbol, Decimal("0"))
        curr = to_decimal(exc.current_prices.get(symbol, {}).get("price", entry))
        total_upnl += (curr - entry) * amt
    equity = exc.balance + used + total_upnl
    if equity <= Decimal("0"):
        logger.warning("portfolio_liquidated", equity=float(equity), timestamp=timestamp)
        for symbol in list(exc.positions.keys()):
            signed = exc.positions.get(symbol, Decimal("0"))
            if signed == 0:
                continue
            exit_side = SIDE_BUY if signed < 0 else SIDE_SELL
            abs_amt = abs(signed)
            price = to_decimal(exc.current_prices.get(symbol, {}).get("price", Decimal("0")))
            if price <= 0:
                price = exc.entry_prices.get(symbol, Decimal("0"))
            try:
                execute_order(
                    exc,
                    symbol,
                    exit_side,
                    abs_amt,
                    price,
                    timestamp,
                    "MARKET",
                    EXIT_LIQUIDATION,
                    fee_override=Decimal("0.005"),
                )
            except Exception as e:
                logger.error("liquidation_error", symbol=symbol, error=str(e))
        exc.balance = Decimal("0")
        return True
    return False


def update_stop_loss(
    exc,
    symbol: str,
    new_trigger_price: Any,
    new_amount: Any = None,
    exit_reason: str | None = None,
) -> bool:
    """Cancel existing SL and place a new one at the given price."""
    new_price = to_decimal(new_trigger_price)
    new_amt = to_decimal(new_amount) if new_amount is not None else None
    current_pos = exc.positions.get(symbol, Decimal("0"))
    exit_side = SIDE_BUY if current_pos < 0 else SIDE_SELL

    sl_ids = [
        oid
        for oid, o in exc._sim.pending_orders.items()
        if o.symbol == symbol and o.side == exit_side and o.order_type in ("stop_market", "stop_loss")
    ]
    for oid in sl_ids:
        exc._sim.cancel_order(oid)

    if not sl_ids and new_amt is None and current_pos == 0:
        return False
    if new_amt is None:
        new_amt = abs(current_pos)
    if new_amt <= 0:
        return False

    result = exc.create_order(
        symbol=symbol,
        order_type="stop_market",
        side=exit_side,
        amount=new_amt,
        params={"stopPrice": new_price, "reduceOnly": True, "exit_reason": exit_reason or EXIT_STOP_LOSS},
    )
    return result is not None


def calc_hold_duration(entry_time: Any, exit_time: Any) -> float | None:
    """Calculate hold duration in seconds between entry and exit timestamps."""
    if entry_time is None or exit_time is None:
        return None
    try:
        if hasattr(entry_time, "timestamp") and hasattr(exit_time, "timestamp"):
            return exit_time.timestamp() - entry_time.timestamp()
        if hasattr(entry_time, "value") and hasattr(exit_time, "value"):
            return (exit_time.value - entry_time.value) / 1e9
    except Exception:
        return None
    return None
