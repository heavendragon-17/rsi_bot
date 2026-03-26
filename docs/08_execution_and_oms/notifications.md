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
    ) -> None: ...

    def on_fill(
        self, symbol, exit_reason, fill_price, amount,
        pnl_gross=None, pnl_net=None, fees=None,
        r_multiple=None, remaining_amount=None, balance=None,
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
| `on_entry`               | `SimExchange._execute_fill` (exact candle-open fill price, includes SL/TP) | `PortfolioManager._handle_buy_signal` (signal price approximation)                                                     |
| `on_fill` (SL / TP)      | `SimExchange._execute_fill` (exact fill price)                             | Not fired — hard SL fills externally on Binance; see [known-gaps.md](../09_portfolio_and_reconciliation/known-gaps.md) |
| `on_fill` (manual close) | `SimExchange._execute_fill` (via `create_order`)                           | `PortfolioManager._handle_full_sell`                                                                                   |
| `on_funding`             | `SimFundingScheduler` (every 8 h)                                          | Not fired                                                                                                              |
| `on_toggle`              | `SimExchange.is_paused` setter (if wired)                                  | Not fired                                                                                                              |
| `on_error`               | Available for any caller                                                   | Available for any caller                                                                                               |

**Duplication guard**: `SimExchange` sets `_fires_entry_notification = True` and
`_fires_fill_notification = True`. `PortfolioManager` checks these flags and
skips its own fire to avoid duplicate messages in sim mode.

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
📄 SIM | 🟢 LONG ENTERED — BTC/USDT

Symbol:        BTC/USDT
Side:          LONG
Entry:         $100,000.00
Size:          0.0100  ($1,000.00)
Leverage:      10x  (Margin: $100.00)

SL (Hard):     $95,000.00  (-5.00%)  Risk: 50.00
TP1:           $105,000.00  (+5.00%)  Reward: +50.00
TP2:           $110,000.00  (+10.00%)  Reward: +100.00

Balance:       $9,950.00
```

### SL Hit (on_fill, exit_reason="HARD_SL")

```
📄 SIM | 🛑 HARD SL HIT — BTC/USDT LONG

Fill:          $94,800.00
Closed:        0.0100  ($948.00)
Gross P&L:     -52.00
Fee (taker):   -0.47  (0.05%)
Net P&L:       -52.47

────────────────────────────────
Trade P&L:     -52.47  (-1.05R)

Balance:       $9,897.53
```

### TP Hit (on_fill, exit_reason="TP1", remaining_amount=0.005)

```
📄 SIM | ✅ TP1 HIT — BTC/USDT LONG (partial)

Fill:          $105,000.00
Closed:        0.0050  ($525.00)
Gross P&L:     +25.00
Fee (maker):   -0.11
Net P&L:       +24.89

Remaining:     0.0050 contracts

Balance:       $9,974.89
```

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

## Troubleshooting

| Symptom                             | Cause                                        | Fix                                                                               |
| ----------------------------------- | -------------------------------------------- | --------------------------------------------------------------------------------- |
| No Telegram messages at all         | `telegram_enabled: false` or missing token   | Check config + `.env`                                                             |
| `TelegramBot` init error on startup | `TELEGRAM_BOT_TOKEN` env var missing         | Add to `.env`, falls back to `NullNotifier`                                       |
| Messages delayed                    | `NotificationWorker` queue backed up         | Normal under load — queue drains async                                            |
| Duplicate on_entry messages         | Exchange fires + PM fires                    | Check `_fires_entry_notification` flag on exchange                                |
| No SL notifications in live mode    | Hard SL fills on exchange without PM polling | Known gap — see [known-gaps.md](../09_portfolio_and_reconciliation/known-gaps.md) |
