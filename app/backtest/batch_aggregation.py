"""Batch backtest result aggregation — combined portfolio curves and metrics."""

from __future__ import annotations

import pandas as pd

from app.backtest.engine.curves import calculate_portfolio_drawdown


def build_batch_portfolio_curves(
    batch_results: list[dict], initial_capital: float
) -> tuple[list[dict], list[dict], list[dict], dict]:
    """Build combined portfolio equity, drawdown, and dispersion curves from batch results.

    Forward-fill rule per symbol: before first trade — excluded; after last trade —
    forward-fill with final balance. Prevents bias toward the latest-exiting symbol.
    """
    sym_curves: list[dict[str, float]] = []
    for r in batch_results:
        ec = r.get("equity_curve", [])
        if not ec or initial_capital <= 0:
            continue
        curve = {
            str(p.get("date", p.get("time", "")))[:10]: float(p["balance"])
            for p in ec
            if ("date" in p or "time" in p) and "balance" in p
        }
        if curve:
            sym_curves.append(curve)

    if not sym_curves:
        return [], [], [], {}

    all_dates = sorted(set().union(*(c.keys() for c in sym_curves)))
    sym_meta: list[tuple[dict[str, float], str, str]] = [
        (c, min(c.keys()), max(c.keys())) for c in sym_curves
    ]

    equity_curve: list[dict] = []
    dispersion_range: list[dict] = []

    for date in all_dates:
        pcts: list[float] = []
        for c, first, last in sym_meta:
            if date < first:
                continue
            balance = c[date] if date in c else c[last]
            pcts.append((balance - initial_capital) / initial_capital * 100)

        if not pcts:
            continue

        avg_pct = sum(pcts) / len(pcts)
        equity_curve.append({"date": date, "balance": round(initial_capital * (1 + avg_pct / 100), 2)})
        dispersion_range.append({"date": date, "min": round(min(pcts), 4), "max": round(max(pcts), 4)})

    dd_stats = calculate_portfolio_drawdown(equity_curve, initial_capital)
    return equity_curve, dd_stats["drawdown_curve"], dispersion_range, dd_stats


def aggregate_batch_results(
    batch_results: list[dict], initial_capital: float
) -> dict:
    """Aggregate per-symbol batch results into a single results dict for persistence."""
    if not batch_results:
        return {
            "net_profit": 0.0,
            "net_profit_pct": 0.0,
            "metrics": {},
            "drawdown": {},
            "risk_metrics": {},
            "equity_curve": [],
            "drawdown_curve": [],
            "dispersion_range": [],
            "monthly_returns": {},
            "round_trips": [],
        }

    n_symbols = max(len(batch_results), 1)
    total_profit = sum(r.get("profit", 0) for r in batch_results)
    total_trades = sum(r.get("trades", 0) for r in batch_results)

    all_metrics = [r.get("metrics", {}) for r in batch_results]
    win_counts = sum(m.get("win_count", 0) for m in all_metrics)
    loss_counts = sum(m.get("loss_count", 0) for m in all_metrics)
    gross_profits = sum(float(m.get("gross_profit", 0)) for m in all_metrics)
    gross_losses = sum(float(m.get("gross_loss", 0)) for m in all_metrics)

    win_rate = (win_counts / total_trades * 100) if total_trades > 0 else 0
    profit_factor = (gross_profits / abs(gross_losses)) if gross_losses != 0 else 0

    sharpe_values = [
        r.get("risk_metrics", {}).get("sharpe_ratio")
        for r in batch_results
        if r.get("risk_metrics", {}).get("sharpe_ratio") is not None
    ]
    avg_sharpe = sum(sharpe_values) / len(sharpe_values) if sharpe_values else None

    all_round_trips: list[dict] = []
    for r in batch_results:
        rt = r.get("round_trips")
        sym = r.get("symbol", "")
        if isinstance(rt, pd.DataFrame) and not rt.empty:
            rt_copy = rt.copy()
            if "symbol" not in rt_copy.columns:
                rt_copy["symbol"] = sym
            all_round_trips.extend(rt_copy.to_dict("records"))
        elif isinstance(rt, list):
            for item in rt:
                if isinstance(item, dict) and "symbol" not in item:
                    item = {**item, "symbol": sym}
                all_round_trips.append(item)

    equity_curve, drawdown_curve, dispersion_range, dd_stats = build_batch_portfolio_curves(
        batch_results, initial_capital
    )

    max_dd = dd_stats.get("max_drawdown_pct", 0)
    max_dd_value = dd_stats.get("max_drawdown_value", 0)

    return {
        "net_profit": total_profit,
        "net_profit_pct": (total_profit / (n_symbols * initial_capital) * 100) if initial_capital else 0,
        "metrics": {
            "total_trades": total_trades,
            "win_count": win_counts,
            "loss_count": loss_counts,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "gross_profit": gross_profits,
            "gross_loss": gross_losses,
            "sharpe_ratio": avg_sharpe,
        },
        "drawdown": {
            "max_drawdown_pct": max_dd,
            "max_drawdown_value": max_dd_value,
        },
        "risk_metrics": {
            "sharpe_ratio": avg_sharpe,
        },
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
        "dispersion_range": dispersion_range,
        "monthly_returns": {},
        "round_trips": all_round_trips,
    }
