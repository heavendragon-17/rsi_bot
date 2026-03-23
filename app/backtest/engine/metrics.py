"""
Backtest metric computation functions.
Extracted from BacktestEngine static methods.
"""

import math

import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger()

# All exit_reason values that represent a stop-loss variant
_SL_LABELS = {"SL", "STOP_LOSS", "BREAKEVEN", "LOCK_PROFIT", "STOP_MARKET"}


def build_round_trips(trades_df: pd.DataFrame) -> pd.DataFrame:
    """Pair entries with exits to form complete round-trips.

    Handles both LONG (BUY entry, SELL exits) and SHORT (SELL entry, BUY exits).
    Groups by symbol first so that portfolio-mode interleaved trades
    from different symbols are never mixed into the same round-trip.
    """
    if trades_df.empty:
        return pd.DataFrame()

    round_trips = []

    if "symbol" in trades_df.columns:
        groups = trades_df.groupby("symbol", sort=False)
    else:
        groups = [("_", trades_df)]

    for _symbol, symbol_trades in groups:
        current_entry = None
        partial_exits: list[dict] = []
        total_pnl = 0.0
        total_exit_amount = 0.0

        for _, trade in symbol_trades.iterrows():
            trade_pnl = trade.get("pnl")
            has_pnl = trade_pnl is not None and not (isinstance(trade_pnl, float) and math.isnan(trade_pnl))
            trade_is_exit = has_pnl

            if current_entry is None or not trade_is_exit:
                if current_entry is not None:
                    if partial_exits:
                        round_trips.append(
                            create_round_trip(current_entry, partial_exits, total_pnl, total_exit_amount)
                        )
                    else:
                        logger.warning(
                            "round_trip_no_exits",
                            symbol=_symbol,
                            entry_time=current_entry.get("time"),
                            entry_side=current_entry.get("side"),
                        )
                current_entry = trade
                partial_exits = []
                total_pnl = 0.0
                total_exit_amount = 0.0
            else:
                partial_exits.append(trade)
                if trade_pnl is not None:
                    total_pnl += float(trade_pnl)
                total_exit_amount += float(trade["amount"])

        if current_entry is not None:
            if partial_exits:
                round_trips.append(create_round_trip(current_entry, partial_exits, total_pnl, total_exit_amount))
            else:
                logger.warning(
                    "round_trip_no_exits",
                    symbol=_symbol,
                    entry_time=current_entry.get("time"),
                    entry_side=current_entry.get("side"),
                )

    if round_trips:
        round_trips.sort(key=lambda rt: rt.get("entry_time") or "")

    return pd.DataFrame(round_trips) if round_trips else pd.DataFrame()


def create_round_trip(entry, exits, total_pnl, total_exit_amount) -> dict:
    """Build a single round-trip dict from an entry and its partial exits."""
    last_exit = exits[-1]

    def get_exit_reason(e):
        return e.get("info", {}).get("exit_reason") or ""

    exit_reasons = [get_exit_reason(e) for e in exits if get_exit_reason(e)]
    final_exit_reason = _get_highest_exit_reason(exit_reasons)

    hold_duration_seconds = None
    if entry.get("time") is not None and last_exit.get("time") is not None:
        try:
            entry_time = pd.to_datetime(entry["time"])
            exit_time = pd.to_datetime(last_exit["time"])
            hold_duration_seconds = (exit_time - entry_time).total_seconds()
        except Exception:
            pass

    total_revenue = sum(e.get("price", 0) * e.get("amount", 0) for e in exits)
    avg_exit_price = total_revenue / total_exit_amount if total_exit_amount > 0 else 0

    entry_margin = entry.get("margin", entry.get("notional", 1))
    entry_notional = entry.get("notional", entry_margin)
    pnl_pct = (total_pnl / entry_margin) * 100 if entry_margin and entry_margin > 0 else 0

    entry_side = entry.get("side", "BUY")
    trade_side = "SHORT" if entry_side == "SELL" else "LONG"

    return {
        "entry_time": entry.get("time"),
        "exit_time": last_exit.get("time"),
        "symbol": entry.get("symbol"),
        "side": trade_side,
        "entry_price": entry.get("price"),
        "exit_price": last_exit.get("price"),
        "avg_exit_price": float(avg_exit_price),
        "amount": entry.get("amount"),
        "exit_amount": total_exit_amount,
        "margin": entry_margin,
        "notional": entry_notional,
        "leverage": entry.get("leverage", 1),
        "pnl": total_pnl,
        "pnl_pct": pnl_pct,
        "hold_duration_seconds": hold_duration_seconds,
        "hold_duration_hours": (hold_duration_seconds / 3600 if hold_duration_seconds else None),
        "exit_reason": final_exit_reason,
        "num_partial_exits": len(exits),
        "hit_tp1": any(get_exit_reason(e) == "TP1" for e in exits),
        "hit_tp2": any(get_exit_reason(e) == "TP2" for e in exits),
        "hit_tp3": any(get_exit_reason(e) == "TP3" for e in exits),
        "hit_sl": any(get_exit_reason(e) in ("SL", "STOP_LOSS") for e in exits),
    }


def _get_highest_exit_reason(exit_reasons: list) -> str:
    """Determine the highest-priority exit reason from a list of reasons."""
    has_sl = any(r in _SL_LABELS for r in exit_reasons)
    if has_sl:
        has_tp = any(r and r.startswith("TP") for r in exit_reasons)
        if has_tp:
            for tp in ["TP3", "TP2", "TP1"]:
                if tp in exit_reasons:
                    return f"{tp}+SL"
        return "SL"
    for tp in ["TP3", "TP2", "TP1"]:
        if tp in exit_reasons:
            return tp
    return exit_reasons[0] if exit_reasons else "UNKNOWN"


def calculate_metrics(round_trips: pd.DataFrame) -> dict:
    """Compute win rate, PnL stats, exit counts, and streaks."""
    if round_trips.empty:
        return {}

    total_trades = len(round_trips)
    wins = round_trips[round_trips["pnl"] > 0]
    losses = round_trips[round_trips["pnl"] <= 0]
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0

    total_pnl = round_trips["pnl"].sum()
    avg_pnl = round_trips["pnl"].mean()
    avg_win = wins["pnl"].mean() if len(wins) > 0 else 0
    avg_loss = losses["pnl"].mean() if len(losses) > 0 else 0
    largest_win = round_trips["pnl"].max()
    largest_loss = round_trips["pnl"].min()

    gross_profit = wins["pnl"].sum() if len(wins) > 0 else 0
    gross_loss = abs(losses["pnl"].sum()) if len(losses) > 0 else 0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")
    risk_reward = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")
    expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss)

    hold_hours = round_trips["hold_duration_hours"].dropna()
    avg_hold_hours = hold_hours.mean() if len(hold_hours) > 0 else 0

    tp1_count = int(round_trips["hit_tp1"].sum())
    tp2_count = int(round_trips["hit_tp2"].sum())
    tp3_count = int(round_trips["hit_tp3"].sum())
    sl_count = int(round_trips["hit_sl"].sum())
    exit_reason_counts = round_trips["exit_reason"].value_counts().to_dict()

    pnl_signs = (round_trips["pnl"] > 0).astype(int)
    max_consec_wins = max_consecutive(pnl_signs, 1)
    max_consec_losses = max_consecutive(pnl_signs, 0)

    return {
        "total_trades": total_trades,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": win_rate,
        "total_pnl": float(total_pnl),
        "avg_pnl": float(avg_pnl),
        "avg_win": float(avg_win),
        "avg_loss": float(avg_loss),
        "largest_win": float(largest_win),
        "largest_loss": float(largest_loss),
        "profit_factor": profit_factor,
        "risk_reward": risk_reward,
        "expectancy": float(expectancy),
        "avg_hold_hours": float(avg_hold_hours),
        "tp1_count": tp1_count,
        "tp2_count": tp2_count,
        "tp3_count": tp3_count,
        "sl_count": sl_count,
        "exit_reason_counts": exit_reason_counts,
        "max_consec_wins": max_consec_wins,
        "max_consec_losses": max_consec_losses,
        "gross_profit": float(gross_profit),
        "gross_loss": float(gross_loss),
    }


def max_consecutive(series, value) -> int:
    """Count max consecutive occurrences of value in a series."""
    max_count = 0
    current = 0
    for v in series:
        if v == value:
            current += 1
            max_count = max(max_count, current)
        else:
            current = 0
    return max_count


def calculate_drawdown(round_trips: pd.DataFrame, initial_balance: float) -> dict:
    """Compute max drawdown, average drawdown, and equity curve."""
    if round_trips.empty or "pnl" not in round_trips.columns:
        return {
            "max_drawdown_pct": 0,
            "max_drawdown_value": 0,
            "equity_curve": [float(initial_balance)],
            "max_dd_duration": 0,
            "avg_drawdown_pct": 0,
        }

    cumulative_pnl = round_trips["pnl"].cumsum().tolist()
    equity_curve = [initial_balance] + [initial_balance + p for p in cumulative_pnl]

    peak = equity_curve[0]
    max_dd = max_dd_value = 0.0
    max_dd_duration = current_dd_duration = 0
    all_drawdowns = []

    for val in equity_curve:
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

    if current_dd_duration > 0:
        max_dd_duration = max(max_dd_duration, current_dd_duration)

    avg_drawdown = sum(all_drawdowns) / len(all_drawdowns) if all_drawdowns else 0

    return {
        "max_drawdown_pct": max_dd * 100,
        "max_drawdown_value": max_dd_value,
        "equity_curve": equity_curve,
        "max_dd_duration": max_dd_duration,
        "avg_drawdown_pct": avg_drawdown,
    }


def calculate_risk_metrics(round_trips: pd.DataFrame, drawdown: dict, initial_balance: float) -> dict:
    """Compute Sharpe, Sortino, Calmar ratios and volatility."""
    zero = {"sharpe_ratio": 0, "sortino_ratio": 0, "calmar_ratio": 0, "volatility": 0, "var_95": 0}
    if round_trips.empty:
        return zero

    returns = round_trips["pnl_pct"].values / 100
    if len(returns) < 2:
        return zero

    mean_return = np.mean(returns)
    std_return = np.std(returns, ddof=1)
    volatility = std_return * 100
    sharpe_ratio = mean_return / std_return if std_return > 0 else 0

    negative_returns = returns[returns < 0]
    downside_std = np.std(negative_returns, ddof=1) if len(negative_returns) > 1 else 0
    sortino_ratio = mean_return / downside_std if downside_std > 0 else 0

    var_95 = np.percentile(returns, 5) * 100 if len(returns) >= 5 else min(returns) * 100

    realized_pnl = float(round_trips["pnl"].sum())
    total_return = (realized_pnl / initial_balance) * 100 if initial_balance > 0 else 0
    max_dd = drawdown.get("max_drawdown_pct", 0)
    calmar_ratio = total_return / max_dd if max_dd > 0 else 0

    return {
        "sharpe_ratio": sharpe_ratio,
        "sortino_ratio": sortino_ratio,
        "calmar_ratio": calmar_ratio,
        "volatility": volatility,
        "var_95": var_95,
    }


def calculate_monthly_returns(round_trips: pd.DataFrame) -> dict:
    """Aggregate PnL by calendar month."""
    if round_trips.empty or "exit_time" not in round_trips.columns:
        return {}

    df = round_trips.copy()
    df["exit_time"] = pd.to_datetime(df["exit_time"])
    df["month"] = df["exit_time"].dt.to_period("M")

    monthly = df.groupby("month").agg(pnl=("pnl", "sum"), trades=("pnl", "count"))

    return {
        str(period): {
            "pnl": float(row["pnl"]),
            "pnl_pct": 0.0,
            "trades": int(row["trades"]),
        }
        for period, row in monthly.iterrows()
    }
