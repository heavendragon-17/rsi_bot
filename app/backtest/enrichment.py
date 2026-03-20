"""
Round-trip enrichment — single source of truth.

Previously duplicated identically in run_batch_analysis.py and
run_portfolio_backtest.py.
"""
from __future__ import annotations

import pandas as pd


def enrich_round_trips(results: dict, debug_rows: list) -> dict:
    """Join entry_spread, rsi_ema9, rsi_wma45, above_count from strategy
    debug rows into ``results["round_trips"]``.
    """
    buy_lookup = {
        (str(r.get("symbol", "")), str(r.get("timestamp", ""))): r
        for r in debug_rows
        if r.get("signal") == "BUY"
    }
    rt_list = results.get("round_trips", [])
    if not rt_list or not buy_lookup:
        return results

    enriched = []
    for rt in rt_list:
        rt = dict(rt)
        sym = str(rt.get("symbol", ""))
        try:
            entry_ts = str(pd.Timestamp(rt["entry_time"])) if rt.get("entry_time") else ""
        except Exception:
            entry_ts = str(rt.get("entry_time", ""))
        match = buy_lookup.get((sym, entry_ts))
        rt["entry_rsi_ema9"] = (
            round(float(match["rsi_ema9"]), 4) if match and match.get("rsi_ema9") is not None else None
        )
        rt["entry_rsi_wma45"] = (
            round(float(match["rsi_wma45"]), 4) if match and match.get("rsi_wma45") is not None else None
        )
        rt["entry_spread"] = (
            round(float(match["spread"]), 4) if match and match.get("spread") is not None else None
        )
        rt["above_count"] = (
            int(match["above_count"]) if match and match.get("above_count") is not None else None
        )
        enriched.append(rt)

    results = dict(results)
    results["round_trips"] = enriched
    return results
