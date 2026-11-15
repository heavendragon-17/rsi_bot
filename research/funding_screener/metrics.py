"""Pair building and funding-spread statistics.

Sign convention: ``rate_h`` > 0 means longs pay. For a pair "long A / short B"
the hourly carry is ``rate_B - rate_A`` (the short collects B's funding, the
long pays A's). This is the signed net spread; adding absolute values (the
mistake in the KOL post) overstates the carry whenever both rates share a sign.
"""

from __future__ import annotations

import math
import statistics
import time
from collections import defaultdict
from collections.abc import Iterable

from venues import DAY, HOUR, Market

HOURS_PER_YEAR = 8760
PRICE_TOLERANCE = 0.04  # legs whose unit prices differ more than 4% are different assets
MIN_HISTORY_HOURS = 72  # below this the 30d rules are not applied
SPIKE_MIN_APR = 30.0


def apr(rate_h: float) -> float:
    return rate_h * HOURS_PER_YEAR * 100


def same_asset(a: Market, b: Market) -> bool:
    pa, pb = a.unit_price, b.unit_price
    if not pa or not pb:
        return True
    return abs(pa - pb) / min(pa, pb) <= PRICE_TOLERANCE


def build_pairs(markets: Iterable[Market]) -> list[tuple[Market, Market]]:
    """Return (long_leg, short_leg) for every cross-venue listing of the same asset.

    The direction is the one with a positive current spread.
    """
    by_sym: dict[str, list[Market]] = defaultdict(list)
    for m in markets:
        by_sym[m.symbol].append(m)
    pairs: list[tuple[Market, Market]] = []
    for legs in by_sym.values():
        for i, a in enumerate(legs):
            for b in legs[i + 1:]:
                if a.venue == b.venue or not same_asset(a, b):
                    continue
                pairs.append((a, b) if b.rate_h >= a.rate_h else (b, a))
    return pairs


def spread_series(hist_long: dict[int, float], hist_short: dict[int, float], since: int) -> list[tuple[int, float]]:
    hours = sorted(h for h in hist_long.keys() & hist_short.keys() if h >= since)
    return [(h, hist_short[h] - hist_long[h]) for h in hours]


def _mean_apr(series: list[tuple[int, float]], since: int) -> float | None:
    vals = [v for h, v in series if h >= since]
    return apr(sum(vals) / len(vals)) if vals else None


def daily_flips(series: list[tuple[int, float]]) -> int:
    days: dict[int, list[float]] = defaultdict(list)
    for h, v in series:
        days[h // DAY].append(v)
    signs = [math.copysign(1, sum(v)) for _, v in sorted(days.items()) if sum(v) != 0]
    return sum(1 for x, y in zip(signs, signs[1:], strict=False) if x != y)


def spread_risk(series: list[tuple[int, float]], sust: float | None, avg7: float | None) -> str | None:
    """LOW / MED / HIGH from 7d volatility of the hourly spread.

    Our own approximation (ProFunding does not publish its formula):
    coefficient of variation of the hourly spread over 7 days, tightened by
    sustainability and the sign of the 7d average.
    """
    if not series:
        return None
    week_start = series[-1][0] - 7 * DAY
    vals = [v for h, v in series if h >= week_start]
    if len(vals) < 24 or avg7 is None:
        return None
    mean = sum(vals) / len(vals)
    if mean <= 0:
        return "HIGH"
    cv = statistics.pstdev(vals) / mean
    if cv > 3 or (sust is not None and sust < 70):
        return "HIGH"
    if cv < 1.0 and (sust is None or sust >= 85):
        return "LOW"
    return "MED"


def pair_stats(long_leg: Market, short_leg: Market, hist_long: dict[int, float] | None,
               hist_short: dict[int, float] | None, now: float | None = None) -> dict:
    now = now or time.time()
    now_rate = short_leg.rate_h - long_leg.rate_h
    out: dict = {
        "now_rate_h": now_rate, "now_apr": apr(now_rate),
        "avg24_apr": None, "avg7_apr": None, "avg30_apr": None, "sust30": None,
        "hist_hours": 0, "flips": None, "risk": None, "spike": False, "flip": False, "drop": False,
        "drop_reason": None,
    }
    if not hist_long or not hist_short:
        return out
    since30 = int(now - 30 * DAY)
    series = spread_series(hist_long, hist_short, since30)
    out["hist_hours"] = len(series)
    if not series:
        return out
    out["avg24_apr"] = _mean_apr(series, int(now - DAY))
    out["avg7_apr"] = _mean_apr(series, int(now - 7 * DAY))
    out["avg30_apr"] = _mean_apr(series, since30)
    out["sust30"] = 100.0 * sum(1 for _, v in series if v > 0) / len(series)
    out["flips"] = daily_flips(series)
    out["risk"] = spread_risk(series, out["sust30"], out["avg7_apr"])

    ref = max(x for x in (out["avg24_apr"], out["avg7_apr"], 0.0) if x is not None)
    out["spike"] = out["now_apr"] >= SPIKE_MIN_APR and out["now_apr"] > max(2 * ref, ref + 30)
    a7, a30 = out["avg7_apr"], out["avg30_apr"]
    out["flip"] = (out["flips"] or 0) >= 4 or (a7 is not None and a30 is not None and (a7 > 0) != (a30 > 0))
    if len(series) >= MIN_HISTORY_HOURS:
        if a30 is not None and a30 < 0:
            out["drop"], out["drop_reason"] = True, "TB 30 ngày âm"
        elif out["sust30"] <= 61:
            out["drop"], out["drop_reason"] = True, f"Sustainability {out['sust30']:.0f}% ≤ 61%"
    return out


def chart_series(hist_long: dict[int, float], hist_short: dict[int, float], days: int = 30) -> list[list[float]]:
    since = int(time.time() - days * DAY)
    return [[h, round(apr(v), 3)] for h, v in spread_series(hist_long, hist_short, since)]


def leg_view(m: Market) -> dict:
    return {
        "venue": m.venue, "raw": m.raw, "rate_h": m.rate_h, "apr": apr(m.rate_h), "interval_h": m.interval_h,
        "mark": m.mark, "bid": m.bid, "ask": m.ask, "spread_rel": m.spread_rel, "oi_usd": m.oi_usd,
        "vol_usd": m.vol_usd, "taker_pct": m.extra.get("taker_pct"),
    }


__all__ = ["HOUR", "apr", "build_pairs", "pair_stats", "chart_series", "leg_view", "same_asset"]
