"""
RSI Trading Bot - Main Entry Point
====================================
Branches on ``bot.mode``:

* ``"signal"`` → ``SignalRunner`` (multi-strategy signal-only runtime).
* any other mode → ``MultiSymbolRunner`` (live-trading path, unchanged).

Usage:
    python main.py
"""

import os
import sys

import yaml
from dotenv import load_dotenv

# Add the current directory to sys.path to allow imports from app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load Env first (needed by exchange factory and TelegramNotifier)
load_dotenv()

from app.core.config import AppConfig  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402

# Setup logging immediately (before any other imports that use loggers)
setup_logging(level="INFO")

import structlog  # noqa: E402

from app.notification.notification_service import NotificationService  # noqa: E402
from app.notification.null_notifier import NullNotifier  # noqa: E402

logger = structlog.get_logger()


def _load_raw_yaml(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _build_notifier(
    bot_mode: str,
    *,
    require_telegram: bool,
    chat_id_override: str | int | None = None,
) -> NotificationService:
    """Build the NotificationService. Signal mode requires a real Telegram
    token — messages are the bot's only output. Live mode falls back to
    NullNotifier if Telegram init fails.

    ``chat_id_override`` lets signal mode source the chat_id from
    ``telegram.group_id`` in config.yaml (the supergroup that hosts the
    topics) instead of relying on the ``TELEGRAM_CHAT_ID`` env var.
    """
    try:
        from app.notification.telegram_notifier import TelegramNotifier

        ns = NotificationService(
            TelegramNotifier(mode=bot_mode, chat_id_override=chat_id_override),
            mode=bot_mode,
        )
        logger.info("telegram_initialized")
        return ns
    except Exception as e:
        if require_telegram:
            logger.error("telegram_required_but_init_failed", error=str(e))
            sys.exit(1)
        logger.warning("telegram_init_failed_using_null_notifier", error=str(e))
        return NotificationService(NullNotifier(), mode=bot_mode)


def _build_signal_startup_message(raw: dict) -> str:
    """Compose the start-up announcement sent to the debug topic."""
    strategies = raw.get("strategies") or []
    active = [s for s in strategies if s.get("active") is True]
    global_tf = raw.get("timeframe", "?")
    global_symbols = raw.get("symbols") or []

    lines = [
        "🤖 Signal Bot Started",
        f"Mode: SIGNAL",
        f"Active strategies: {len(active)}",
    ]
    for s in active:
        tf = s.get("timeframe", global_tf)
        syms = s.get("symbols") or global_symbols
        lines.append(
            f"  • {s.get('name')} — topic {s.get('telegram_topic_id')}"
            f" · {tf} · {len(syms)} symbols"
        )
    return "\n".join(lines)


def _run_signal_mode(raw: dict, ns: NotificationService) -> None:
    """Start and run the SignalRunner lifecycle.

    Imports are lazy so unit tests that patch only the live-bot path don't
    pay the cost of loading the multiplexer / stream manager / VP store.
    """
    from app.signal.runner import SignalRunner
    from app.signal.strategy_config import validate_telegram_config
    from app.trading.status_writer import StatusWriter

    try:
        runner = SignalRunner(raw, ns)
        runner.start()
    except ValueError as e:
        logger.error("signal_config_invalid", error=str(e))
        ns.stop()
        sys.exit(1)

    # Enable Telegram command polling (/bot_version, /force_deploy, ...).
    # Exchange-scoped commands (/status, /history, ...) reply with a
    # "not available in signal mode" notice since no exchange is attached.
    ns.start_command_polling()

    # Re-resolve debug_topic_id; runner.start() already validated so this
    # cannot raise unless the config is mutated between calls.
    debug_topic_id = validate_telegram_config(raw)
    try:
        ns.send_message(
            _build_signal_startup_message(raw), topic_id=debug_topic_id
        )
    except Exception:
        logger.exception("signal_startup_broadcast_failed")

    def _vp_positions() -> list[dict]:
        out: list[dict] = []
        for strategy_name, vps in runner.vp_store.all_open_by_strategy().items():
            for vp in vps:
                out.append({
                    "symbol": vp.symbol,
                    "side": vp.side,
                    "strategy": strategy_name,
                    "entry_price": float(vp.entry_price),
                })
        return out

    status_writer = StatusWriter(_vp_positions)
    try:
        status_writer.start()
        runner.wait()
    finally:
        try:
            ns.send_message("🛑 Signal Bot Stopped", topic_id=debug_topic_id)
        except Exception:
            logger.exception("signal_shutdown_broadcast_failed")
        status_writer.stop()
        runner.stop()


def _run_live_mode(
    config_path: str, bot_mode: str, ns: NotificationService
) -> None:
    """Existing live-bot path; kept separate so the signal branch doesn't
    pay the AppConfig overhead."""
    from app.trading.exchange.factory import create_exchange
    from app.trading.runner import MultiSymbolRunner
    from app.trading.status_writer import StatusWriter
    from app.trading.strategy.loader import load_strategy

    try:
        app_config = AppConfig.from_yaml(config_path)
    except (FileNotFoundError, ValueError) as e:
        logger.error("invalid_config", error=str(e))
        ns.stop()
        sys.exit(1)

    config = app_config.to_legacy_dict()
    exchange = create_exchange(config, notification_service=ns)

    runner = MultiSymbolRunner(
        config=config,
        strategy_class=load_strategy(config),
        exchange=exchange,
        notification_service=ns,
    )

    def _live_positions() -> list[dict]:
        out: list[dict] = []
        for symbol, portfolio in list(runner.portfolios.items()):
            pos = portfolio.get_position(symbol)
            if pos is not None:
                out.append({
                    "symbol": symbol,
                    "side": pos.side,
                    "size": float(pos.amount),
                    "entry_price": float(pos.entry_price),
                })
        return out

    def _sim_snapshot() -> None:
        state = getattr(runner.exchange, "state", None)
        if state is not None and hasattr(state, "write_snapshot"):
            state.write_snapshot()

    status_writer = StatusWriter(_live_positions, snapshot_hook=_sim_snapshot)

    ns.send_message(f"🤖 RSI Bot Started\nMode: {bot_mode.upper()}")
    try:
        runner.start()
        status_writer.start()
        runner.wait()
    finally:
        status_writer.stop()
        runner.stop()
        ns.send_message("🛑 RSI Bot Stopped")


def main(config_path: str = "config.yaml") -> None:
    try:
        raw = _load_raw_yaml(config_path)
    except FileNotFoundError:
        logger.error("config_file_not_found", path=config_path)
        sys.exit(1)

    bot_mode = (raw.get("bot") or {}).get("mode", "mock")
    logger.info("bot_starting", mode=bot_mode.upper())

    chat_id_override: str | int | None = None
    if bot_mode == "signal":
        chat_id_override = (raw.get("telegram") or {}).get("group_id")

    ns = _build_notifier(
        bot_mode,
        require_telegram=(bot_mode == "signal"),
        chat_id_override=chat_id_override,
    )

    try:
        if bot_mode == "signal":
            _run_signal_mode(raw, ns)
        else:
            _run_live_mode(config_path, bot_mode, ns)
    except KeyboardInterrupt:
        logger.info("bot_stopped_by_user")


if __name__ == "__main__":
    main()
