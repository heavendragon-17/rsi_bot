"""``/test_signal`` Telegram command — fires a fake entry into every active
strategy's topic so operators can verify the notifier wiring end-to-end
without waiting for a real signal.

Lives under ``app/signal/`` because it depends on ``StrategyInstanceConfig``
and ``signal_formatter``; ``app/notification/`` stays free of any back-import
into the signal package.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal

import structlog

from app.notification.notification_service import NotificationService
from app.signal import signal_formatter
from app.signal.strategy_config import StrategyInstanceConfig
from app.signal.virtual_position import VirtualPosition

logger = structlog.get_logger()

_FAKE_TAG = "[FAKE TEST]"


def _fake_vp(strategy_name: str, symbol: str = "BTC/USDT") -> VirtualPosition:
    """Build a deterministic VP for the fake-entry message."""
    return VirtualPosition(
        signal_id="TEST#000",
        strategy_name=strategy_name,
        symbol=symbol,
        side="LONG",
        entry_price=Decimal("50000"),
        sl_price=Decimal("49000"),
        tp_levels=(Decimal("51000"), Decimal("52000"), Decimal("53000")),
        tp_close_pcts=(0.33, 0.5, 1.0),
        opened_at_candle_ts=int(datetime.now(timezone.utc).timestamp() * 1000),
        timeframe="15m",
    )


def make_test_signal_callback(
    strategies: list[StrategyInstanceConfig],
    notification_service: NotificationService,
    debug_topic_id: int,
    *,
    verify_chat_id: Callable[[str], bool] | None = None,
    send_reply: Callable[..., bool] | None = None,
) -> Callable[[str], None]:
    """Build the ``/test_signal`` callback bound to runtime state.

    Returns a ``(chat_id) -> None`` callback ready to register via
    ``NotificationService.start_command_polling(extra_callbacks=...)``.
    """

    def callback(chat_id: str) -> None:
        if verify_chat_id is not None and not verify_chat_id(chat_id):
            return
        try:
            for cfg in strategies:
                vp = _fake_vp(cfg.name)
                msg = f"{_FAKE_TAG}\n{signal_formatter.format_entry(vp)}"
                notification_service.send_message(msg, topic_id=cfg.telegram_topic_id)

            notification_service.send_message(
                f"{_FAKE_TAG}\n/test_signal fired for {len(strategies)} strategies.",
                topic_id=debug_topic_id,
            )
            if send_reply is not None:
                send_reply(
                    f"✅ Fake signal posted to {len(strategies)} strategy topic(s) "
                    f"+ debug topic. Check each topic for the [FAKE TEST] message.",
                    chat_id=chat_id,
                )
        except Exception as e:
            logger.exception("test_signal_callback_failed")
            if send_reply is not None:
                send_reply(f"❌ /test_signal failed: {e!r}", chat_id=chat_id)

    return callback
