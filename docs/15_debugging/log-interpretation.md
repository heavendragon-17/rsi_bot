# Log Interpretation

> How to read structlog output and trace signals through the system.

---

## structlog Format

All logs use key=value structured format:

```
2026-02-25 14:30:15 [info] order_placed symbol=BTC/USDT order_type=market side=BUY amount=0.1 order_id=abc123
```

Components: `timestamp [level] event_name key1=value1 key2=value2 ...`

---

## Key Log Fields

| Field | Meaning |
|-------|---------|
| `symbol` | Trading pair (e.g., `BTC/USDT`) |
| `order_id` | Exchange order ID |
| `order_type` | `market`, `limit`, `stop_market` |
| `side` | `BUY` or `SELL` |
| `amount` | Position size |
| `price` | Order price |
| `action` | Strategy action type (`OpenPosition`, `ClosePosition`, etc.) |
| `state` | Context state (`SCANNING`, `CONFIRMING`) |
| `reason` | Exit reason (`STOP_LOSS`, `LOCK_PROFIT`, `CLOSE_BY_CANDLE_SL`) |

---

## Tracing a Signal Through the System

### Entry Flow

```
1. [info] strategy_action   symbol=BTC/USDT action=OpenPosition
2. [info] dispatching_action action=OpenPosition symbol=BTC/USDT
3. [info] calculating_size   balance=10000 risk_pct=0.02 sl_distance=0.015
4. [info] setting_leverage    symbol=BTC/USDT leverage=10
5. [info] order_placed        symbol=BTC/USDT order_type=market side=BUY amount=0.13
6. [info] position_opened     symbol=BTC/USDT entry_price=42150.00 amount=0.13
7. [info] order_placed        symbol=BTC/USDT order_type=stop_market side=SELL (SL)
8. [info] order_placed        symbol=BTC/USDT order_type=limit side=SELL (TP1)
9. [info] order_placed        symbol=BTC/USDT order_type=limit side=SELL (TP2)
10.[info] notification_sent   type=entry symbol=BTC/USDT
```

### TP Hit Flow

```
1. [info] tp_fill_detected    symbol=BTC/USDT tp_level=TP1 order_id=xyz
2. [info] position_updated    symbol=BTC/USDT tp1_hit=True new_amount=0.065
3. [info] sl_moved            symbol=BTC/USDT old_sl=41500 new_sl=42180 (lock profit)
4. [info] notification_sent   type=tp_hit symbol=BTC/USDT
```

### SL Exit Flow

```
1. [info] strategy_action     symbol=BTC/USDT action=ClosePosition reason=CLOSE_BY_CANDLE_SL
2. [info] cancelling_orders   symbol=BTC/USDT
3. [info] order_placed        symbol=BTC/USDT order_type=market side=SELL reduceOnly=True
4. [info] position_closed     symbol=BTC/USDT exit_reason=STOP_LOSS pnl=-150.00
5. [info] notification_sent   type=exit symbol=BTC/USDT
```

### Error Flow

```
1. [error] order_error         symbol=BTC/USDT error=InsufficientFundsError msg="..."
2. [warning] position_drift    symbol=BTC/USDT local=True exchange=False
```

---

## Filtering Tips

```bash
# Filter by symbol
grep "symbol=BTC/USDT" bot.log

# Filter by log level
grep "\[error\]" bot.log
grep "\[warning\]" bot.log

# Filter by event type
grep "order_placed\|order_error" bot.log

# Trace a specific order
grep "order_id=abc123" bot.log

# Watch entry/exit flow
grep "position_opened\|position_closed" bot.log
```
