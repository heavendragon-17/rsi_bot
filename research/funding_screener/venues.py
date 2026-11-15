"""Public funding-rate adapters for perp DEXs (no API keys, stdlib only).

Every adapter returns a list of :class:`Market` with the CURRENT funding rate
normalised to an hourly decimal fraction (``rate_h``), signed so that a
positive value means longs pay shorts. History fetchers return
``{hour_ts: rate_h}`` with ``hour_ts`` = unix seconds floored to the hour.

Units verified against public docs / live responses (2026-11-15):
- Hyperliquid  ``funding`` hourly fraction; history ``fundingHistory`` hourly.
- Lighter      ``/funding-rates`` lighter rows look 8h-normalised fractions
               (BTC 0.000064 vs history 0.0009 %/h); ``/fundings`` ``rate`` is
               a PERCENT per hour with ``direction`` long(+)/short(-).
               This is an inference, see README "assumptions".
- QFEX         ``funding_rate`` decimal per ``funding_interval_minutes`` (60).
- Extended     ``fundingRate`` hourly fraction.
- Variational  ``funding.*.annualized_rate`` decimal (no history endpoint).
- Aster        Binance-style ``lastFundingRate`` per ``fundingIntervalHours``.
- Paradex      ``funding_rate`` per ``funding_interval_minutes`` (no history).
"""

from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger("screener.venues")

HOUR = 3600
DAY = 24 * HOUR
HISTORY_DAYS = 30
TIMEOUT_S = 20
USER_AGENT = "Mozilla/5.0 (compatible; funding-screener/1.0)"

HL_URL = "https://api.hyperliquid.xyz/info"
LIGHTER_URL = "https://mainnet.zklighter.elliot.ai/api/v1"
QFEX_URL = "https://api.qfex.com"
EXTENDED_URL = "https://api.starknet.extended.exchange/api/v1"
VARIATIONAL_URL = "https://omni-client-api.prod.ap-northeast-1.variational.io"
ASTER_URL = "https://fapi.asterdex.com"
PARADEX_URL = "https://api.prod.paradex.trade/v1"

# Same underlying, different ticker on different venues.
ALIASES = {"XAU": "GOLD", "XAG": "SILVER", "WTI": "CL", "USOIL": "CL", "BRENTOIL": "BRENT"}
# Commodities / indices that are RWA even when listed on a crypto-first venue.
RWA_STATIC = {
    "GOLD", "SILVER", "CL", "BRENT", "NATGAS", "COPPER", "PLATINUM", "XPT", "PALLADIUM",
    "SPX", "SPY", "QQQ", "US100", "US500", "NDX", "NIKKEI", "KOSPI", "HSI", "DXY", "EUR", "JPY",
    "TSLA", "NVDA", "AAPL", "MSFT", "META", "AMZN", "GOOGL", "COIN", "MSTR", "HOOD", "PLTR",
}


@dataclass
class Market:
    venue: str
    symbol: str  # normalised base asset, e.g. "BTC"
    raw: str  # venue-native id used for history calls
    rate_h: float  # current funding, hourly fraction, + = longs pay
    interval_h: float = 1.0
    mark: float | None = None
    bid: float | None = None
    ask: float | None = None
    oi_usd: float | None = None
    vol_usd: float | None = None
    scale: float = 1.0  # 1000 for kPEPE / 1000PEPE style contracts
    rwa: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def unit_price(self) -> float | None:
        return self.mark / self.scale if self.mark else None

    @property
    def spread_rel(self) -> float | None:
        if self.bid and self.ask and self.ask >= self.bid > 0:
            return (self.ask - self.bid) / ((self.ask + self.bid) / 2)
        return None


# --------------------------------------------------------------------------- helpers


def http_json(url: str, body: dict | None = None, params: dict | None = None) -> Any:
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if data is not None:
        headers["Content-Type"] = "application/json"
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:  # 4xx is not worth retrying except 429
            last_err = exc
            if exc.code != 429 and exc.code < 500:
                break
        except Exception as exc:  # noqa: BLE001 - network errors of any kind
            last_err = exc
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET {url[:120]} failed: {last_err}")


def fnum(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def hour_floor(ts: float) -> int:
    if ts > 1e12:  # milliseconds
        ts /= 1000
    return int(ts // HOUR * HOUR)


def normalise(raw: str) -> tuple[str, float]:
    """Map a venue ticker to (base asset, price scale)."""
    s = raw.split(":")[-1]
    for suffix in ("-USD-PERP", "-PERP", "-SWAP", "-USDC", "-USDT", "-USD", "USDT", "USDC", "USD"):
        if s.upper().endswith(suffix) and len(s) > len(suffix):
            s = s[: -len(suffix)]
            break
    scale = 1.0
    if s.startswith("k") and len(s) > 1 and s[1:].isupper():
        s, scale = s[1:], 1000.0
    up = s.upper()
    for prefix, mult in (("1000000", 1e6), ("1000", 1e3), ("1M", 1e6)):
        if up.startswith(prefix) and len(up) > len(prefix) and up[len(prefix)].isalpha():
            up, scale = up[len(prefix):], mult
            break
    return ALIASES.get(up, up), scale


def expand_interval(points: list[tuple[float, float]], interval_h: float) -> dict[int, float]:
    """Turn per-settlement rates [(settle_ts, rate_per_interval)] into hourly rates."""
    out: dict[int, float] = {}
    n = max(1, int(round(interval_h)))
    for ts, rate in points:
        end = hour_floor(ts)
        for k in range(n):
            out[end - k * HOUR] = rate / n
    return out


def window(days: int = HISTORY_DAYS) -> tuple[int, int]:
    end = int(time.time())
    return end - days * DAY, end


# --------------------------------------------------------------------------- Hyperliquid (+ HIP-3)


def fetch_hyperliquid() -> list[Market]:
    out: list[Market] = []
    dex_names = [""]
    try:
        dexs = http_json(HL_URL, body={"type": "perpDexs"})
        dex_names += [d["name"] for d in dexs if isinstance(d, dict) and d.get("name")]
    except Exception as exc:  # noqa: BLE001
        log.warning("hyperliquid perpDexs failed: %s", exc)
    for dex in dex_names:
        body: dict[str, Any] = {"type": "metaAndAssetCtxs"}
        if dex:
            body["dex"] = dex
        try:
            meta, ctxs = http_json(HL_URL, body=body)
        except Exception as exc:  # noqa: BLE001
            log.warning("hyperliquid dex %r failed: %s", dex, exc)
            continue
        venue = "Hyperliquid" if not dex else f"HL:{dex}"
        for u, c in zip(meta.get("universe", []), ctxs, strict=False):
            if u.get("isDelisted"):
                continue
            mark = fnum(c.get("markPx"))
            rate = fnum(c.get("funding"))
            if mark is None or rate is None:
                continue
            sym, scale = normalise(u["name"])
            imp = c.get("impactPxs") or [None, None]
            oi = fnum(c.get("openInterest"))
            out.append(Market(
                venue=venue, symbol=sym, raw=u["name"], rate_h=rate, mark=mark,
                bid=fnum(imp[0]), ask=fnum(imp[1]) if len(imp) > 1 else None,
                oi_usd=oi * mark if oi is not None else None, vol_usd=fnum(c.get("dayNtlVlm")),
                scale=scale, rwa=bool(dex) and sym not in _CRYPTO_HINT,
            ))
    return out


def history_hyperliquid(m: Market, since: int) -> dict[int, float]:
    out: dict[int, float] = {}
    start_ms = since * 1000
    for _ in range(4):  # 500 rows per page, 30d = 720 rows
        rows = http_json(HL_URL, body={"type": "fundingHistory", "coin": m.raw, "startTime": start_ms})
        if not rows:
            break
        for r in rows:
            out[hour_floor(r["time"])] = float(r["fundingRate"])
        last = rows[-1]["time"]
        if len(rows) < 500 or last <= start_ms:
            break
        start_ms = last + 1
    return out


# --------------------------------------------------------------------------- Lighter


def fetch_lighter() -> list[Market]:
    details = http_json(f"{LIGHTER_URL}/orderBookDetails", params={"filter": "perp"})
    rates: dict[int, float] = {}
    try:
        for r in http_json(f"{LIGHTER_URL}/funding-rates").get("funding_rates", []):
            if r.get("exchange") == "lighter":
                rates[int(r["market_id"])] = float(r["rate"]) / 8.0  # 8h-normalised -> hourly
    except Exception as exc:  # noqa: BLE001
        log.warning("lighter funding-rates failed: %s", exc)
    out: list[Market] = []
    for d in details.get("order_book_details", []):
        if d.get("status") not in (None, "active"):
            continue
        mid = int(d["market_id"])
        if mid not in rates:
            continue
        mark = fnum(d.get("mark_price")) or fnum(d.get("last_trade_price"))
        oi_usd = fnum(d.get("open_interest_usd"))
        if oi_usd is None and fnum(d.get("open_interest")) is not None and mark:
            oi_usd = float(d["open_interest"]) * mark
        sym, scale = normalise(d["symbol"])
        out.append(Market(
            venue="Lighter", symbol=sym, raw=d["symbol"], rate_h=rates[mid], mark=mark,
            oi_usd=oi_usd, vol_usd=fnum(d.get("daily_quote_token_volume")), scale=scale,
            extra={"market_id": mid, "taker_pct": fnum(d.get("taker_fee")), "maker_pct": fnum(d.get("maker_fee"))},
        ))
    return out


def history_lighter(m: Market, since: int) -> dict[int, float]:
    params = {"market_id": m.extra["market_id"], "resolution": "1h", "start_timestamp": since,
              "end_timestamp": int(time.time()), "count_back": 0}
    data = http_json(f"{LIGHTER_URL}/fundings", params=params)
    out: dict[int, float] = {}
    for r in data.get("fundings", []):
        rate = fnum(r.get("rate"))
        if rate is None:
            continue
        sign = -1.0 if r.get("direction") == "short" else 1.0
        out[hour_floor(r["timestamp"])] = sign * rate / 100.0  # percent -> fraction
    return out


def enrich_lighter(m: Market) -> None:
    data = http_json(f"{LIGHTER_URL}/orderBookOrders", params={"market_id": m.extra["market_id"], "limit": 1})
    bids, asks = data.get("bids") or [], data.get("asks") or []
    if bids and asks:
        m.bid, m.ask = fnum(bids[0].get("price")), fnum(asks[0].get("price"))


# --------------------------------------------------------------------------- QFEX


def fetch_qfex() -> list[Market]:
    data = http_json(f"{QFEX_URL}/md/contracts").get("data", [])
    out: list[Market] = []
    for c in data:
        if (c.get("target_currency") or "USD").upper() not in ("USD", "USDC", "USDT"):
            continue
        rate = fnum(c.get("next_funding_rate"))
        if rate is None:
            rate = fnum(c.get("funding_rate"))
        if rate is None:
            continue
        interval_h = (fnum(c.get("funding_interval_minutes")) or 60) / 60
        sym, scale = normalise(c["ticker_id"])
        out.append(Market(
            venue="QFEX", symbol=sym, raw=c["ticker_id"], rate_h=rate / interval_h, interval_h=interval_h,
            mark=fnum(c.get("last_price")) or fnum(c.get("index_price")),
            oi_usd=fnum(c.get("open_interest_usd")), vol_usd=fnum(c.get("target_volume")),
            scale=scale, rwa=True,
        ))
    return out


def history_qfex(m: Market, since: int) -> dict[int, float]:
    iso = lambda t: datetime.fromtimestamp(t, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
    params = {"intervalMinutes": 60, "fromISO": iso(since), "toISO": iso(time.time())}
    data = http_json(f"{QFEX_URL}/funding/{urllib.parse.quote(m.raw, safe='')}", params=params)
    out: dict[int, float] = {}
    for r in data.get("data", []):
        rate = fnum(r.get("rate"))
        if rate is None:
            continue
        ts = datetime.strptime(r["windowStart"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)
        out[hour_floor(ts.timestamp())] = rate * 60 / (fnum(r.get("intervalMinutes")) or 60)
    return out


def enrich_qfex(m: Market) -> None:
    data = http_json(f"{QFEX_URL}/md/orderbook/{urllib.parse.quote(m.raw, safe='')}")
    bids = [b for b in data.get("bids", []) if fnum(b[1])]
    asks = [a for a in data.get("asks", []) if fnum(a[1])]
    if bids and asks:
        m.bid = max(float(b[0]) for b in bids)
        m.ask = min(float(a[0]) for a in asks)


# --------------------------------------------------------------------------- Extended


def fetch_extended() -> list[Market]:
    out: list[Market] = []
    for d in http_json(f"{EXTENDED_URL}/info/markets").get("data", []):
        if d.get("status") not in (None, "ACTIVE") or d.get("type", "PERPETUAL") != "PERPETUAL":
            continue
        st = d.get("marketStats") or {}
        rate = fnum(st.get("fundingRate"))
        if rate is None:
            continue
        sym, scale = normalise(d["name"])
        out.append(Market(
            venue="Extended", symbol=sym, raw=d["name"], rate_h=rate,
            mark=fnum(st.get("markPrice")), bid=fnum(st.get("bidPrice")), ask=fnum(st.get("askPrice")),
            oi_usd=fnum(st.get("openInterest")), vol_usd=fnum(st.get("dailyVolume")), scale=scale,
            rwa=d.get("category", "").upper() in ("TRADFI", "RWA", "EQUITY", "COMMODITY"),
        ))
    return out


def history_extended(m: Market, since: int) -> dict[int, float]:
    out: dict[int, float] = {}
    params: dict[str, Any] = {"startTime": since * 1000, "endTime": int(time.time()) * 1000, "limit": 1000}
    for _ in range(5):
        data = http_json(f"{EXTENDED_URL}/info/{urllib.parse.quote(m.raw, safe='')}/funding", params=params)
        for r in data.get("data", []):
            rate = fnum(r.get("f"))
            if rate is not None:
                out[hour_floor(r["T"])] = rate
        cursor = (data.get("pagination") or {}).get("cursor")
        if not cursor or len(data.get("data", [])) < params["limit"]:
            break
        params["cursor"] = cursor
    return out


# --------------------------------------------------------------------------- Variational (no history API)


def fetch_variational() -> list[Market]:
    out: list[Market] = []
    for x in http_json(f"{VARIATIONAL_URL}/metadata/v2/stats").get("listings", []):
        if x.get("contract_type", "perpetual") != "perpetual":
            continue
        fund = x.get("funding") or {}
        cur = fund.get("next") or fund.get("last") or {}
        ann = fnum(cur.get("annualized_rate"))
        if ann is None:
            continue
        secs = fnum(cur.get("interval_seconds")) or fnum(fund.get("interval_seconds")) or 8 * HOUR
        oi = x.get("open_interest") or {}
        oi_usd = None
        if isinstance(oi, dict):
            long_oi, short_oi = fnum(oi.get("long_open_interest")), fnum(oi.get("short_open_interest"))
            if long_oi is not None or short_oi is not None:
                oi_usd = (long_oi or 0) + (short_oi or 0)
        q = (x.get("quotes") or {})
        base = q.get("size_100k") or q.get("base") or {}
        sym, scale = normalise(x["ticker"])
        out.append(Market(
            venue="Variational", symbol=sym, raw=x["ticker"], rate_h=ann / 8760, interval_h=secs / HOUR,
            mark=fnum(x.get("mark_price")), bid=fnum(base.get("bid")), ask=fnum(base.get("ask")),
            oi_usd=oi_usd, vol_usd=fnum(x.get("volume_24h")), scale=scale,
        ))
    return out


# --------------------------------------------------------------------------- Aster


def fetch_aster() -> list[Market]:
    prem = http_json(f"{ASTER_URL}/fapi/v1/premiumIndex")
    intervals: dict[str, float] = {}
    try:
        for r in http_json(f"{ASTER_URL}/fapi/v1/fundingInfo"):
            intervals[r["symbol"]] = float(r.get("fundingIntervalHours") or 8)
    except Exception as exc:  # noqa: BLE001
        log.warning("aster fundingInfo failed: %s", exc)
    books: dict[str, dict] = {}
    vols: dict[str, float] = {}
    try:
        books = {b["symbol"]: b for b in http_json(f"{ASTER_URL}/fapi/v1/ticker/bookTicker")}
        vols = {t["symbol"]: float(t.get("quoteVolume") or 0) for t in http_json(f"{ASTER_URL}/fapi/v1/ticker/24hr")}
    except Exception as exc:  # noqa: BLE001
        log.warning("aster tickers failed: %s", exc)
    out: list[Market] = []
    for p in prem:
        s = p["symbol"]
        if not (s.endswith("USDT") or s.endswith("USD")):
            continue
        rate = fnum(p.get("lastFundingRate"))
        if rate is None:
            continue
        ih = intervals.get(s, 8.0)
        sym, scale = normalise(s)
        b = books.get(s, {})
        out.append(Market(
            venue="Aster", symbol=sym, raw=s, rate_h=rate / ih, interval_h=ih, mark=fnum(p.get("markPrice")),
            bid=fnum(b.get("bidPrice")), ask=fnum(b.get("askPrice")), vol_usd=vols.get(s), scale=scale,
            rwa=s.endswith("USD") and not s.endswith("USDT"),
        ))
    return out


def history_aster(m: Market, since: int) -> dict[int, float]:
    rows = http_json(f"{ASTER_URL}/fapi/v1/fundingRate",
                     params={"symbol": m.raw, "startTime": since * 1000, "limit": 1000})
    return expand_interval([(r["fundingTime"], float(r["fundingRate"])) for r in rows], m.interval_h)


def enrich_aster(m: Market) -> None:
    r = http_json(f"{ASTER_URL}/fapi/v1/openInterest", params={"symbol": m.raw})
    oi = fnum(r.get("openInterest"))
    if oi is not None and m.mark:
        m.oi_usd = oi * m.mark


# --------------------------------------------------------------------------- Paradex (no history API used)


def fetch_paradex() -> list[Market]:
    out: list[Market] = []
    for x in http_json(f"{PARADEX_URL}/markets/summary", params={"market": "ALL"}).get("results", []):
        s = x.get("symbol", "")
        rate = fnum(x.get("funding_rate"))
        if not s.endswith("-PERP") or rate is None:
            continue
        ih = (fnum(x.get("funding_interval_minutes")) or 480) / 60
        mark = fnum(x.get("mark_price"))
        oi = fnum(x.get("open_interest"))
        sym, scale = normalise(s)
        out.append(Market(
            venue="Paradex", symbol=sym, raw=s, rate_h=rate / ih, interval_h=ih, mark=mark,
            bid=fnum(x.get("bid")), ask=fnum(x.get("ask")),
            oi_usd=oi * mark if oi is not None and mark else None, vol_usd=fnum(x.get("volume_24h")), scale=scale,
        ))
    return out


_CRYPTO_HINT = {"BTC", "ETH", "SOL", "HYPE", "XRP", "DOGE", "BNB"}


@dataclass(frozen=True)
class VenueSpec:
    name: str
    fetch: Callable[[], list[Market]]
    history: Callable[[Market, int], dict[int, float]] | None
    enrich: Callable[[Market], None] | None
    min_gap_s: float  # throttle between history/enrich calls


VENUES: list[VenueSpec] = [
    VenueSpec("Hyperliquid", fetch_hyperliquid, history_hyperliquid, None, 1.0),
    VenueSpec("Lighter", fetch_lighter, history_lighter, enrich_lighter, 0.8),
    VenueSpec("QFEX", fetch_qfex, history_qfex, enrich_qfex, 0.5),
    VenueSpec("Extended", fetch_extended, history_extended, None, 0.5),
    VenueSpec("Variational", fetch_variational, None, None, 1.0),
    VenueSpec("Aster", fetch_aster, history_aster, enrich_aster, 0.3),
    VenueSpec("Paradex", fetch_paradex, None, None, 0.5),
]


def spec_for(venue: str) -> VenueSpec:
    family = "Hyperliquid" if venue.startswith("HL:") else venue
    return next(v for v in VENUES if v.name == family)
