"""Walk-forward backtest of the screener's delta-neutral rules on real funding history.

    python backtest.py --days 45 --sizes 10000,20000 --out results

What it does
1. Pulls the current market list from every venue that has a public funding
   history API (Hyperliquid + HIP-3, Lighter, QFEX, Extended, Aster) and keeps
   cross-venue pairs whose legs both have OI >= --min-oi.
2. Downloads hourly funding history for those legs (cached in --cache).
3. Replays day by day. At 00:00 UTC, using ONLY data before that hour:
   - close positions held >= --hold-days, or whose trailing 24h carry is <= 0;
   - rank candidates with the screener rules (lookback avg > 0, sustainability
     > 61% hard floor, spike filter, break-even <= --max-be-h) and open the best
     ones, one per symbol, up to --max-positions.
   Every hour each open position earns size x (rate_short - rate_long).
   Entry and exit each pay taker fee + half the bid/ask + --impact on both legs.
4. Also runs a naive baseline (highest current APR, no filters) for comparison.

Known biases (also written into the report): OI and bid/ask come from today's
snapshot, not from the past; price basis between venues and liquidation risk are
not simulated; 8h funding is spread evenly over the hours of its interval.
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import metrics
from venues import DAY, HOUR, VENUES, Market, spec_for

log = logging.getLogger("backtest")

DEFAULT_TAKER_PCT = {"Hyperliquid": 0.045, "HL:*": 0.09, "Lighter": 0.0, "QFEX": 0.05,
                     "Extended": 0.025, "Aster": 0.035}
DEFAULT_SPREAD_PCT = 0.05  # assumed full bid/ask when a venue gives none


@dataclass
class Position:
    symbol: str
    long_key: str
    short_key: str
    size: float
    opened: int
    entry_cost: float
    exit_cost: float
    funding: float = 0.0
    closed: int | None = None
    hours: int = 0
    reason: str = ""

    @property
    def net(self) -> float:
        return self.funding - self.entry_cost - (self.exit_cost if self.closed else 0.0)


@dataclass
class Run:
    name: str
    size: float
    open: list[Position] = field(default_factory=list)
    done: list[Position] = field(default_factory=list)
    daily: dict[int, float] = field(default_factory=lambda: defaultdict(float))


def taker_pct(venue: str) -> float:
    return DEFAULT_TAKER_PCT.get(venue, DEFAULT_TAKER_PCT["HL:*"] if venue.startswith("HL:") else 0.05)


def leg_cost(m: Market, size: float, impact_pct: float) -> float:
    """One side (entry OR exit) cost on one leg, in USD."""
    spread_pct = m.spread_rel * 100 if m.spread_rel is not None else DEFAULT_SPREAD_PCT
    return size * (taker_pct(m.venue) + spread_pct / 2 + impact_pct) / 100


def key(m: Market) -> str:
    return f"{m.venue}|{m.raw}"


# --------------------------------------------------------------------------- data


def load_universe(min_oi: float) -> list[tuple[Market, Market]]:
    markets: list[Market] = []
    for spec in VENUES:
        if spec.history is None:
            continue
        try:
            got = spec.fetch()
            log.info("%s: %d markets", spec.name, len(got))
            markets += got
        except Exception as exc:  # noqa: BLE001
            log.warning("%s snapshot failed: %s", spec.name, exc)
    for m in markets:  # enrich missing OI / bid-ask only for liquid-looking legs
        spec = spec_for(m.venue)
        if spec.enrich and (m.oi_usd is None or m.spread_rel is None):
            try:
                spec.enrich(m)
                time.sleep(spec.min_gap_s)
            except Exception:  # noqa: BLE001
                pass
    liquid = [m for m in markets if (m.oi_usd or 0) >= min_oi]
    pairs = metrics.build_pairs(liquid)
    log.info("liquid markets %d -> %d cross-venue pairs", len(liquid), len(pairs))
    return pairs


def load_history(legs: list[Market], days: int, cache: Path) -> dict[str, dict[int, float]]:
    cache.mkdir(parents=True, exist_ok=True)
    out: dict[str, dict[int, float]] = {}
    since = int(time.time() - days * DAY)
    for i, m in enumerate(legs, 1):
        f = cache / (key(m).replace("|", "__").replace(":", "_").replace("/", "_") + ".json")
        if f.exists() and time.time() - f.stat().st_mtime < 6 * HOUR:
            out[key(m)] = {int(k): v for k, v in json.loads(f.read_text()).items()}
            continue
        spec = spec_for(m.venue)
        try:
            data = spec.history(m, since)  # type: ignore[misc]
            f.write_text(json.dumps(data))
            out[key(m)] = data
        except Exception as exc:  # noqa: BLE001
            log.warning("history %s failed: %s", key(m), exc)
            out[key(m)] = {}
        if i % 25 == 0:
            log.info("history %d/%d legs", i, len(legs))
        time.sleep(spec.min_gap_s)
    return out


# --------------------------------------------------------------------------- strategy


def score_pair(hl: dict[int, float], hs: dict[int, float], t: int, lookback_h: int, cost_pct: float,
               max_be_h: float) -> dict | None:
    """Screener rules evaluated at hour t using data strictly before t."""
    series = [(h, hs[h] - hl[h]) for h in range(t - lookback_h * HOUR, t, HOUR) if h in hl and h in hs]
    if len(series) < lookback_h * 0.8:
        return None
    vals = [v for _, v in series]
    avg = sum(vals) / len(vals)
    sust = 100 * sum(1 for v in vals if v > 0) / len(vals)
    last24 = vals[-24:]
    avg24 = sum(last24) / len(last24)
    now = vals[-1]
    if avg <= 0 or sust <= 61 or avg24 <= 0:
        return None
    if metrics.apr(now) >= 30 and metrics.apr(now) > max(2 * metrics.apr(max(avg, avg24)), metrics.apr(avg) + 30):
        return None  # spike
    week = vals[-168:]
    cv = statistics.pstdev(week) / (sum(week) / len(week)) if sum(week) > 0 else 99
    risk = "LOW" if cv < 1 and sust >= 85 else "HIGH" if cv > 3 or sust < 70 else "MED"
    if risk == "HIGH" and sust < 85:
        return None
    expected_h = min(now, avg) if now > 0 else avg
    be_h = cost_pct / (expected_h * 100) if expected_h > 0 else float("inf")
    if be_h > max_be_h:
        return None
    tier = 0 if sust > 93 and risk != "HIGH" and be_h <= 14 else 1 if sust >= 90 else 2
    return {"sust": sust, "avg_apr": metrics.apr(avg), "be_h": be_h, "tier": tier, "risk": risk}


def run_backtest(pairs, hist, start: int, end: int, size: float, args, naive: bool) -> Run:
    run = Run(name="naive" if naive else "screener", size=size)
    lookback_h = args.lookback * 24

    def spread_at(p: Position, h: int) -> float | None:
        a, b = hist[p.long_key].get(h), hist[p.short_key].get(h)
        return None if a is None or b is None else b - a

    for t in range(start, end, HOUR):
        # accrue funding for the hour [t, t+1h)
        for p in run.open:
            s = spread_at(p, t)
            if s is not None:
                pnl = p.size * s
                p.funding += pnl
                run.daily[t // DAY * DAY] += pnl
            p.hours += 1
        if t % DAY:
            continue
        # daily decision at 00:00 UTC
        for p in list(run.open):
            last = [spread_at(p, h) for h in range(t - DAY, t, HOUR)]
            last = [x for x in last if x is not None]
            held_days = (t - p.opened) / DAY
            if held_days >= args.hold_days or (not naive and last and sum(last) <= 0):
                p.closed, p.reason = t, "hết hạn giữ" if held_days >= args.hold_days else "spread 24h âm"
                run.daily[t // DAY * DAY] -= p.exit_cost
                run.open.remove(p)
                run.done.append(p)
        held_syms = {p.symbol for p in run.open}
        cands = []
        for a, b in pairs:
            hl, hs = hist.get(key(a), {}), hist.get(key(b), {})
            if a.symbol in held_syms or not hl or not hs:
                continue
            for lo, sh, hlo, hsh in ((a, b, hl, hs), (b, a, hs, hl)):
                cost_usd = 2 * (leg_cost(lo, size, args.impact) + leg_cost(sh, size, args.impact))
                cost_pct = cost_usd / size * 100
                if naive:
                    now = [hsh.get(t - HOUR), hlo.get(t - HOUR)]
                    if None in now or now[0] - now[1] <= 0:
                        continue
                    cands.append(((0, -(now[0] - now[1])), lo, sh))
                else:
                    sc = score_pair(hlo, hsh, t, lookback_h, cost_pct, args.max_be_h)
                    if sc:
                        cands.append(((sc["tier"], -sc["sust"], sc["be_h"], -sc["avg_apr"]), lo, sh))
        cands.sort(key=lambda c: c[0])
        for _, lo, sh in cands:
            if len(run.open) >= args.max_positions:
                break
            if lo.symbol in {p.symbol for p in run.open}:
                continue
            entry = leg_cost(lo, size, args.impact) + leg_cost(sh, size, args.impact)
            p = Position(lo.symbol, key(lo), key(sh), size, t, entry, entry)
            run.daily[t // DAY * DAY] -= entry
            run.open.append(p)
    for p in run.open:  # mark-to-market: still open at the end, exit cost charged
        p.closed, p.reason = end, "còn mở cuối kỳ"
        run.daily[(end - HOUR) // DAY * DAY] -= p.exit_cost
        run.done.append(p)
    run.open = []
    return run


# --------------------------------------------------------------------------- report


def summarise(run: Run, start: int, end: int) -> dict:
    days = [run.daily.get(d, 0.0) for d in range(start // DAY * DAY, end // DAY * DAY, DAY)]
    total = sum(days)
    return {
        "strategy": run.name, "size_per_leg": run.size, "days": len(days), "total_usd": round(total, 2),
        "avg_per_day_usd": round(total / max(1, len(days)), 2),
        "median_day_usd": round(statistics.median(days), 2) if days else 0,
        "worst_day_usd": round(min(days), 2) if days else 0, "best_day_usd": round(max(days), 2) if days else 0,
        "losing_days": sum(1 for d in days if d < 0), "trades": len(run.done),
        "fees_usd": round(sum(p.entry_cost + p.exit_cost for p in run.done), 2),
        "funding_usd": round(sum(p.funding for p in run.done), 2),
        "capital_deployed_usd": run.size * 2,  # per position, both legs, before margin
        "daily": [[time.strftime("%Y-%m-%d", time.gmtime(d)), round(v, 2)]
                  for d, v in zip(range(start // DAY * DAY, end // DAY * DAY, DAY), days, strict=False)],
        "positions": [{"symbol": p.symbol, "long": p.long_key, "short": p.short_key,
                       "opened": time.strftime("%m-%d", time.gmtime(p.opened)), "hours": p.hours,
                       "funding": round(p.funding, 2), "costs": round(p.entry_cost + p.exit_cost, 2),
                       "net": round(p.funding - p.entry_cost - p.exit_cost, 2), "exit": p.reason}
                      for p in run.done],
    }


def write_report(results: list[dict], meta: dict, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    (out / "backtest.json").write_text(json.dumps({"meta": meta, "results": results}, indent=1))
    lines = [f"# Backtest delta-neutral ({meta['start']} → {meta['end']}, {meta['days']} ngày)", "",
             f"Cặp xét: {meta['pairs']} · tối đa {meta['max_positions']} vị thế · giữ tối đa {meta['hold_days']} ngày · "
             f"lookback {meta['lookback']} ngày · OI tối thiểu ${meta['min_oi']:,.0f}", "",
             "| Chiến lược | Size/chân | Lãi ròng/ngày | Tổng | Ngày lỗ | Lệnh | Phí+trượt | Funding |",
             "|---|---|---|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['strategy']} | ${r['size_per_leg']:,.0f} | **${r['avg_per_day_usd']:,.2f}** | "
                     f"${r['total_usd']:,.2f} | {r['losing_days']}/{r['days']} | {r['trades']} | "
                     f"${r['fees_usd']:,.2f} | ${r['funding_usd']:,.2f} |")
    lines += ["", "## Lệnh của chiến lược screener (size nhỏ nhất)", "",
              "| Coin | Long | Short | Mở | Giờ | Funding | Phí | Ròng | Đóng vì |", "|---|---|---|---|---|---|---|---|---|"]
    first = next(r for r in results if r["strategy"] == "screener")
    for p in first["positions"]:
        lines.append(f"| {p['symbol']} | {p['long']} | {p['short']} | {p['opened']} | {p['hours']} | "
                     f"{p['funding']} | {p['costs']} | {p['net']} | {p['exit']} |")
    lines += ["", "## Giới hạn", *[f"- {b}" for b in meta["biases"]], "", "## Kiểm tra đơn vị funding", "",
              *[f"- {s}" for s in meta.get("unit_checks", [])]]
    path = out / "backtest_report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def unit_checks(pairs, hist) -> list[str]:
    """Compare each leg's live hourly rate with its latest history point (same units expected)."""
    rows, seen = [], set()
    for p in pairs:
        for m in p:
            if m.venue in seen or m.symbol not in ("BTC", "ETH", "SOL", "NVDA", "TSLA"):
                continue
            h = hist.get(key(m)) or {}
            if not h:
                continue
            last = [h[x] for x in sorted(h)[-6:]]
            rows.append(f"{m.venue} {m.raw}: live {m.rate_h * 100:.5f}%/h vs TB 6 giờ lịch sử "
                        f"{sum(last) / len(last) * 100:.5f}%/h")
            seen.add(m.venue)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=45, help="test window in days")
    ap.add_argument("--lookback", type=int, default=14, help="days of history used for the rules")
    ap.add_argument("--sizes", default="10000,20000")
    ap.add_argument("--max-positions", type=int, default=3)
    ap.add_argument("--hold-days", type=float, default=3)
    ap.add_argument("--max-be-h", type=float, default=48)
    ap.add_argument("--min-oi", type=float, default=50_000)
    ap.add_argument("--impact", type=float, default=0.02, help="extra slippage %% per fill")
    ap.add_argument("--max-pairs", type=int, default=400)
    ap.add_argument("--cache", default="cache/backtest")
    ap.add_argument("--out", default="results")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    pairs = load_universe(args.min_oi)
    pairs.sort(key=lambda p: -min(p[0].oi_usd or 0, p[1].oi_usd or 0))
    pairs = pairs[: args.max_pairs]
    legs = list({key(m): m for p in pairs for m in p}.values())
    log.info("downloading history for %d legs", len(legs))
    hist = load_history(legs, args.days + args.lookback + 1, Path(args.cache))

    end = int(time.time()) // DAY * DAY  # last full UTC day
    start = end - args.days * DAY
    results = []
    for size in [float(s) for s in args.sizes.split(",")]:
        for naive in (False, True):
            results.append(summarise(run_backtest(pairs, hist, start, end, size, args, naive), start, end))
    meta = {
        "start": time.strftime("%Y-%m-%d", time.gmtime(start)), "end": time.strftime("%Y-%m-%d", time.gmtime(end)),
        "days": args.days, "pairs": len(pairs), "max_positions": args.max_positions, "hold_days": args.hold_days,
        "lookback": args.lookback, "min_oi": args.min_oi, "unit_checks": unit_checks(pairs, hist),
        "biases": [
            "OI và bid/ask lấy từ snapshot hôm nay, không phải quá khứ (lạc quan cho các coin mới thanh khoản).",
            "Không mô phỏng chênh giá mark giữa hai sàn (basis) và rủi ro thanh lý một chân.",
            "Funding 8h được chia đều cho từng giờ; tiền thực nhận phụ thuộc thời điểm settle.",
            "Phí taker mặc định bậc thấp nhất công khai; trượt giá = nửa bid/ask + impact cố định mỗi lần khớp.",
            "Variational và Paradex không có API lịch sử nên không có trong backtest.",
        ],
    }
    path = write_report(results, meta, Path(args.out))
    if hasattr(sys.stdout, "reconfigure"):  # Windows consoles default to cp1252
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(path.read_text(encoding="utf-8"))  # noqa: T201 - CLI output


if __name__ == "__main__":
    main()
