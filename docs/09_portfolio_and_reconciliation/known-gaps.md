# Known Gaps & Limitations

> Honest documentation of what the system does NOT currently handle. These are known trade-offs, not bugs.

---

## Position Drift

**Gap**: Runtime reconciliation is candle-driven rather than continuous, and
only positions already tracked locally are reconciled.

**Impact**: An out-of-band close can remain stale until the next closed-candle
loop. A manually opened exchange position that the bot has never tracked is
not adopted automatically.

**Current mitigation**:
- `sync_from_exchange()` runs at startup and after each closed-candle runner
  iteration
- `sync_tp_fills()` polls TP order statuses periodically
- Orphan position detection logs warnings on startup

**Missing**:
- No account/user-data stream for immediate fill and position updates
- No independent wall-clock heartbeat between candle closes
- No automatic adoption or closure of untracked exchange positions

**Recommendation**: Add an authenticated account-update stream, plus an
independent periodic full-account reconciliation that alerts on untracked
positions instead of silently adopting them.

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

**Gap**: Manual closes are reconciled on the next closed-candle loop, but
manual opens, replacement orders, and leverage changes are not incorporated
into local strategy state.

**Impact**: The bot can temporarily manage a position that no longer exists,
or miss a position/order that was created manually.

**Current mitigation**: `sync_from_exchange()` cleans tracked positions at
startup and after closed candles. Startup orphan detection logs exchange
positions that are absent locally.

**Recommendation**: Subscribe to authenticated order/position updates and
alert on any manual mutation that cannot be reconciled safely.

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
| Position drift | Medium | Wait for/trigger reconciliation and verify exchange | Medium (add account stream + heartbeat) |
| Funding fees | Low | Check exchange history manually | Low (add tracking) |
| No portfolio risk limit | Medium | Conservative position sizing | Medium (add aggregate limits) |
| No live trade record | Low | Use Telegram history | Medium (add persistence) |
| Manual intervention | Medium | Avoid manual changes; verify exchange after emergencies | Medium (add account stream) |
| Fill reconciliation | Medium | Monitor exchange manually | High (add robust order tracking) |
