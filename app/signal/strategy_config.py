"""StrategyInstanceConfig resolver for signal-mode bots.

Produces one frozen :class:`StrategyInstanceConfig` per active strategy from
the raw YAML dict. The caller (``SignalRunner``) should have already confirmed
``bot.mode == 'signal'`` — the resolver enforces every other signal-mode
requirement (telegram topics, known strategy names, unique ids).

Dependency direction: ``app/signal/`` → ``app/trading/`` via ``STRATEGY_MAP``.
The signal package hosts runtime code that drives strategies, so it is
allowed to import from the trading layer.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import structlog

from app.core.config import RiskConfig
from app.trading.strategy.loader import STRATEGY_MAP

logger = structlog.get_logger()


@dataclass(frozen=True)
class StrategyInstanceConfig:
    """Resolved per-strategy config.

    Built once at startup from global defaults + per-strategy overrides.
    """

    name: str
    telegram_topic_id: int
    symbols: tuple[str, ...]
    timeframe: str
    risk: RiskConfig

    @property
    def targets(self) -> frozenset[tuple[str, str]]:
        return frozenset((s, self.timeframe) for s in self.symbols)

    def as_legacy_dict(self) -> dict:
        """Dict shape existing strategy constructors expect.

        Mirrors :meth:`AppConfig.to_legacy_dict` for the subset of keys
        strategies read (``strategy``, ``symbols``, ``timeframe``, ``risk``,
        ``strategy_params``).
        """
        return {
            "strategy": self.name,
            "symbols": list(self.symbols),
            "timeframe": self.timeframe,
            "risk": {
                "risk_per_trade_pct": float(self.risk.risk_per_trade_pct),
                "max_position_size_pct": float(self.risk.max_position_size_pct),
                "leverage": self.risk.leverage,
                "use_initial_capital_for_risk": self.risk.use_initial_capital_for_risk,
                "use_risk_based_sizing": self.risk.use_risk_based_sizing,
                "tp1_close_pct": float(self.risk.tp1_close_pct),
                "tp2_close_pct": float(self.risk.tp2_close_pct),
                "min_sl_distance_pct": float(self.risk.min_sl_distance_pct),
            },
            "strategy_params": {},
        }


_DECIMAL_RISK_FIELDS = {
    "risk_per_trade_pct",
    "max_position_size_pct",
    "tp1_close_pct",
    "tp2_close_pct",
    "min_sl_distance_pct",
}
_INT_RISK_FIELDS = {"leverage"}
_BOOL_RISK_FIELDS = {"use_initial_capital_for_risk", "use_risk_based_sizing"}
_RISK_FIELDS = {f.name for f in dataclasses.fields(RiskConfig)}


def _build_global_risk(risk_raw: dict) -> RiskConfig:
    """Build the global RiskConfig from the top-level ``risk:`` block.

    Duplicates coercion from ``AppConfig.from_yaml``; a shared
    ``RiskConfig.from_dict`` helper is tracked for the slice-10 config
    migration.
    """
    return RiskConfig(
        risk_per_trade_pct=Decimal(str(risk_raw.get("risk_per_trade_pct", "0.02"))),
        max_position_size_pct=Decimal(str(risk_raw.get("max_position_size_pct", "0.99"))),
        leverage=int(risk_raw.get("leverage", 10)),
        use_initial_capital_for_risk=bool(risk_raw.get("use_initial_capital_for_risk", False)),
        use_risk_based_sizing=bool(risk_raw.get("use_risk_based_sizing", True)),
        tp1_close_pct=Decimal(str(risk_raw.get("tp1_close_pct", "0.33"))),
        tp2_close_pct=Decimal(str(risk_raw.get("tp2_close_pct", "0.50"))),
        min_sl_distance_pct=Decimal(str(risk_raw.get("min_sl_distance_pct", "0.003"))),
    )


def _coerce_risk_value(field_name: str, raw: Any) -> Any:
    if field_name in _DECIMAL_RISK_FIELDS:
        return Decimal(str(raw))
    if field_name in _INT_RISK_FIELDS:
        return int(raw)
    if field_name in _BOOL_RISK_FIELDS:
        return bool(raw)
    return raw


def _merge_risk(base: RiskConfig, override: dict | None, strategy_name: str) -> RiskConfig:
    """Apply per-field overrides on top of the global ``RiskConfig``.

    Distinct from ``app/trading/strategy/utils/config_helpers.merge_config``:
    that helper builds a fresh frozen dataclass from scratch (filtering
    unknowns); this one partial-overrides an existing instance.
    """
    if not override:
        return base
    updates: dict[str, Any] = {}
    for key, value in override.items():
        if key not in _RISK_FIELDS:
            logger.warning(
                "strategy_config_unknown_risk_key",
                strategy=strategy_name,
                key=key,
            )
            continue
        updates[key] = _coerce_risk_value(key, value)
    if not updates:
        return base
    return dataclasses.replace(base, **updates)


def validate_telegram_config(raw: dict) -> int:
    """Validate the ``telegram`` block and return the parsed debug topic id.

    Exposed so callers (``SignalRunner``) can read the validated
    ``debug_topic_id`` without a second pass over ``raw``. Idempotent —
    :func:`resolve_strategy_configs` also calls this internally.
    """
    telegram = raw.get("telegram") or {}
    group_id = telegram.get("group_id")
    debug_topic_id = telegram.get("debug_topic_id")
    if group_id is None:
        raise ValueError("signal mode requires telegram.group_id to be set")
    if debug_topic_id is None:
        raise ValueError("signal mode requires telegram.debug_topic_id to be set")
    try:
        return int(debug_topic_id)
    except (TypeError, ValueError) as e:
        raise ValueError(
            f"telegram.debug_topic_id must be an integer, got {debug_topic_id!r}"
        ) from e


def _resolve_entry(
    entry: dict,
    *,
    global_symbols: tuple[str, ...],
    global_timeframe: str,
    global_risk: RiskConfig,
    debug_topic_id: int,
    seen_topics: dict[int, str],
) -> StrategyInstanceConfig:
    """Validate and build a single StrategyInstanceConfig.

    Mutates ``seen_topics`` on success to enforce cross-strategy uniqueness.
    """
    name = entry.get("name")
    if not name:
        raise ValueError("every strategy entry must declare `name`")
    if name not in STRATEGY_MAP:
        available = ", ".join(sorted(STRATEGY_MAP))
        raise ValueError(f"unknown strategy `{name}`. Available: {available}")

    topic_id_raw = entry.get("telegram_topic_id")
    if topic_id_raw is None:
        raise ValueError(f"strategy `{name}` must declare `telegram_topic_id`")
    topic_id = int(topic_id_raw)
    if topic_id == debug_topic_id:
        raise ValueError(
            f"strategy `{name}` telegram_topic_id={topic_id} collides with debug_topic_id"
        )
    if topic_id in seen_topics:
        raise ValueError(
            f"strategy `{name}` telegram_topic_id={topic_id} "
            f"is already used by `{seen_topics[topic_id]}`"
        )
    seen_topics[topic_id] = name

    symbols_raw = entry.get("symbols")
    symbols = tuple(symbols_raw) if symbols_raw else global_symbols
    if not symbols:
        raise ValueError(
            f"strategy `{name}` has no symbols (global list is empty and "
            "no per-strategy override given)"
        )

    timeframe = entry.get("timeframe") or global_timeframe
    risk = _merge_risk(global_risk, entry.get("risk"), name)

    return StrategyInstanceConfig(
        name=name,
        telegram_topic_id=topic_id,
        symbols=symbols,
        timeframe=str(timeframe),
        risk=risk,
    )


def resolve_strategy_configs(raw: dict) -> list[StrategyInstanceConfig]:
    """Parse a raw signal-mode config dict into validated strategy configs.

    Returns an empty list if no strategies are active — the caller should
    warn and exit cleanly. Raises ``ValueError`` on any schema violation.

    Merge semantics:
      * ``symbols`` — per-strategy override replaces the global list if set.
      * ``timeframe`` — per-strategy override replaces the global value if set.
      * ``risk`` — per-field override; unspecified keys fall through to the
        global ``RiskConfig``. Unknown keys are warn-logged and ignored.
      * ``active`` — defaults to ``True`` when absent.

    Deferred (tracked for v2): per-strategy ``exclude:`` lists and
    per-strategy ``strategy_params``.
    """
    debug_topic_id = validate_telegram_config(raw)

    global_symbols = tuple(raw.get("symbols") or ())
    global_timeframe = raw.get("timeframe")
    if not global_timeframe:
        raise ValueError("signal mode requires a top-level `timeframe`")
    global_risk = _build_global_risk(raw.get("risk") or {})

    strategies_raw = raw.get("strategies") or []
    if not isinstance(strategies_raw, list):
        raise ValueError("`strategies` must be a list")

    resolved: list[StrategyInstanceConfig] = []
    seen_topics: dict[int, str] = {}

    for entry in strategies_raw:
        if not isinstance(entry, dict):
            raise ValueError(f"each strategy entry must be a mapping, got {type(entry).__name__}")
        if not entry.get("active", True):
            continue
        resolved.append(
            _resolve_entry(
                entry,
                global_symbols=global_symbols,
                global_timeframe=global_timeframe,
                global_risk=global_risk,
                debug_topic_id=debug_topic_id,
                seen_topics=seen_topics,
            )
        )

    return resolved
