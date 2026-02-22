# Error Handling

> Error flows, categories, crash recovery, and SSE error events.

---

## Error Flow

```
Engine crash / bad params / CSV parse error
        │
        ▼
Worker process catches exception
  → publishes SSE "error" event with message
  → marks Run as status="failed" in DB with error message
        │
        ▼
Frontend receives SSE "error"
  → shows toast notification (sonner) — immediate feedback
  → sets isRunning = false
        │
        ▼
Failed run appears in History
  → status badge shows "failed" (red)
  → clicking the run shows error message detail
  → user can delete or retry with modified config
```

## Error Categories

| Category | Example | Handling |
|----------|---------|----------|
| Data missing | CSV file not found | Pre-flight check in `runBacktest()`, show DataPrepModal |
| Data invalid | CSV parse error, wrong columns | Backend validation, SSE error event |
| Config invalid | Invalid param combination | Backend validation, HTTP 400 |
| Engine crash | Unhandled exception in strategy | try/catch in worker, SSE error + DB mark |
| Timeout | SSE connection drops after 300s | Frontend reconnects or shows stale warning |

## Custom Exception Hierarchy

Defined in `app/core/exceptions.py`. Each exchange adapter catches its own library errors and re-raises as these:

```
ExchangeError              — Base for all exchange errors
├── InsufficientFundsError — Not enough margin/balance
├── OrderRejectedError     — Exchange rejected order
├── OrderNotFoundError     — Order ID not found
├── ConnectionError        — Network/API connectivity
└── RateLimitError         — API rate limit exceeded
PositionError              — Position management errors
```

## Live Bot Error Recovery

| Situation | Recovery |
|-----------|----------|
| Missing config | Log error + exit |
| Telegram init failure | Fall back to `NullNotifier` |
| Leverage setting failure | Log warning, continue |
| Position cleanup failure | Log and continue |
| WebSocket disconnect | Auto-reconnect after 2s |
| Order placement failure | Log error, skip trade |
| Balance sync failure | Log warning, use last known |
| Indicator computation error | Fallback to manual calculation |

## Backtest Crash Recovery

On server startup:

```sql
UPDATE runs
SET status = 'failed',
    completed_at = CURRENT_TIMESTAMP,
    error_message = 'Server restart — run interrupted'
WHERE status = 'running';
```

No checkpoint/resume complexity.

## Frontend Error Handling

- **Toast notifications**: sonner library for immediate feedback
- **SSE error events**: Parsed and displayed with error detail
- **API errors**: `ApiError` class in `ui/src/api/client.ts`
- **Stale detection**: SSE connection timeout warning after 300s
