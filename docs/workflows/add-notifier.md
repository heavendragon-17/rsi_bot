# Add a Notification Channel

> Add a new notification channel (Discord, Slack, email, PagerDuty, etc.).
> Reference spec: `docs/08_execution_and_oms/notifications.md`
> Interface: `INotifier` in `app/core/interfaces.py`

## Prerequisites

- Read `docs/08_execution_and_oms/notifications.md` — full architecture, event table, and message format examples
- Read `app/core/interfaces.py` — `INotifier` abstract class (lines ~196–266) for the exact method signatures
- Read `app/services/notification/telegram_notifier.py` — reference implementation with error handling patterns

## Steps

### 1. Understand the method contract

Subclass `INotifier` from `app/core/interfaces.py`. Your class must implement all 6 abstract methods with the exact signatures below:

```python
from app.core.interfaces import INotifier
from decimal import Decimal
from typing import Optional, Dict

class MyNotifier(INotifier):
    def send_message(self, message: str) -> None: ...

    def on_entry(
        self,
        symbol: str,
        side: str,
        entry_price: Decimal,
        amount: Decimal,
        sl_price: Optional[Decimal] = None,
        tp_prices: Optional[Dict[str, Decimal]] = None,
        leverage: int = 1,
        balance: Optional[Decimal] = None,
    ) -> None: ...

    def on_fill(
        self,
        symbol: str,
        exit_reason: str,
        fill_price: Decimal,
        amount: Decimal,
        pnl_gross: Optional[Decimal] = None,
        pnl_net: Optional[Decimal] = None,
        fees: Optional[Decimal] = None,
        r_multiple: Optional[Decimal] = None,
        remaining_amount: Optional[Decimal] = None,
        balance: Optional[Decimal] = None,
    ) -> None: ...

    def on_error(self, context: str, error: str) -> None: ...

    def on_funding(
        self,
        symbol: str,
        rate: Decimal,
        payment: Decimal,
        balance: Decimal,
    ) -> None: ...

    def on_toggle(self, is_paused: bool) -> None: ...
```

**Critical**: All methods must **never raise exceptions** that could crash the bot. Follow `telegram_notifier.py` — wrap all external calls in `try/except Exception`, log the error, return silently.

### 2. Create the notifier file

File: `app/services/notification/{name}_notifier.py`

Model on `app/services/notification/telegram_notifier.py`. Key patterns:

- Subclass `INotifier` (enforces the contract at class definition time)
- Read credentials from environment variables in `__init__` (`os.getenv`)
- Raise `RuntimeError` in `__init__` if required env vars are missing (fail loudly at startup, not silently at runtime)
- Use `structlog.get_logger()` for logging
- Use `requests` for HTTP calls with a short timeout (5 s)
- Wrap all external calls in `try/except` — the notifier must never crash the bot

### 3. Inject the notifier

File: `main.py`

The bot creates a `NotificationService` wrapping either `TelegramNotifier` or `NullNotifier`:

```python
from app.services.notification.notification_service import NotificationService
from app.services.notification.telegram_notifier import TelegramNotifier
from app.services.notification.null_notifier import NullNotifier

try:
    notifier = TelegramNotifier(mode=config.bot.mode)
except Exception:
    notifier = NullNotifier()

notification_service = NotificationService(notifier, mode=config.bot.mode)
```

`NotificationService` wraps the `INotifier` with a background `NotificationWorker` queue (non-blocking). Always pass `NotificationService` instances — never raw notifiers — to `PortfolioManager`, `SimExchange`, etc.

**To replace Telegram**: Swap `TelegramNotifier(...)` with your notifier class.

**To add alongside Telegram**: Create a `MultiNotifier` wrapper that fans out to multiple channels:

```python
class MultiNotifier(INotifier):
    def __init__(self, notifiers: list[INotifier]):
        self.notifiers = notifiers

    def send_message(self, message: str) -> None:
        for n in self.notifiers:
            try: n.send_message(message)
            except Exception: pass

    # Repeat for all 6 methods
```

### 4. Add credentials to `.env`

```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

Document all required env vars in the module docstring of your notifier file.

## Testing

1. Write `tests/test_{name}_notifier.py`
2. Mock the HTTP call (e.g., `unittest.mock.patch('requests.post')`)
3. Test that exceptions in HTTP calls do NOT propagate — the notifier swallows them
4. Test that missing env vars raise `RuntimeError` at construction time
5. Test that each of the 6 methods can be called without errors
6. Run `pytest tests/ -v`

## Documentation Impact

Consult `docs/INDEX.md` → "Code Path → Documentation File" table:

- `app/services/notification/` modified → update **`docs/08_execution_and_oms/notifications.md`**: add the new channel to the Key Files table and update the Configuration section with its env vars and fallback behavior
