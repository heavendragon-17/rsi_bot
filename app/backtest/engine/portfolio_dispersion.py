"""Per-symbol cumulative return dispersion for portfolio equity curves."""

from __future__ import annotations


def build_symbol_dispersion(
    round_trips_list: list, equity_curve: list, initial: float
) -> list:
    """Compute per-symbol cumulative % return at each equity curve date.

    Returns ``[{"date": "YYYY-MM-DD", "min": float, "max": float}]`` — the
    range of symbol returns at each point in time. Returns [] if fewer than
    2 symbols traded.
    """
    if not round_trips_list or not equity_curve or initial <= 0:
        return []

    events: list[tuple[str, str, float]] = []
    for rt in round_trips_list:
        sym = str(rt.get("symbol", ""))
        exit_time = rt.get("exit_time")
        if exit_time is None or not sym:
            continue
        date_str = exit_time.isoformat()[:10] if hasattr(exit_time, "isoformat") else str(exit_time)[:10]
        events.append((date_str, sym, float(rt.get("pnl", 0))))

    if not events:
        return []

    all_syms = sorted({e[1] for e in events})
    if len(all_syms) < 2:
        return []

    events.sort()
    cum_pnls: dict[str, float] = {s: 0.0 for s in all_syms}
    dispersion: list[dict] = []
    evt_idx = 0
    n_events = len(events)

    for point in equity_curve:
        date = str(point.get("date", ""))[:10]
        while evt_idx < n_events and events[evt_idx][0] <= date:
            _, sym, pnl = events[evt_idx]
            if sym in cum_pnls:
                cum_pnls[sym] += pnl
            evt_idx += 1
        pcts = [v / initial * 100 for v in cum_pnls.values()]
        dispersion.append({"date": date, "min": round(min(pcts), 4), "max": round(max(pcts), 4)})

    return dispersion
