"""Shared SL/TP ladder builders for strategy use."""

from __future__ import annotations


def build_tp_allocations(tp_count: int, tp1_pct: float, tp2_pct: float) -> dict:
    """Build TP allocation dict from tp_count and close percentages.

    Returns dict like {"TP1": 0.5, "TP2": 0.5, "TP3": 1.0} where each value
    is the cumulative close fraction at that TP level.
    """
    if tp_count == 1:
        return {"TP1": 1.0}
    elif tp_count == 2:
        return {"TP1": tp1_pct, "TP2": 1.0}
    else:
        return {"TP1": tp1_pct, "TP2": tp2_pct, "TP3": 1.0}
