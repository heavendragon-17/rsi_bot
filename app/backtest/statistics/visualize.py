"""
Chart generation for backtest statistical analysis.

Produces PNG files:
  - equity_curve.png   — cumulative P&L over time
  - pnl_distribution.png — histogram of trade P&L
  - monthly_performance.png — bar chart of monthly returns
"""

from __future__ import annotations

import os

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")  # headless backend
import matplotlib.pyplot as plt


def generate_all_charts(
    df: pd.DataFrame,
    initial_balance: float,
    monthly: pd.DataFrame,
    output_dir: str,
) -> dict[str, str]:
    """Generate all charts and return {name: filepath} map."""
    paths: dict[str, str] = {}

    paths["equity_curve"] = _plot_equity_curve(df, initial_balance, output_dir)
    paths["pnl_distribution"] = _plot_pnl_distribution(df, output_dir)
    paths["monthly_performance"] = _plot_monthly_performance(monthly, output_dir)

    return paths


def _plot_equity_curve(df: pd.DataFrame, initial_balance: float, output_dir: str) -> str:
    """Line chart of account equity over trade sequence."""
    equity = [initial_balance]
    for pnl in df["pnl"]:
        equity.append(equity[-1] + pnl)

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(range(len(equity)), equity, linewidth=1.5, color="#2196F3")
    ax.axhline(y=initial_balance, color="gray", linestyle="--", alpha=0.5, label="Initial")
    ax.fill_between(
        range(len(equity)),
        equity,
        initial_balance,
        where=[e >= initial_balance for e in equity],
        alpha=0.15,
        color="green",
    )
    ax.fill_between(
        range(len(equity)),
        equity,
        initial_balance,
        where=[e < initial_balance for e in equity],
        alpha=0.15,
        color="red",
    )
    ax.set_title("Equity Curve", fontsize=14, fontweight="bold")
    ax.set_xlabel("Trade #")
    ax.set_ylabel("Balance ($)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    path = os.path.join(output_dir, "equity_curve.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _plot_pnl_distribution(df: pd.DataFrame, output_dir: str) -> str:
    """Histogram of per-trade P&L with win/loss coloring."""
    wins = df[df["pnl"] > 0]["pnl"]
    losses = df[df["pnl"] <= 0]["pnl"]

    fig, ax = plt.subplots(figsize=(10, 5))

    bin_edges: list[float] = np.linspace(df["pnl"].min(), df["pnl"].max(), 25).tolist()
    ax.hist(wins, bins=bin_edges, color="#4CAF50", alpha=0.7, label=f"Wins ({len(wins)})")
    ax.hist(losses, bins=bin_edges, color="#F44336", alpha=0.7, label=f"Losses ({len(losses)})")
    ax.axvline(x=0, color="black", linestyle="-", linewidth=0.8)
    ax.axvline(x=df["pnl"].mean(), color="blue", linestyle="--", linewidth=1, label=f"Mean: ${df['pnl'].mean():,.0f}")

    ax.set_title("Win/Loss Distribution", fontsize=14, fontweight="bold")
    ax.set_xlabel("P&L ($)")
    ax.set_ylabel("Frequency")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    path = os.path.join(output_dir, "pnl_distribution.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _plot_monthly_performance(monthly: pd.DataFrame, output_dir: str) -> str:
    """Bar chart of monthly P&L with win rate overlay."""
    if monthly.empty:
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.text(0.5, 0.5, "No monthly data", ha="center", va="center", fontsize=14)
        path = os.path.join(output_dir, "monthly_performance.png")
        fig.savefig(path, dpi=150)
        plt.close(fig)
        return path

    fig, ax1 = plt.subplots(figsize=(12, 6))

    colors = ["#4CAF50" if p >= 0 else "#F44336" for p in monthly["pnl"]]
    x = range(len(monthly))
    ax1.bar(x, monthly["pnl"], color=colors, alpha=0.7, label="P&L ($)")
    ax1.set_ylabel("P&L ($)", color="black")
    ax1.axhline(y=0, color="gray", linestyle="-", linewidth=0.5)

    # Win rate on secondary axis
    ax2 = ax1.twinx()
    ax2.plot(x, monthly["win_rate"], "o-", color="#FF9800", linewidth=2, markersize=6, label="Win Rate %")
    ax2.set_ylabel("Win Rate (%)", color="#FF9800")
    ax2.set_ylim(0, 100)

    ax1.set_xticks(list(x))
    ax1.set_xticklabels(monthly["month"], rotation=45, ha="right")
    ax1.set_title("Monthly Performance", fontsize=14, fontweight="bold")
    ax1.grid(True, alpha=0.3, axis="y")

    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")

    fig.tight_layout()
    path = os.path.join(output_dir, "monthly_performance.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path
