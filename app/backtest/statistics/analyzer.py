"""
Statistical analyzer for backtest round-trip trade results.

Reads a backtest CSV and produces:
  1. Core metrics (win rate, EV, reward-to-risk)
  2. Stress tests (monthly/quarterly breakdown, market regime splits)
  3. Risk metrics (max consecutive losses, max drawdown, std dev)
  4. Visualizations (equity curve, win/loss distribution, monthly bars)

Usage:
    python -m app.backtest.statistics.analyzer \
        --trades app/backtest/report/csv/backtest_trades_BTCUSDT_15m.csv \
        --balance 100000 \
        --output app/backtest/report/stats
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd
import structlog

from app.backtest.statistics.metrics import (
    compute_core_metrics,
    compute_monthly_breakdown,
    compute_quarterly_breakdown,
    compute_regime_breakdown,
    compute_risk_metrics,
)
from app.backtest.statistics.visualize import generate_all_charts

logger = structlog.get_logger()


def load_trades(path: str) -> pd.DataFrame:
    """Load round-trip trades CSV and parse timestamps."""
    df = pd.read_csv(path)
    for col in ("entry_time", "exit_time"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])
    return df


def print_section(title: str) -> None:
    width = 60
    print(f"\n{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}")


def print_metric(label: str, value, fmt: str = "") -> None:
    if fmt:
        print(f"  {label:<35s} {value:{fmt}}")
    else:
        print(f"  {label:<35s} {value}")


def run_analysis(trades_path: str, initial_balance: float, output_dir: str) -> dict:
    """Run full statistical analysis and return results dict."""
    df = load_trades(trades_path)
    if df.empty:
        logger.error("no_trades_found", path=trades_path)
        return {}

    logger.info("trades_loaded", count=len(df), path=trades_path)

    # ── 1. Core Metrics ──────────────────────────────────────────────
    core = compute_core_metrics(df)
    print_section("CORE METRICS")
    print_metric("Total trades", core["total_trades"])
    print_metric("Winning trades", core["win_count"])
    print_metric("Losing trades", core["loss_count"])
    print_metric("Win rate", core["win_rate"], ".2f")
    print_metric("Avg win ($)", core["avg_win"], ",.2f")
    print_metric("Avg loss ($)", core["avg_loss"], ",.2f")
    print_metric("EV per trade ($)", core["ev_per_trade"], ",.2f")
    print_metric("Reward-to-Risk ratio", core["reward_to_risk"], ".2f")
    print_metric("Profit factor", core["profit_factor"], ".2f")
    print_metric("Expectancy ($)", core["expectancy"], ",.2f")
    print_metric("Total PnL ($)", core["total_pnl"], ",.2f")

    # ── 2. Stress Tests ──────────────────────────────────────────────
    monthly = compute_monthly_breakdown(df)
    print_section("MONTHLY BREAKDOWN")
    print(f"  {'Month':<12s} {'Trades':>7s} {'Wins':>6s} {'WR%':>7s} {'PnL ($)':>12s}")
    print(f"  {'-' * 46}")
    for _, row in monthly.iterrows():
        print(
            f"  {row['month']:<12s} {row['trades']:>7d} "
            f"{row['wins']:>6d} {row['win_rate']:>6.1f}% "
            f"{row['pnl']:>12,.2f}"
        )

    quarterly = compute_quarterly_breakdown(df)
    if not quarterly.empty:
        print_section("QUARTERLY BREAKDOWN")
        print(f"  {'Quarter':<12s} {'Trades':>7s} {'Wins':>6s} {'WR%':>7s} {'PnL ($)':>12s}")
        print(f"  {'-' * 46}")
        for _, row in quarterly.iterrows():
            print(
                f"  {row['quarter']:<12s} {row['trades']:>7d} "
                f"{row['wins']:>6d} {row['win_rate']:>6.1f}% "
                f"{row['pnl']:>12,.2f}"
            )

    regime = compute_regime_breakdown(df)
    if regime is not None:
        print_section("MARKET REGIME BREAKDOWN")
        print(f"  {'Regime':<15s} {'Trades':>7s} {'Wins':>6s} {'WR%':>7s} {'PnL ($)':>12s}")
        print(f"  {'-' * 49}")
        for _, row in regime.iterrows():
            print(
                f"  {row['regime']:<15s} {row['trades']:>7d} "
                f"{row['wins']:>6d} {row['win_rate']:>6.1f}% "
                f"{row['pnl']:>12,.2f}"
            )

    # ── 3. Risk Metrics ──────────────────────────────────────────────
    risk = compute_risk_metrics(df, initial_balance)
    print_section("RISK METRICS")
    print_metric("Max consecutive losses", risk["max_consec_losses"])
    print_metric("Max consecutive wins", risk["max_consec_wins"])
    print_metric("Max drawdown ($)", risk["max_drawdown_value"], ",.2f")
    print_metric("Max drawdown (%)", risk["max_drawdown_pct"], ".2f")
    print_metric("Std dev of returns (%)", risk["std_dev_pct"], ".2f")
    print_metric("Sharpe ratio (trade-level)", risk["sharpe_ratio"], ".3f")
    print_metric("Sortino ratio (trade-level)", risk["sortino_ratio"], ".3f")
    print_metric("VaR 95% (%)", risk["var_95_pct"], ".2f")

    # ── 4. Visualizations ────────────────────────────────────────────
    os.makedirs(output_dir, exist_ok=True)
    chart_paths = generate_all_charts(
        df, initial_balance=initial_balance, monthly=monthly, output_dir=output_dir
    )
    print_section("CHARTS SAVED")
    for name, path in chart_paths.items():
        print(f"  {name:<30s} {path}")

    results = {
        "core": core,
        "monthly": monthly.to_dict(orient="records"),
        "quarterly": quarterly.to_dict(orient="records") if not quarterly.empty else [],
        "regime": regime.to_dict(orient="records") if regime is not None else [],
        "risk": risk,
        "charts": chart_paths,
    }
    logger.info("analysis_complete", total_trades=core["total_trades"])
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Statistical analysis of backtest trades")
    parser.add_argument("--trades", required=True, help="Path to round-trip trades CSV")
    parser.add_argument("--balance", type=float, default=100000, help="Initial balance")
    parser.add_argument("--output", default="app/backtest/report/stats", help="Output dir for charts")
    args = parser.parse_args()

    run_analysis(args.trades, args.balance, args.output)


if __name__ == "__main__":
    main()
