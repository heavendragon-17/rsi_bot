# Add a Notification Channel

> Add a new notification channel (Discord, Slack, email, PagerDuty, etc.).
> Reference implementation: `app/services/notification/telegram_bot.py`
> Interface contract (duck-typed): `app/services/notification/null_notifier.py`

## Prerequisites

- Read `docs/live-bot.md` — Telegram Notifications section
- Read `app/services/notification/null_notifier.py` — the full method signature contract (7 methods)
- Read `app/services/notification/telegram_bot.py` — see how error handling is done

## Steps

### 1. Understand the method contract

The "interface" is defined by duck typing from `NullNotifier`. Your class must implement all 7 methods with `*args, **kwargs` signatures:

```python
def send_message(self, *args, **kwargs) -> None: ...
def on_entry(self, *args, **kwargs) -> None: ...
def on_fill(self, *args, **kwargs) -> None: ...
def on_exit(self, *args, **kwargs) -> None: ...
def on_error(self, *args, **kwargs) -> None: ...
def on_funding(self, *args, **kwargs) -> None: ...
def on_toggle(self, *args, **kwargs) -> None: ...
```

**Critical**: All methods must **never raise exceptions** that could crash the bot. Follow the `telegram_bot.py` pattern — wrap all external calls in `try/except Exception`, log the error, return silently.

### 2. Create the notifier file

File: `app/services/notification/{name}_notifier.py`

Model on `app/services/notification/telegram_bot.py`. Key patterns:

- Read credentials from environment variables in `__init__` (`os.getenv`)
- Raise `RuntimeError` in `__init__` if required env vars are missing (fail loudly at startup, not silently at runtime)
- Use `structlog.get_logger()` for logging
- Use `requests` for HTTP calls with a short timeout (5s)
- Wrap all external calls in `try/except` — the notifier must never crash the bot

### 3. Inject the notifier

File: `main.py`

Currently the bot initializes `TelegramBot` and falls back to `NullNotifier`:
```python
try:
    notifier = TelegramBot()
except Exception:
    notifier = NullNotifier()
```

**To replace Telegram**: Swap `TelegramBot()` with your notifier class.

**To add alongside Telegram**: Create a `MultiNotifier` wrapper that fans out to multiple channels:
```python
class MultiNotifier:
    def __init__(self, notifiers):
        self.notifiers = notifiers

    def send_message(self, *a, **kw):
        for n in self.notifiers:
            try: n.send_message(*a, **kw)
            except Exception: pass
    # ... repeat for all 7 methods
```

For paper/sim mode: also update `app/paper/notifier.py` (`PaperTelegramNotifier`) if you want the new channel in sim mode.

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
5. Test that each of the 7 methods can be called without errors
6. Run `pytest tests/ -v`

## Documentation Impact

Consult `docs/INDEX.md` → "Code Path → Documentation File" table:

- `app/services/notification/` modified → update **`docs/live-bot.md`**: generalize the "Telegram Notifications" section to "Notifications", add the new channel with its env vars and fallback behavior
