"""Send a fake signal through the real notifier path to verify Telegram delivery.

Run this after configuring ``config.yaml`` (signal mode + telegram.group_id +
strategy.telegram_topic_id) and ``.env`` (TELEGRAM_BOT_TOKEN) to confirm that:

  1. The notifier wires ``telegram.group_id`` → chat_id correctly.
  2. The strategy's topic_id resolves to a real Telegram thread.
  3. Entry / SL-hit / TP-hit / shutdown formatters render and post.

Usage:
    python scripts/test_signal_notification.py                 # entry only
    python scripts/test_signal_notification.py --all           # entry + sl + tp + shutdown
    python scripts/test_signal_notification.py --strategy rsi_no_retest

Posts go to the FIRST active strategy's topic by default; override with
``--strategy <name>``. The ``[FAKE]`` tag is prepended so you can clearly
distinguish test posts from real signals.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal

import yaml
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from app.core.events import Candle  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402
from app.notification.notification_service import NotificationService  # noqa: E402
from app.notification.telegram_notifier import TelegramNotifier  # noqa: E402
from app.signal import signal_formatter  # noqa: E402
from app.signal.virtual_position import VirtualPosition  # noqa: E402

setup_logging(level="INFO")


def _build_fake_vp(strategy_name: str, symbol: str = "BTC/USDT") -> VirtualPosition:
    return VirtualPosition(
        signal_id="TEST#999",
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


def _fake_candle(price: Decimal) -> Candle:
    return Candle(
        symbol="BTC/USDT",
        timeframe="15m",
        timestamp=datetime.now(timezone.utc),
        open=price,
        high=price,
        low=price,
        close=price,
        volume=Decimal("1.0"),
    )


def _tag(msg: str) -> str:
    return f"[FAKE TEST]\n{msg}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--strategy", default=None, help="Strategy name (default: first active)")
    parser.add_argument("--all", action="store_true", help="Send entry + SL + TP + shutdown")
    args = parser.parse_args()

    with open(args.config) as f:
        raw = yaml.safe_load(f) or {}

    bot_mode = (raw.get("bot") or {}).get("mode", "mock")
    telegram_cfg = raw.get("telegram") or {}
    group_id = telegram_cfg.get("group_id")
    debug_topic_id = telegram_cfg.get("debug_topic_id")

    if bot_mode != "signal":
        print(f"WARNING: bot.mode is '{bot_mode}', not 'signal'. Continuing anyway.")
    if group_id is None:
        print("ERROR: telegram.group_id missing from config.yaml")
        return 1

    strategies = [s for s in (raw.get("strategies") or []) if s.get("active", True)]
    if args.strategy:
        strategies = [s for s in strategies if s.get("name") == args.strategy]
    if not strategies:
        print("ERROR: no active strategies match the given --strategy filter")
        return 1
    target = strategies[0]
    strategy_name = target["name"]
    topic_id = int(target["telegram_topic_id"])

    print(
        f"Posting fake signal: group_id={group_id} strategy={strategy_name} "
        f"topic_id={topic_id} debug_topic_id={debug_topic_id}"
    )

    notifier = TelegramNotifier(mode="signal", chat_id_override=group_id)
    ns = NotificationService(notifier, mode="signal")

    try:
        vp = _build_fake_vp(strategy_name)
        ns.send_message(_tag(signal_formatter.format_entry(vp)), topic_id=topic_id)
        print("  → sent fake ENTRY")

        if args.all:
            time.sleep(1.0)
            sl_candle = _fake_candle(Decimal("48800"))
            ns.send_message(
                _tag(signal_formatter.format_sl_hit(vp, sl_candle)),
                topic_id=topic_id,
            )
            print("  → sent fake SL-HIT")

            time.sleep(1.0)
            tp_candle = _fake_candle(Decimal("51500"))
            ns.send_message(
                _tag(signal_formatter.format_tp_hit(vp, 0, vp.tp_levels[0], tp_candle)),
                topic_id=topic_id,
            )
            print("  → sent fake TP-HIT")

            time.sleep(1.0)
            ns.send_message(
                _tag(signal_formatter.format_shutdown_broadcast(strategy_name, [vp])),
                topic_id=topic_id,
            )
            print("  → sent fake SHUTDOWN")

        # Give the background worker time to flush before stop().
        time.sleep(2.0)
    finally:
        ns.stop()

    print("Done. Check the Telegram topic for the test message(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
