"""
Structured logging setup (replaces app/utils/logger.py).
All modules use: logger = structlog.get_logger()

Call setup_logging() once at startup in main.py.
"""
from __future__ import annotations

import logging
import threading

import structlog


def setup_logging(level: str = "INFO", json_output: bool = False, log_file: str = "rsi_bot.log", console: bool = True) -> None:
    """
    Configure structlog + stdlib logging.

    Args:
        level: Log level ("DEBUG", "INFO", "WARNING", "ERROR")
        json_output: True for production (JSON lines), False for dev (colored console)
        log_file: Name/path for the log file
        console: Whether to output logs to standard output
    """
    structlog.reset_defaults()

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_thread_name,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if json_output:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    root = logging.getLogger()
    root.handlers.clear()
    
    if console:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root.addHandler(handler)

    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    root.setLevel(getattr(logging, level.upper()))
    
    # Suppress verbose 3rd-party loggers
    logging.getLogger("ccxt").setLevel(logging.WARNING)


def _add_thread_name(logger, method_name, event_dict):
    """Processor: add current thread name to every log record."""
    event_dict["thread"] = threading.current_thread().name
    return event_dict


def bind_trade_context(symbol: str, trade_id: str = None) -> None:
    """Bind trade context for structured logging. Call at position open."""
    structlog.contextvars.bind_contextvars(symbol=symbol)
    if trade_id:
        structlog.contextvars.bind_contextvars(trade_id=trade_id)


def clear_trade_context() -> None:
    """Clear trade context. Call at position close."""
    structlog.contextvars.unbind_contextvars("symbol", "trade_id")
