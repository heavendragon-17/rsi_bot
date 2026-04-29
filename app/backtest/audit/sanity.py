"""Sanity audits — three cheap structural checks before the heavy statistics.

Each check returns a self-contained dict with at minimum a `passed` boolean.
The wrapper `run_sanity_audits` aggregates them and surfaces an overall
`passed` for the report's verdict logic.

Checks
------
1. **pnl_concentration** — top-N |ret_abs| share of total |ret_abs|.
   Catches strategies whose entire edge sits in 1-2 lucky trades. Pass
   when share < `SANITY_TOP_TRADE_SHARE_MAX` (0.50).

2. **long_short_symmetry** — aggregate `ret_abs` per side. A symmetric
   long/short strategy should make money on both sides; if one direction
   is structurally broken the strategy is half-fragile and should fail.
   Skipped (returns `applicable=False`, `passed=True`) when the caller
   declares `single_direction=True` — that flag is *not* inferred from
   data, the caller must pass it explicitly.

3. **cost_sensitivity** — subtract a stressed round-trip cost from every
   trade's `ret_pct` and check the stressed total stays positive. The
   stress amount is::

       stress_per_trade = M × (2 × DEFAULT_TAKER_FEE) × 100

   where M = `SANITY_COST_STRESS_FEE_MULTIPLIER` (default 2),
   `DEFAULT_TAKER_FEE` = 0.0005 per leg (10 bps round-trip), and the
   ×100 lifts the fraction-valued fee into the percent-valued units of
   `ret_pct` (which is stored as `pnl / notional × 100`). At M=2 this
   subtracts 0.20 (i.e. 0.20%) from each trade. This is a *conservative*
   stress: the original `ret_pct` already had baseline fees deducted, so
   subtracting another M × base on top is harsher than literally
   "doubling fees" — it's the framing the audit spec asked for and
   matches the wording in `docs/17_audit/audit.md`.

   The slippage component the spec mentions ("+1 tick extra slippage")
   is omitted in v1 because tick-size is symbol-dependent and not
   exposed through the audit's canonical inputs. Pure fee stress only.
   TODO(audit-slippage): revisit once a per-symbol tick-size lookup
   exists; the constant `SANITY_COST_STRESS_EXTRA_SLIPPAGE_TICKS` is
   reserved in `audit/constants.py` for this.
"""

from __future__ import annotations

import pandas as pd

from app.backtest.audit.constants import (
    SANITY_COST_STRESS_FEE_MULTIPLIER,
    SANITY_TOP_TRADE_COUNT,
    SANITY_TOP_TRADE_SHARE_MAX,
)
from app.backtest.audit.trade_log import TradeLog
from app.core.actions import SIDE_BUY, SIDE_SELL
from app.core.constants import DEFAULT_TAKER_FEE

_PERCENT_FACTOR = 100.0  # ret_pct stored as percent (pnl / notional × 100)


def _check_pnl_concentration(df: pd.DataFrame) -> dict:
    """Top-N |ret_abs| share of total |ret_abs|."""
    abs_ret = df["ret_abs"].abs()
    total = float(abs_ret.sum())
    if total == 0.0:
        return {
            "value": 0.0,
            "threshold": SANITY_TOP_TRADE_SHARE_MAX,
            "passed": True,
            "top_trade_count": 0,
            "total_trade_count": int(len(df)),
            "note": "all trades have zero |ret_abs|",
        }
    top_n = int(min(SANITY_TOP_TRADE_COUNT, len(abs_ret)))
    top_share = float(abs_ret.nlargest(top_n).sum()) / total
    return {
        "value": top_share,
        "threshold": SANITY_TOP_TRADE_SHARE_MAX,
        "passed": top_share < SANITY_TOP_TRADE_SHARE_MAX,
        "top_trade_count": top_n,
        "total_trade_count": int(len(df)),
        "total_abs_ret": total,
    }


def _check_long_short_symmetry(df: pd.DataFrame, single_direction: bool) -> dict:
    """Both-sides positive PnL, or skipped when single_direction is declared."""
    if single_direction:
        return {
            "applicable": False,
            "passed": True,
            "reason": "single_direction strategy",
        }
    by_side = df.groupby("side")["ret_abs"].sum().to_dict()
    buy_pnl = float(by_side.get(SIDE_BUY, 0.0))
    sell_pnl = float(by_side.get(SIDE_SELL, 0.0))
    n_buy = int((df["side"] == SIDE_BUY).sum())
    n_sell = int((df["side"] == SIDE_SELL).sum())
    passed = n_buy > 0 and n_sell > 0 and buy_pnl > 0 and sell_pnl > 0
    return {
        "applicable": True,
        "passed": passed,
        "buy_pnl": buy_pnl,
        "sell_pnl": sell_pnl,
        "buy_trade_count": n_buy,
        "sell_trade_count": n_sell,
    }


def _check_cost_sensitivity(df: pd.DataFrame) -> dict:
    """Subtract M × base round-trip cost from every trade's ret_pct."""
    base_round_trip_cost_pct = 2.0 * DEFAULT_TAKER_FEE * _PERCENT_FACTOR
    stress_per_trade_pct = float(SANITY_COST_STRESS_FEE_MULTIPLIER) * base_round_trip_cost_pct
    stressed = df["ret_pct"] - stress_per_trade_pct
    stressed_total = float(stressed.sum())
    return {
        "passed": stressed_total > 0.0,
        "stressed_total_ret_pct": stressed_total,
        "original_total_ret_pct": float(df["ret_pct"].sum()),
        "stress_per_trade_pct": stress_per_trade_pct,
        "fee_multiplier": SANITY_COST_STRESS_FEE_MULTIPLIER,
        "base_round_trip_cost_pct": base_round_trip_cost_pct,
        "trade_count": int(len(df)),
    }


def run_sanity_audits(
    tl: TradeLog,
    *,
    single_direction: bool = False,
) -> dict:
    """Run all three sanity checks and return an aggregated result.

    `single_direction` must be set explicitly by the caller. The audit
    pipeline never infers it from data, because a backtest with only
    one realized side may simply have lacked setups on the other side
    — not be structurally single-direction.
    """
    df = tl.df
    if df.empty:
        return {
            "passed": False,
            "trade_count": 0,
            "reason": "no closed trades",
        }
    pnl_conc = _check_pnl_concentration(df)
    symmetry = _check_long_short_symmetry(df, single_direction=single_direction)
    cost = _check_cost_sensitivity(df)
    return {
        "passed": bool(pnl_conc["passed"] and symmetry["passed"] and cost["passed"]),
        "trade_count": int(len(df)),
        "single_direction_declared": bool(single_direction),
        "pnl_concentration": pnl_conc,
        "long_short_symmetry": symmetry,
        "cost_sensitivity": cost,
    }
