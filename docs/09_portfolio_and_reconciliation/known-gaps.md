# Known Gaps & Limitations

> Honest documentation of what the system does NOT currently handle. These are known trade-offs, not bugs.

---

## Position Drift

**Gap**: No periodic exchange state sync during runtime.

**Impact**: If a WebSocket disconnect occurs during an order fill, or if the exchange processes an order that the bot's HTTP response misses, the bot's in-memory position state can diverge from the exchange's actual state.

**Current mitigation**:
- `sync_from_exchange()` on startup reconciles state
- `sync_tp_fills()` polls TP order statuses periodically
- Orphan position detection logs warnings on startup

**Missing**:
- No periodic full reconciliation loop during runtime
- No heartbeat check comparing local position vs exchange position
- No automatic recovery from mid-session drift

**Recommendation**: Implement a periodic reconciliation task (e.g., every 60 seconds) that calls `fetch_positions()` and compares against `self.positions`.

---

## Funding Fee Tracking

**Gap**: Binance perpetual futures charge/pay funding every 8 hours. These are NOT tracked by the bot.

**Impact**: Funding payments affect the exchange balance but are invisible to the bot. Long-held positions in a strong trend may accumulate significant funding costs/income that are not reflected in any internal PnL reporting.

**Current state**: Funding fees are implicitly included in the balance (exchange deducts/adds them), but there is no record of individual funding payments.

**Recommendation**: Subscribe to `@markPrice@arr` WebSocket stream or poll `GET /fapi/v1/income` to track funding events.

---

## No Portfolio-Level Risk Limit

**Gap**: No cap on total exposure across all symbols.

**Impact**: With multi-symbol trading, it's possible to have 5 positions each using 50% of balance (with leverage), exceeding available margin and risking liquidation.

**Current mitigation**: `max_position_size_pct` caps individual trade size, and `risk_per_trade_pct` controls risk per trade, but neither limits aggregate exposure.

**Recommendation**: Add portfolio-level guards:
- Maximum total margin utilization percentage
- Maximum number of concurrent positions
- Correlation-aware exposure limits

---

## No Historical Trade Record (Live Mode)

**Gap**: In live mode, closed trades are not persisted to a database. Only backtest results are stored in SQLite.

**Impact**: No way to review historical live performance, generate reports, or audit past trades except through Telegram notification history and exchange trade history.

**Recommendation**: Add a trades table for live mode, or export trade events to a log file/database.

---

## Manual Exchange Intervention

**Gap**: If a user manually closes a position, places orders, or modifies leverage on the exchange (via Binance web/app), the bot's local state becomes stale.

**Impact**: Bot may try to manage a position that no longer exists, or miss a position that was manually opened.

**Current mitigation**: `sync_from_exchange()` on startup cleans up stale positions, but mid-session manual intervention is not detected.

**Recommendation**: Implement a periodic position sync, or subscribe to order/position update WebSocket streams.

---

## No Fill Reconciliation Loop

**Gap**: If an HTTP response for `create_order()` is lost (network timeout), the order may have been placed on the exchange but the bot doesn't know the order ID.

**Impact**: Orphan orders on the exchange that the bot doesn't track. Could result in unexpected fills.

**Current mitigation**: Exchange exception handling retries on transient errors, but doesn't reconcile after total response loss.

**Recommendation**: After order placement timeout, query `fetch_open_orders()` to find the order by symbol/side/amount.

---

## Summary Table

| Gap | Severity | Workaround | Fix Complexity |
|-----|----------|------------|----------------|
| Position drift | High | Restart bot to re-sync | Medium (add periodic sync) |
| Funding fees | Low | Check exchange history manually | Low (add tracking) |
| No portfolio risk limit | Medium | Conservative position sizing | Medium (add aggregate limits) |
| No live trade record | Low | Use Telegram history | Medium (add persistence) |
| Manual intervention | Medium | Don't manually intervene | Medium (add WebSocket sync) |
| Fill reconciliation | Medium | Monitor exchange manually | High (add robust order tracking) |
