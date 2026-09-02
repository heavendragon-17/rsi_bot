# Core V2.1 signal contract

> Status: reviewer-approved signal logic implemented as a signal-only strategy.
> Strategy version: `2.1`.
> Locked config version: `core-v2.1-locked-2026-08-20`.
> Automated order placement is outside this implementation.

Core V2.1 is a long-only, closed-candle setup scanner. It evaluates one
altcoin M15 candle at a time, using the latest fully closed Alt H1, BTC H1,
and BTC H4 context that was available when that M15 candle closed. Its public
outputs are advisory setup events; `WAIT_FOR_PULLBACK` is not a trade.

The pure implementation is under
`app/trading/strategy/core_v2_1/`. Historical replay and live signal
coordination call the same evaluator rather than maintaining separate copies
of the trading rules.

## Locked universe and routing

BTC is a benchmark only. It must never enter the trade-candidate loop.

| Venue | Trade candidates | Source instrument convention |
|---|---|---|
| Binance USD-M Futures | ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT, DOGEUSDT, ADAUSDT, LINKUSDT, AVAXUSDT, SUIUSDT, HYPEUSDT, ZECUSDT, LITUSDT, AAVEUSDT, NEARUSDT, XMRUSDT, TAOUSDT, ENAUSDT, WLDUSDT, FARTCOINUSDT, JTOUSDT, INJUSDT, UNIUSDT, ONDOUSDT, GRASSUSDT | CCXT linear-perpetual form, such as `ETH/USDT:USDT` |
| Hyperliquid Perp | PUMP | `PUMP/USDC:USDC` |
| Binance USD-M Futures | BTCUSDT, reference-only | `BTC/USDT:USDT` |

Venue is part of market identity. `PUMP` must not be substituted with a
Binance `PUMPUSDT` instrument or merged with a same-named market from another
venue.

## Timeframes and indicators

| Input | Required indicators |
|---|---|
| Alt M15 | EMA21, EMA200, ATR14, RSI21, EMA9 of RSI21, WMA45 of RSI21 |
| Alt H1 | RSI21, EMA9 of RSI21, WMA45 of RSI21 |
| BTC H1 | Close, EMA21, RSI21, EMA9 of RSI21, WMA45 of RSI21 |
| BTC H4 | RSI21, EMA9 of RSI21, WMA45 of RSI21 |

The dedicated indicator implementation does not call an optional TA library.
Its deterministic seed contract is:

- RSI21: simple mean of the first 21 gains and losses, followed by Wilder
  recursion. A flat input produces RSI 50; zero average loss produces RSI 100;
  zero average gain produces RSI 0.
- ATR14: simple mean of the first 14 true ranges, followed by Wilder
  recursion. The first true range is `High - Low`.
- EMA: recursive `alpha = 2 / (period + 1)`, seeded by the first finite input.
- WMA45: rolling weights `1..45`, with the latest observation carrying weight
  45.
- Warm-up values remain unavailable. Evaluation starts only when every
  required value in every timeframe is finite and ATR14 is positive.

No RSI14 or H2 input is part of Core V2.1.

## Locked feature anchor

Recursive indicators are seeded from one absolute source-history anchor, not
from a moving exchange-retention window:

| Contract | Value |
|---|---|
| Anchor version | `core-v2.1-anchor-2026-06-29T11:15Z-v1` |
| M15 source open | `2026-06-29T11:15:00Z` (`2026-06-29 18:15` in stored UTC+7 CSV form) |
| First complete M15 close | `2026-06-29T11:30:00Z` |
| First complete H1 close | `2026-06-29T13:00:00Z` |
| First complete H4 close | `2026-06-29T16:00:00Z` |

The first H1/H4 rows are the first UTC-aligned native buckets wholly covered
by the source anchor. Replay derives those buckets from M15; the live runtime
requests the venue-native H1/H4 series from the same first-complete-close
boundary. Both paths must produce the same point-in-time evaluator inputs.

The anchor version is persisted with runtime state and emitted in replay
metadata. Losing the anchored prefix, changing the seed convention, or moving
the anchor requires an explicit strategy-version and state/data migration. A
normal refresh or restart must never silently re-anchor EMA, RSI, or ATR.

## Point-in-time contract

For an Alt M15 candle closing at time `T`:

- the current and prior M15 inputs must be fully closed and contiguous;
- Alt H1 and BTC H1 must equal the latest expected UTC H1 close at `T`;
- BTC H4 must equal the latest expected UTC four-hour close at `T`;
- no input may close after `T`;
- an H1/H4 candle closing exactly at `T` is available at `T`;
- if that exact dependency is missing, evaluation fails closed instead of
  falling back to a context one full interval old;
- missed M15 candles are processed chronologically. A gap, duplicate, or
  backward timestamp is an integrity error.

For repository CSVs, `timestamp` is a timezone-naive UTC+7 candle **open**.
The replay loader subtracts seven hours, attaches UTC, and adds the timeframe
to create the canonical close timestamp. H1 and H4 buckets are derived from
complete M15 buckets anchored to UTC epoch boundaries. Partial buckets are
discarded. The live runtime consumes native venue candles but enforces the
same exact expected close for every dependency.

## Fresh bullish crossover

A fresh cross exists only when both conditions hold:

```text
Previous M15 RSI_EMA9 <= Previous M15 RSI_WMA45
Current  M15 RSI_EMA9 >  Current  M15 RSI_WMA45
```

Remaining above WMA45 is not a fresh cross. One fresh cross can create only
one cycle.

## Mandatory cross-candle filters

All groups below must pass on the fresh-cross candle.

| Group | Exact conditions |
|---|---|
| Alt M15 trend | `Close > EMA21`; `EMA21 > EMA200`; current EMA21 `>` EMA21 exactly three M15 bars ago |
| Alt M15 momentum | `RSI21 > 50`; `RSI21 > RSI_EMA9`; `RSI21 > RSI_WMA45` |
| Alt H1 | `RSI21 > 50`; `RSI_EMA9 >= RSI_WMA45` |
| BTC H1 regime | `Close > EMA21`; `RSI21 > 50`; `RSI_EMA9 >= RSI_WMA45` |
| BTC H4 alignment | `RSI21 > RSI_EMA9 > RSI_WMA45` |

The current `RSI_EMA9 > RSI_WMA45` relation is already guaranteed by the
fresh cross. Failure of any mandatory filter silently rejects and consumes
the cycle. The symbol becomes disarmed.

## Anti-chase classification

On a mandatory-filter-passing cross candle:

```text
DistanceATR    = (Close - EMA21) / ATR14
SignalRangeATR = (High - Low) / ATR14
```

`A_PLUS_LONG` requires both `DistanceATR <= 1.0` and
`SignalRangeATR <= 1.5`. It consumes the cycle immediately.

If either strict failure occurs—`DistanceATR > 1.0` or
`SignalRangeATR > 1.5`—the output is `WAIT_FOR_PULLBACK`. Its reason list
contains `PRICE_EXTENDED_FROM_EMA21`, `SIGNAL_CANDLE_TOO_LARGE`, or both.
The cross candle is WAIT bar zero and is not one of the four monitored bars.

The displayed zone on any WAIT observation is:

```text
[current EMA21, current EMA21 + 0.25 * current ATR14]
```

The evaluator recalculates this zone from the current candle. It does not
freeze the cross-candle EMA21 or ATR14.

## WAIT state machine

Only the next four fully closed M15 candles are eligible: WAIT #1 through
WAIT #4. Each is processed in this exact priority:

1. cancellation;
2. pullback confirmation;
3. expiry.

### Cancellation

The WAIT is cancelled if any condition is true:

- Alt M15 `Close < EMA21`;
- Alt M15 `RSI21 < 50`;
- Alt M15 `RSI_EMA9 <= RSI_WMA45`;
- BTC H1 `Close <= EMA21`;
- BTC H1 `RSI21 <= 50`;
- BTC H1 `RSI_EMA9 < RSI_WMA45`;
- BTC H4 `RSI21 <= RSI_EMA9`;
- BTC H4 `RSI_EMA9 <= RSI_WMA45`.

Alt H1 losing confirmation does not itself cancel a WAIT, but Alt H1 must be
bullish again before a pullback can confirm.

### Pullback confirmation

After cancellation checks pass, the current M15 candle must touch:

```text
Low <= EMA21 + 0.25 * ATR14
```

It must then satisfy all of the following:

- M15 `Close > EMA21`;
- M15 `EMA21 > EMA200`;
- M15 `RSI21 > 50`;
- M15 `RSI_EMA9 > RSI_WMA45`;
- M15 `RSI21 > RSI_EMA9`;
- Alt H1 `RSI21 > 50` and `RSI_EMA9 >= RSI_WMA45`;
- BTC H1 remains bullish under the mandatory BTC H1 rule;
- BTC H4 remains strictly aligned.

Pullback confirmation does not re-require the EMA21 three-bar slope or either
anti-chase threshold.

### Expiry

If WAIT #4 neither cancels nor confirms, it emits `WAIT_EXPIRED` on that
candle. There is no WAIT #5.

## Re-arm and terminal-candle rule

An A+, rejection, pullback, cancellation, or expiry consumes the cycle and
leaves the symbol disarmed. A subsequent fully closed M15 candle with
`RSI_EMA9 <= RSI_WMA45` re-arms the symbol. It must then wait for a new fresh
cross.

A WAIT terminal candle does not also re-arm the cycle, even when the
cancellation reason is `RSI_EMA9 <= RSI_WMA45`. Re-arm is evaluated on a
subsequent closed M15 candle. Re-arm, rejection, quiet scans, and intermediate
WAIT progress are audit decisions but not Telegram events.

## Advisory reference levels

For `A_PLUS_LONG`, use the cross candle. For `PULLBACK_LONG`, use the
confirmation candle:

```text
Reference Entry = candle Close
Reference Stop  = candle Low - 0.25 * ATR14
1R              = Reference Entry - Reference Stop
TP1             = Reference Entry + 1R
TP2             = Reference Entry + 2R
TP3             = Reference Entry + 3R
```

These are auditable reference levels, not exchange orders or guaranteed
fills. The exact formula can produce a zero or negative reference stop for
extreme or synthetic inputs; the pure signal layer deliberately does not add
an execution floor or mutate the reviewer-approved math. An execution layer
must validate market-specific price constraints before any future order work.
`WAIT_FOR_PULLBACK` has a preferred zone but no confirmed Entry, Stop, or TP
values. The separate execution policy is documented in
[Core V2.1 execution decisions](core-v2-1-execution-decisions.md).

## Public event policy

The signal runtime may notify exactly these setup lifecycle events:

- `A_PLUS_LONG`;
- `WAIT_FOR_PULLBACK`;
- `PULLBACK_LONG`;
- `WAIT_CANCELLED`;
- `WAIT_EXPIRED`.

Every event contains the strategy symbol, venue, source M15 close time,
deterministic event identity, reason codes where relevant, and either advisory
trade levels or the preferred zone. No-signal, rejected, re-armed, and WAIT
progress decisions remain silent but are retained in replay/runtime audit
state.

## Durability boundary

The signal-only coordinator persists:

- immutable anchored raw candles keyed by `(venue, instrument, timeframe,
  close_time)`;
- typed Core state;
- last processed M15 close;
- every transition decision;
- deduplicated advisory events;
- the first-install bootstrap suppression watermark; and
- a retryable notification outbox.

State advancement and event/outbox insertion occur in one SQLite transaction.
A new installation bootstraps historical state silently. On an empty SQLite
database, the canonical validated Hyperliquid PUMP M15 CSV supplies the locked
anchor before the public API tail is reconciled; Hyperliquid's rolling API
window alone is not an acceptable moving seed after it no longer reaches that
anchor. If the file is absent while the public API still covers the full
anchor-through-tail range, public hydration may supply it; otherwise startup
fails closed. A restart resumes after the persisted close and processes every
missing M15 candle in order. Bootstrap
feature computation is linear/precomputed over each unique market series and
must remain semantically identical to uninterrupted chronological evaluation.
Readiness uses the indicator contract itself: an RSI21/EMA9/WMA45 bundle needs
66 closed candles, while M15 evaluation needs 67 so both the current and
previous RSI bundles are complete. These exact boundaries keep live bootstrap
aligned with the replay instead of imposing a later arbitrary warm-up.

Identical duplicate candles are idempotent. Conflicting duplicate source or
persisted rows are integrity failures and stop processing; they are never
silently resolved by keeping the first or last value. Event identity includes
the strategy version, venue, symbol, close time, and event type, so a restart
cannot create a second logical event for the same transition.

Outbox delivery is durable and at-least-once. Workers claim rows with expiring
lease tokens; a stale worker cannot acknowledge or reschedule a row after a
new owner reclaims it. A crash after Telegram accepts a message but before
SQLite records `sent` can still produce a recognizable duplicate, so every
message carries a short deterministic event tag. This is not an exactly-once
Telegram guarantee.

The coordinator does not place, cancel, or manage exchange orders.
