"""Shared config construction helpers for strategy dataclasses."""

from __future__ import annotations

from dataclasses import fields as dc_fields
from typing import TypeVar

T = TypeVar("T")


def merge_config(config_cls: type[T], overrides: dict) -> T:
    """Construct a frozen config dataclass, filtering unknown keys.

    Usage::

        cfg = merge_config(RsiMomentumConfig, strategy_params)
    """
    valid = {f.name for f in dc_fields(config_cls)}  # type: ignore[arg-type]
    return config_cls(**{k: v for k, v in overrides.items() if k in valid})
