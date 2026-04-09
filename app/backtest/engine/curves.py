"""
Equity and drawdown curve builders for backtest results.
Extracted from BacktestEngine static methods.
"""


def build_equity_curve_dated(round_trips_list: list, initial_balance: float) -> list:
    """Build ``[{date, balance}]`` annotated with each trade's exit timestamp."""
    curve = []
    balance = initial_balance
    for rt in round_trips_list:
        balance += rt.get("pnl") or 0
        exit_time = rt.get("exit_time")
        if hasattr(exit_time, "isoformat"):
            date_str = exit_time.isoformat()
        else:
            date_str = str(exit_time) if exit_time is not None else ""
        curve.append({"date": date_str, "balance": round(balance, 2)})
    return curve


def build_drawdown_curve_dated(equity_curve: list, initial_balance: float) -> list:
    """Build ``[{date, drawdown}]`` from the dated equity curve."""
    peak = initial_balance
    curve = []
    for point in equity_curve:
        balance = point["balance"]
        if balance > peak:
            peak = balance
        dd_pct = (peak - balance) / peak * 100 if peak > 0 else 0.0
        curve.append({"date": point["date"], "drawdown": round(dd_pct, 4)})
    return curve


def calculate_portfolio_drawdown(
    equity_curve: list[dict], initial_balance: float
) -> dict:
    """Calculate portfolio drawdown metrics from an equity curve.

    Args:
        equity_curve: List of {"date": str, "balance": float} dicts.
        initial_balance: Starting balance for peak tracking.

    Returns:
        Dict with max_drawdown_pct, max_drawdown_value, drawdown_curve,
        max_dd_duration, avg_drawdown_pct.
    """
    if not equity_curve:
        return {
            "max_drawdown_pct": 0,
            "max_drawdown_value": 0,
            "drawdown_curve": [],
            "max_dd_duration": 0,
            "avg_drawdown_pct": 0,
        }

    peak = initial_balance
    max_dd = 0.0
    max_dd_value = 0.0
    dd = 0.0
    current_dd_duration = 0
    max_dd_duration = 0
    all_drawdowns: list[float] = []
    dd_curve: list[dict] = []

    for point in equity_curve:
        val = point["balance"]
        date_str = point["date"]

        if val > peak:
            peak = val
            if current_dd_duration > 0:
                max_dd_duration = max(max_dd_duration, current_dd_duration)
            current_dd_duration = 0
        else:
            dd = (peak - val) / peak if peak > 0 else 0
            if dd > 0:
                all_drawdowns.append(dd * 100)
                current_dd_duration += 1
            if dd > max_dd:
                max_dd = dd
                max_dd_value = peak - val

        dd_curve.append({
            "date": date_str,
            "drawdown": round(dd * 100, 4) if val <= peak else 0.0,
        })

    if current_dd_duration > 0:
        max_dd_duration = max(max_dd_duration, current_dd_duration)

    avg_drawdown = sum(all_drawdowns) / len(all_drawdowns) if all_drawdowns else 0

    return {
        "max_drawdown_pct": max_dd * 100,
        "max_drawdown_value": max_dd_value,
        "drawdown_curve": dd_curve,
        "max_dd_duration": max_dd_duration,
        "avg_drawdown_pct": avg_drawdown,
    }
