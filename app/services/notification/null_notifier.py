"""
Null Object pattern for notifications.
Used when Telegram is disabled or fails to initialize.
Silently discards all notification calls — bot continues normally.
"""


class NullNotifier:
    """No-op notifier. All methods silently do nothing."""

    def send_message(self, *args, **kwargs) -> None:
        pass

    def on_entry(self, *args, **kwargs) -> None:
        pass

    def on_fill(self, *args, **kwargs) -> None:
        pass

    def on_exit(self, *args, **kwargs) -> None:
        pass

    def on_error(self, *args, **kwargs) -> None:
        pass

    def on_funding(self, *args, **kwargs) -> None:
        pass

    def on_toggle(self, *args, **kwargs) -> None:
        pass
