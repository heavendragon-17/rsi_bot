# Notifications

> **Location**: `app/notification/`
> **Interface**: `INotifier` in `app/core/interfaces.py`

## Architecture

```
main.py
  └── NotificationService(TelegramNotifier | NullNotifier, mode=...)
        ├── injected into → create_exchange()  → SimExchange
        ├── injected into → MultiSymbolRunner  → PortfolioManager (per thread)
        └── injected into → MultiSymbolRunner  → SimFundingScheduler
```

All notification calls are **non-blocking** — every method enqueues work into
`NotificationWorker` (a bounded daemon queue, max 100 items, drop-on-full policy).
Trading threads are never blocked by Telegram latency.

---

## Key Files

| File                                                | Role                                                                            |
| --------------------------------------------------- | ------------------------------------------------------------------------------- |
| `app/core/interfaces.py` — `INotifier`              | Abstract contract. Scalar params only.                                          |
| `app/notification/notification_service.py` | Wraps `INotifier` + `NotificationWorker`. Single instance created in `main.py`. |
| `app/notification/telegram_notifier.py`    | Implements `INotifier` with HTML formatting and mode-aware prefix.              |
| `app/notification/null_notifier.py`        | No-op implementation. Used when Telegram is disabled or fails.                  |
| `app/notification/notification_worker.py`  | Background daemon thread. Dispatches queue items to the underlying notifier.    |
| `app/notification/telegram_bot.py`         | Low-level HTTP sender (`requests` → Telegram Bot API). Not an `INotifier`.      |
| `app/notification/command_handlers.py`     | Handler logic for Telegram bot commands (extracted from notifier).               |
| `app/notification/deploy_commands.py`      | Registers bot commands with the Telegram Bot API on startup.                     |
| `app/notification/formatting.py`           | Shared HTML formatting helpers for notification messages.                        |

---

## INotifier Interface

```python
class INotifier(ABC):
    def send_message(self, message: str) -> None: ...

    def on_entry(
        self, symbol, side, entry_price, amount,
        sl_price=None, tp_prices=None, leverage=1, balance=None,
        indicators=None, entry_fee=None,
        # Rich signal metadata (populated by NotificationDispatcher):
        reason=None, soft_sl_price=None, lock_profit_price=None,
        tp_allocations=None, signal_class=None, risk_per_trade_pct=None,
    ) -> None: ...

    def on_fill(
        self, symbol, exit_reason, fill_price, amount,
        pnl_gross=None, pnl_net=None, fees=None,
        r_multiple=None, remaining_amount=None, balance=None,
        entry_price=None, total_fees=None,
        hold_duration=None, return_pct=None,
    ) -> None: ...

    def on_error(self, context: str, error: str) -> None: ...
    def on_funding(self, symbol, rate, payment, balance) -> None: ...
    def on_toggle(self, is_paused: bool) -> None: ...
```

**Design rules:**

- All parameters are **scalars** (str, Decimal, int, bool, Optional[...]).
  No exchange-adapter-specific state objects (no `SimTradeState`, no `PaperOrder`).
- All implementations must be **safe to call from any thread** and **never raise**.

---

## Who Fires Each Event

| Event                    | Sim mode                                                                   | Live / Paper mode                                                                                                      |
| ------------------------ | -------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `on_entry`               | `NotificationDispatcher` (fired by `TradeExecutor` **after** SL/TP are placed so the card can render them) | `NotificationDispatcher` (same path)                                          |
| `on_fill` (SL / TP)      | `SimExchange.execute_fill_from_result` → `sim_notifications.emit_notifications` (exact fill price) | Not fired — hard SL fills externally on Binance; see [known-gaps.md](../09_portfolio_and_reconciliation/known-gaps.md) |
| `on_fill` (manual close) | `SimExchange.execute_fill_from_order` (via `create_order`)                 | `PortfolioManager._handle_full_sell`                                                                                   |
| `on_funding`             | `SimFundingScheduler` (every 8 h)                                          | Not fired                                                                                                              |
| `on_toggle`              | `SimExchange.is_paused` setter (if wired)                                  | Not fired                                                                                                              |
| `on_error`               | Available for any caller                                                   | Available for any caller                                                                                               |

**Duplication guard**: `SimExchange` sets `_fires_entry_notification = False`
(entry notifications come from `NotificationDispatcher` so SL/TP are already in
the card) and `_fires_fill_notification = True` (fills happen on tick, not on
signal, so sim owns them). `NotificationDispatcher` checks these flags and
skips firing any event the exchange already owns.

---

## Mode Prefixes

| Mode    | Prefix      |
| ------- | ----------- |
| `live`  | 🤖 LIVE     |
| `paper` | 🧪 TESTNET  |
| `sim`   | 📄 SIM      |
| `mock`  | 🔬 BACKTEST |

---

## Message Format Examples

### Entry (on_entry)

```
📄 SIM | 🟢 LONG ENTERED — API3/USDT  [Acceptable · Class 2]

Symbol:        API3/USDT
Side:          LONG (BUY to open)
Entry:         $0.33740
Size:          31,746  ($10,711.11)
Leverage:      10x  (Margin: $1,071.11)

SL (Hard):     $0.32710  (-3.02%)  Risk: -321.33  (3.00% of acct)
SL (Soft):     $0.33403  (-1.00%)  candle-close exit
Lock Profit:   $0.33761  (+0.06%)  → SL moves here after TP1

TP1:           $0.34082  (+1.01%)  1.00R  close 100%  +108.57
Exp. Reward:   +108.57  (1.00R weighted)

Reason:        NO-RETEST BUY (spread=3.39 >= 2.5)

────────────────────────────
RSI EMA9:      42.20
RSI WMA45:     38.81
Spread:        3.39
Above EMA21:   1

Risk/Trade:    2.00%
Entry Fee:     -5.36
Balance:       $9,333.77
```

**Dynamic precision**: prices (`Entry`, `SL`, `TP1/2/3`, `Lock Profit`, `Fill`,
`Exit`) and sizes (`Size`, `Closed`) are rendered by `fmt_price_auto` and
`fmt_amount_auto` in `app/notification/formatting.py`. Decimals are derived from
two `%` knobs at the top of that module:

```python
PRICE_PRECISION_PCT = 0.01   # last digit ≈ 0.01% of price — tight
SIZE_PRECISION_PCT  = 1.0    # last digit ≈ 1% of amount — readable
```

So BTC at $100,123 shows 2 dp, API3 at $0.33 shows 5 dp, ZIL at $0.007 shows 7
dp; BTC size 0.003427 shows 5 dp, API3 size 31,746 shows 0 dp. USD-denominated
values (`notional`, `Margin`, `Risk`, `Balance`, `Gross/Net P&L`, `Fees`) always
use 2 dp via `fmt_price`. Tune the knobs to change every card in one place; no
`fmt_*_precise` is used in notifications (those helpers are reserved for
copy-trade reports outside this flow).

### SL Hit (on_fill, exit_reason="HARD_SL" or "MOVED_SL")

`HARD_SL` is reported when the original stop_market fires. `MOVED_SL` is
reported when the stop has been relocated (lock-profit / trailing) and
subsequently fires — such exits are always at-or-above entry by construction.

```
📄 SIM | 🛑 HARD SL HIT — BTC/USDT LONG

Entry:         $100,000.00
Exit:          $97,000.00
Closed:        0.003427  ($332.42)
Gross P&L:     -10.28
Total Fees:    -0.09  (entry -0.05, exit -0.05 taker)
Net P&L:       -10.37

─────────────────────────────────
Trade P&L:     -10.37  (-1.00R)
Return:        -3.09%
Hold:          22m

Balance:       $9,989.63
```

### TP Hit (on_fill, exit_reason="TP1", remaining_amount=0)

```
📄 SIM | ✅ TP1 HIT — XLM/USDT LONG (CLOSED)

Entry:         $0.1747
Exit:          $0.1759
Closed:        190,476  ($33,276.52)
Gross P&L:     +225.09
Total Fees:    -23.18  (entry -16.52, exit -6.66 maker)
Net P&L:       +201.91

─────────────────────────────────
Trade P&L:     +201.91  (1.00R)
Return:        +0.61%
Hold:          30m

Balance:       $10,298.93
```

`Net P&L` is the true lifecycle net: `gross − entry_fee_slice − exit_fee`.
The entry fee is pro-rated for partial closes so the displayed value matches
what the balance actually gained across the trade.

### Funding (on_funding)

```
📄 SIM | 💸 FUNDING — BTC/USDT

Rate:          +0.01%  (longs pay)
Payment:       -0.10

Balance:       $9,974.79
```

---

## Configuration

### Environment Variables (`.env`)

| Variable             | Required     | Description                            |
| -------------------- | ------------ | -------------------------------------- |
| `TELEGRAM_BOT_TOKEN` | For Telegram | Bot token from @BotFather              |
| `TELEGRAM_CHAT_ID`   | For Telegram | Channel or user ID to send messages to |

### config.yaml

```yaml
bot:
  telegram_enabled: true # false → NullNotifier, no Telegram calls
```

---

## Setup Guide

1. Create a bot via [@BotFather](https://t.me/BotFather): `/newbot` → copy the token
2. Find your chat ID: message [@userinfobot](https://t.me/userinfobot) or
   `https://api.telegram.org/bot<TOKEN>/getUpdates` after sending the bot a message
3. Add to `.env`:
   ```
   TELEGRAM_BOT_TOKEN=1234567890:ABC...
   TELEGRAM_CHAT_ID=-100123456789
   ```
4. Set `telegram_enabled: true` in `config.yaml`

---

## Telegram Commands

The `TelegramBot` supports efficient "long-polling" to receive commands without blocking the trading threads. It uses the `getUpdates` API with a timeout to instantly react to commands while using negligible resources.

The following commands are wired up via `notification_service.attach_exchange(exchange)` and handled by `TelegramNotifier`:

| Command    | Action                                                                                                                |
| ---------- | --------------------------------------------------------------------------------------------------------------------- |
| `/status`  | Shows bot state (`▶️ RUNNING` or `⏸ PAUSED`), current total USDT balance, and all open positions with unrealized PnL. |
| `/history` | Shows the last 10 closed trades, their net PnL, exit reason (e.g., TP1, HARD_SL), and amount.                         |
| `/winrate` | Shows total trades, wins, losses, and the overall win rate percentage.                                                |
| `/report`  | Shows lifetime metrics: net PnL, gross PnL, total fees paid, and total funding paid.                                  |
| `/reset`   | **DANGEROUS**: Clears all closed trades and resets the bot's standard balance. This is primarily for paper/sim mode.  |

To add a new command:

1. Define a handler method in `TelegramNotifier` (e.g., `_handle_mycmd(self, chat_id: str)`).
2. Register it in `start_command_polling()` dictionary mapping (`callbacks = {"/mycmd": self._handle_mycmd}`).

---

## Adding a New Notification Channel

See [docs/workflows/add-notifier.md](../workflows/add-notifier.md) for the step-by-step guide.
Summary: implement `INotifier`, pass an instance to `NotificationService(your_notifier, mode=...)`.

---

## Telegram Topic Routing (signal mode)

`send_message()` accepts an optional keyword-only `topic_id: int | None` param
that flows through `NotificationService` → `NotificationWorker` → the concrete
notifier → `TelegramBot.send_message(..., message_thread_id=topic_id)`. When
set, Telegram posts the message into that forum topic inside the configured
supergroup; when `None` (live-bot default), the message goes to the main chat.

```python
# Signal bot — route per-strategy:
ns.send_message("🟢 LONG BTC/USDT  (RSIN#042) …", topic_id=42)

# Signal bot — route to the shared debug topic:
ns.send_message("[debug] ⏰ RSIN#042 expired …", topic_id=99)

# Live bot (unchanged):
ns.send_message("🤖 RSI Bot Started")
```

### Routing table (signal mode, per spec §10)

| Event                                     | Topic                            |
|-------------------------------------------|----------------------------------|
| 🟢 Entry signal                           | strategy's `telegram_topic_id`   |
| 🛑 Mechanical SL hit                      | strategy's `telegram_topic_id`   |
| 🎯 Mechanical TP hit                      | strategy's `telegram_topic_id`   |
| 🔚 Strategy-emitted exit                  | strategy's `telegram_topic_id`   |
| 📉 SL moved / ⚖️ Partial close             | strategy's `telegram_topic_id`   |
| ⚠ Shutdown broadcast (per strategy)       | strategy's `telegram_topic_id`   |
| ⏰ VP age expiry                           | `telegram.debug_topic_id`        |
| ⚠ Invariant violation (invalid action)    | `telegram.debug_topic_id`        |
| ⚠ Strategy thread dead after N failures   | `telegram.debug_topic_id`        |

### Implementation notes

* Signal-bot messages are built by pure templates in
  `app/signal/signal_formatter.py` and sent via `send_message()` — they are
  **plain text** (no HTML, no parse_mode escaping needed) so user-facing
  strings like `strategy_name` and `symbol` cannot cause Telegram markup
  injection.
* The typed events (`on_entry`, `on_fill`, `on_error`, `on_funding`,
  `on_toggle`) deliberately do **not** carry a `topic_id`. They are the
  live-bot surface and always post to the main chat.
* `NullNotifier` and `TelegramNotifier` both implement
  `send_message(msg, *, topic_id=None)`. The kwarg-only form prevents
  accidental positional misuse (e.g. confusing `topic_id` with `chat_id`).

---

## Troubleshooting

| Symptom                             | Cause                                        | Fix                                                                               |
| ----------------------------------- | -------------------------------------------- | --------------------------------------------------------------------------------- |
| No Telegram messages at all         | `telegram_enabled: false` or missing token   | Check config + `.env`                                                             |
| `TelegramBot` init error on startup | `TELEGRAM_BOT_TOKEN` env var missing         | Add to `.env`, falls back to `NullNotifier`                                       |
| Messages delayed                    | `NotificationWorker` queue backed up         | Normal under load — queue drains async                                            |
| Duplicate on_entry messages         | Exchange and dispatcher both fire            | Check `_fires_entry_notification` flag — sim should leave it `False` so only the dispatcher fires after SL/TP are placed |
| Entry card missing SL/TP lines      | Exchange fires the entry notification *before* SL/TP orders are placed | Set `_fires_entry_notification = False` on the exchange so `NotificationDispatcher.notify_entry` fires at the end of `TradeExecutor._handle_entry_signal` |
| No SL notifications in live mode    | Hard SL fills on exchange without PM polling | Known gap — see [known-gaps.md](../09_portfolio_and_reconciliation/known-gaps.md) |
