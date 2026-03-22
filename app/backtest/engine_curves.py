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
