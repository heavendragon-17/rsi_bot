# Core V2.1 — Automated Execution Decisions

> Status: user-approved implementation policy recorded on 2026-08-20.
> This is the durable source of truth for future Core V2.1 execution work.
> The policy is documented but not yet implemented in the runtime.

---

## Scope and precedence

These decisions apply to future Core V2.1 backtesting, Telegram messages, paper
trading, and live automated execution. They supplement the approved Core V2.1
signal-qualification rules; they do not change the behavior of older strategies.

When implementing Core V2.1:

- Use this document for execution and accounting semantics.
- Use the existing shared `config.yaml` settings where this document explicitly
  says to inherit older-strategy behavior.
- Do not silently replace an unresolved item with an unrelated runtime default.

---

## Locked decisions

### 1. Take-profit ladder

Core V2.1 uses three target levels:

```text
TP1 = 1R
TP2 = 2R
TP3 = 3R
```

The target multiples are locked. The percentages of the position closed at
TP1, TP2, and TP3 are a separate concern; see **Unresolved details** below.

### 2. Strategy stop-loss trigger

For a long position, the Core V2.1 strategy stop is triggered only when a fully
closed M15 candle satisfies:

```text
M15 Close < current M15 EMA21
```

This is a strict comparison. An intrabar wick below EMA21 does not by itself
trigger the strategy stop. Any separate exchange-level disaster stop is not
defined by this decision and must not be confused with the strategy stop.

### 3. Reference, simulated, and live entry prices

The system must retain distinct price concepts instead of using one field for
all purposes.

| Price | Required use |
|---|---|
| `reference_entry` | Signal candle close. Use for strategy validation and the levels shown in Telegram. |
| `simulated_fill` | Next candle open adjusted adversely by configured slippage. Use for P&L backtests. |
| `actual_fill` | Exchange-reported fill in live operation. Persist the actual/weighted-average fill and use it for live accounting. |

For a long simulated entry:

```text
simulated_fill = next_M15_open * (1 + configured_slippage_rate)
```

The existing close-as-fill model remains acceptable only for verifying Core
V2.1 signal logic. It must be labelled as signal-validation mode and must not be
presented as execution-realistic P&L.

Realized R must use `simulated_fill` in P&L simulation and `actual_fill` in live
operation. It must never use `reference_entry` merely because that is the price
shown in Telegram. The implementation must retain the original reference
values as well, so the displayed signal can be audited without rewriting it
after execution.

### 4. Position sizing and account risk

Use the same position-sizing and risk settings as the older strategies, read
from the same `config.yaml` file. Do not introduce a second V2-only risk block.

The implementation should consume the existing shared settings, including as
applicable:

- `risk.risk_per_trade_pct`
- `risk.max_position_size_pct`
- `risk.use_risk_based_sizing`
- `risk.use_initial_capital_for_risk`
- `risk.min_sl_distance_pct`
- `risk.leverage`

Before live execution, tests must verify the units used by these fields. The
current code interprets percentage-named fields as fractions, so comments and
configured values must not be treated as proof of their numeric meaning.

### 5. Maximum holding behavior

Use the same maximum-holding settings and behavior as the older strategies,
from the same `config.yaml` strategy configuration. Do not create duplicate
Core V2.1 maximum-holding defaults.

The future signal-mode configuration resolver must pass these strategy settings
through; the current resolver does not yet forward per-strategy
`strategy_params`.

### 6. Overlapping signals

Overlapping Core V2.1 signals are not permitted.

The minimum implementation invariant is one active Core V2.1 advisory/position
per strategy and symbol. While one is active, another actionable Core V2.1
entry for that same symbol must not be emitted or opened. Candle processing and
the setup state machine must continue so re-arm state remains deterministic.

This records the existing one-position-per-symbol interpretation. A stricter
portfolio-wide rule allowing only one active Core V2.1 position across all
symbols would require an explicit additional decision.

### 7. Hyperliquid charges

Use the standard-user Hyperliquid rate, not a VIP, promotional, or assumed
discounted tier.

- Live accounting must store exchange-reported fees and funding whenever they
  are available.
- A backtest must record the numeric rate and effective date used, because the
  standard rate can change.
- Slippage remains the configured execution assumption; it is not a
  Hyperliquid fee rate.
- Do not hard-code a numeric Hyperliquid rate unless it has been verified for
  the standard user tier at implementation time.

---

## Accounting and audit fields

Future trade records must preserve at least:

```text
signal_candle_close_time
reference_entry
reference_stop_or_initial_risk_basis
reference_tp1
reference_tp2
reference_tp3
simulated_fill          # backtest, when applicable
actual_fill             # live, when applicable
exit_signal_time
exit_fill
configured_slippage_rate
fees
funding
gross_pnl
net_pnl
gross_realized_r
net_realized_r
```

This separation is required to reproduce the Telegram signal, the simulated
trade, and the live exchange result independently.

---

## Acceptance checks for future implementation

1. Telegram shows the signal candle close as `reference_entry`.
2. Signal-validation replay may use close-as-fill but labels the result as
   non-execution P&L.
3. Execution backtests enter at the next M15 open with adverse configured
   slippage.
4. Live trades persist the exchange-reported fill rather than the signal close.
5. Realized R changes when the simulated/actual fill differs from the reference
   entry.
6. A wick below M15 EMA21 without a close below it does not trigger the strategy
   stop.
7. A fully closed M15 candle with `Close < EMA21` does trigger the strategy
   stop path.
8. A second actionable signal cannot overlap an active V2 position for the same
   symbol.
9. Position sizing and maximum holding read the shared older-strategy settings
   from `config.yaml`.
10. Hyperliquid backtests identify the standard-user rate and effective date;
    live records use exchange-reported charges.

---

## Unresolved details — do not infer silently

The following were not numerically defined by the decisions above:

- Position allocation percentages at TP1, TP2, and TP3. The `1R/2R/3R`
  decision defines target prices, not close fractions.
- Whether reported canonical realized R is gross or net of fees and funding.
  Store both until this is explicitly selected.
- Whether a separate disaster/flash-crash stop is required in addition to the
  M15 EMA21 candle-close strategy stop.
- Whether “no overlapping signals” should later become portfolio-wide instead
  of the recorded per-strategy-and-symbol rule.
- The numeric Hyperliquid standard-user fee schedule. Resolve it from an
  authoritative exchange source at implementation time.
