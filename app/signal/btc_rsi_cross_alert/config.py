"""Frozen configuration and strict resolver for the BTC RSI cross alert.

Locked v1 values (spec §6) are explicit in ``config.yaml`` for auditability
but validated exactly — no other symbol, timeframes, periods, or settle range
is silently accepted. Topic uniqueness is enforced across ordinary strategies,
both timeframe routes of this component, and the debug topic together.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger()

COMPONENT_NAME: str = "btc_rsi_cross_alert"
CANONICAL_SYMBOL: str = "BTC/USDT"
LOCKED_TRIGGER_TIMEFRAMES: frozenset[str] = frozenset({"5m", "15m"})
LOCKED_TREND_TIMEFRAME: str = "4h"
LOCKED_CONFIRMATION_TIMEFRAME: str = "1h"
LOCKED_RSI_PERIOD: int = 21
LOCKED_RSI_EMA_PERIOD: int = 9
LOCKED_RSI_WMA_PERIOD: int = 45
MIN_CONTEXT_SETTLE_SECONDS: int = 0
MAX_CONTEXT_SETTLE_SECONDS: int = 30


@dataclass(frozen=True)
class BtcRsiCrossAlertConfig:
    """Resolved, validated config for one active BTC RSI cross alert entry."""

    name: str
    telegram_topic_id: int
    m15_telegram_topic_id: int
    symbol: str
    trigger_timeframes: tuple[str, ...]
    trend_timeframe: str
    confirmation_timeframe: str
    rsi_period: int
    rsi_ema_period: int
    rsi_wma_period: int
    context_settle_seconds: int

    @property
    def targets(self) -> frozenset[tuple[str, str]]:
        """Stream targets: triggers plus native H1 and H4 context frames."""

        return frozenset(
            {(self.symbol, tf) for tf in self.trigger_timeframes}
            | {(self.symbol, self.trend_timeframe)}
            | {(self.symbol, self.confirmation_timeframe)}
        )

    @property
    def telegram_topic_ids(self) -> Mapping[str, int]:
        """Return the configured topic per trigger timeframe.

        ``telegram_topic_id`` remains the M5 field for compatibility with the
        original single-topic config surface. The M15 route is explicit so
        the two timeframe-specific checkers cannot silently share a topic.
        """

        return {"5m": self.telegram_topic_id, "15m": self.m15_telegram_topic_id}

    def topic_id_for(self, timeframe: str) -> int:
        """Return the Telegram topic configured for one trigger timeframe."""

        try:
            return self.telegram_topic_ids[timeframe]
        except KeyError as exc:
            raise ValueError(
                f"unsupported BTC RSI cross trigger timeframe: {timeframe!r}"
            ) from exc


def _coerce_topic_id(raw: Any, *, field_name: str) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{COMPONENT_NAME} {field_name} must be an integer-coercible "
            f"value, got {raw!r}"
        ) from exc


def _resolve_topic_ids(
    entry: dict,
    *,
    debug_topic_id: int,
    seen_topics: dict[int, str],
) -> tuple[int, int]:
    """Validate and reserve the M5 and M15 Telegram topics."""

    m5_raw = entry.get("telegram_topic_id")
    if m5_raw is None:
        raise ValueError(f"{COMPONENT_NAME} must declare telegram_topic_id for M5")
    m15_raw = entry.get("m15_telegram_topic_id")
    if m15_raw is None:
        raise ValueError(
            f"{COMPONENT_NAME} must declare m15_telegram_topic_id for M15"
        )

    topic_ids = {
        "5m": _coerce_topic_id(m5_raw, field_name="telegram_topic_id"),
        "15m": _coerce_topic_id(m15_raw, field_name="m15_telegram_topic_id"),
    }
    if len(set(topic_ids.values())) != len(topic_ids):
        raise ValueError(
            f"{COMPONENT_NAME} M5 and M15 Telegram topics must be different"
        )

    for timeframe, topic_id in topic_ids.items():
        field_name = (
            "telegram_topic_id"
            if timeframe == "5m"
            else "m15_telegram_topic_id"
        )
        if topic_id == debug_topic_id:
            raise ValueError(
                f"{COMPONENT_NAME} {field_name}={topic_id} collides with "
                "debug_topic_id"
            )
        if topic_id in seen_topics:
            raise ValueError(
                f"{COMPONENT_NAME} {field_name}={topic_id} is already used by "
                f"`{seen_topics[topic_id]}`"
            )

    for timeframe, topic_id in topic_ids.items():
        seen_topics[topic_id] = f"{COMPONENT_NAME} ({timeframe})"
    return topic_ids["5m"], topic_ids["15m"]


def _validate_locked_values(entry: dict) -> None:
    symbol = entry.get("symbol", CANONICAL_SYMBOL)
    if symbol != CANONICAL_SYMBOL:
        raise ValueError(
            f"{COMPONENT_NAME} only supports symbol {CANONICAL_SYMBOL!r}, got {symbol!r}"
        )

    triggers_raw = entry.get("trigger_timeframes")
    if not triggers_raw:
        raise ValueError(
            f"{COMPONENT_NAME} requires trigger_timeframes {sorted(LOCKED_TRIGGER_TIMEFRAMES)}"
        )
    if not isinstance(triggers_raw, (list, tuple)):
        raise ValueError(f"{COMPONENT_NAME} trigger_timeframes must be a list")
    triggers = tuple(str(tf) for tf in triggers_raw)
    if len(set(triggers)) != len(triggers):
        raise ValueError(f"{COMPONENT_NAME} trigger_timeframes must not contain duplicates")
    if set(triggers) != LOCKED_TRIGGER_TIMEFRAMES:
        raise ValueError(
            f"{COMPONENT_NAME} trigger_timeframes must be exactly "
            f"{sorted(LOCKED_TRIGGER_TIMEFRAMES)}, got {sorted(triggers)}"
        )

    trend = entry.get("trend_timeframe")
    if trend != LOCKED_TREND_TIMEFRAME:
        raise ValueError(
            f"{COMPONENT_NAME} trend_timeframe must be {LOCKED_TREND_TIMEFRAME!r}, got {trend!r}"
        )
    confirmation = entry.get("confirmation_timeframe")
    if confirmation != LOCKED_CONFIRMATION_TIMEFRAME:
        raise ValueError(
            f"{COMPONENT_NAME} confirmation_timeframe must be "
            f"{LOCKED_CONFIRMATION_TIMEFRAME!r}, got {confirmation!r}"
        )

    locked_periods = {
        "rsi_period": LOCKED_RSI_PERIOD,
        "rsi_ema_period": LOCKED_RSI_EMA_PERIOD,
        "rsi_wma_period": LOCKED_RSI_WMA_PERIOD,
    }
    for key, expected in locked_periods.items():
        raw_value = entry.get(key)
        if raw_value is None:
            raise ValueError(f"{COMPONENT_NAME} requires {key}={expected}")
        # Locked v1 periods accept plain integers only — no silent float
        # truncation or string coercion.
        if not isinstance(raw_value, int) or isinstance(raw_value, bool):
            raise ValueError(
                f"{COMPONENT_NAME} {key} must be the exact integer {expected}, "
                f"got {raw_value!r}"
            )
        if raw_value != expected:
            raise ValueError(
                f"{COMPONENT_NAME} {key} is locked to {expected}, got {raw_value}"
            )

    settle_raw = entry.get("context_settle_seconds")
    if settle_raw is None:
        raise ValueError(f"{COMPONENT_NAME} requires context_settle_seconds")
    if (
        not isinstance(settle_raw, int)
        or isinstance(settle_raw, bool)
        or not (
            MIN_CONTEXT_SETTLE_SECONDS
            <= settle_raw
            <= MAX_CONTEXT_SETTLE_SECONDS
        )
    ):
        raise ValueError(
            f"{COMPONENT_NAME} context_settle_seconds must be an integer in "
            f"[{MIN_CONTEXT_SETTLE_SECONDS}, {MAX_CONTEXT_SETTLE_SECONDS}], got {settle_raw!r}"
        )


def resolve_btc_rsi_cross_alert_config(
    entries: list[dict],
    *,
    debug_topic_id: int,
    seen_topics: dict[int, str],
) -> BtcRsiCrossAlertConfig | None:
    """Validate the component entries and return the active config, or None.

    Disabled entries are ignored entirely — their topic is NOT reserved.
    Raises ``ValueError`` on any spec §6 violation. ``seen_topics`` maps
    already-reserved topic ids to owner names (ordinary strategies resolved
    earlier); both of this component's topic routes are registered there on
    success.
    """

    active_entries = [
        entry for entry in entries if isinstance(entry, dict) and entry.get("active", True)
    ]
    disabled_count = sum(
        1
        for entry in entries
        if isinstance(entry, dict) and not entry.get("active", True)
    )
    if len(active_entries) > 1:
        raise ValueError(
            f"at most one active {COMPONENT_NAME} entry is allowed, "
            f"got {len(active_entries)}"
        )
    if not active_entries:
        if disabled_count:
            logger.debug(
                "btc_rsi_cross_alert_disabled",
                disabled_entries=disabled_count,
            )
        return None

    entry = active_entries[0]
    _validate_locked_values(entry)

    name = entry.get("name", COMPONENT_NAME)
    if name != COMPONENT_NAME:
        raise ValueError(
            f"component name must be {COMPONENT_NAME!r}, got {name!r}"
        )

    m5_topic_id, m15_topic_id = _resolve_topic_ids(
        entry,
        debug_topic_id=debug_topic_id,
        seen_topics=seen_topics,
    )

    config = BtcRsiCrossAlertConfig(
        name=COMPONENT_NAME,
        telegram_topic_id=m5_topic_id,
        m15_telegram_topic_id=m15_topic_id,
        symbol=CANONICAL_SYMBOL,
        trigger_timeframes=("5m", "15m"),
        trend_timeframe=LOCKED_TREND_TIMEFRAME,
        confirmation_timeframe=LOCKED_CONFIRMATION_TIMEFRAME,
        rsi_period=LOCKED_RSI_PERIOD,
        rsi_ema_period=LOCKED_RSI_EMA_PERIOD,
        rsi_wma_period=LOCKED_RSI_WMA_PERIOD,
        context_settle_seconds=int(entry["context_settle_seconds"]),
    )
    logger.info(
        "btc_rsi_cross_alert_resolved",
        topics=config.telegram_topic_ids,
        targets=sorted(config.targets),
        context_settle_seconds=config.context_settle_seconds,
    )
    return config


def is_btc_rsi_cross_alert_entry(entry: dict) -> bool:
    """True when a raw strategies-list entry names this component."""

    return isinstance(entry, dict) and entry.get("name") == COMPONENT_NAME
