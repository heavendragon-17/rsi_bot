"""Live delta-neutral funding screener (stdlib only).

Run:  python screener.py            -> http://localhost:8787
      PORT=10000 python screener.py  (Render / Railway set PORT for you)

Background threads:
- snapshot loop: every REFRESH_S pulls current funding/OI/bid-ask from all venues;
- history workers (one per venue family): 30d hourly funding for the legs of the
  most promising pairs, refreshed every HISTORY_TTL_S;
- venues without a public history endpoint (Variational, Paradex) are recorded
  locally from the snapshots, so their sustainability fills in over time.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import metrics
from venues import DAY, HOUR, RWA_STATIC, VENUES, Market, hour_floor, spec_for

log = logging.getLogger("screener")

ROOT = Path(__file__).resolve().parent
CACHE_FILE = Path(os.environ.get("SCREENER_CACHE", ROOT / "cache" / "history.json"))
REFRESH_S = int(os.environ.get("REFRESH_S", "60"))
HISTORY_TTL_S = 30 * 60
ENRICH_TTL_S = 5 * 60
MAX_HISTORY_PAIRS = int(os.environ.get("MAX_HISTORY_PAIRS", "220"))
MIN_CANDIDATE_APR = 5.0
MIN_CANDIDATE_OI = 10_000
FOCUS_VENUES = {"QFEX", "Lighter"}
MAX_ROWS = 800
KEEP_S = 31 * DAY


class State:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.markets: dict[tuple[str, str], Market] = {}
        self.status: dict[str, dict] = {}
        self.history: dict[str, dict] = {}  # "venue|raw" -> {"fetched": ts, "data": {hour: rate}, "n": {hour: count}}
        self.enriched: dict[str, float] = {}
        self.queue: list[tuple[str, str]] = []  # legs wanting history, priority order
        self.updated = 0.0
        self._rows_cache: tuple[float, dict] | None = None
        self._load()

    # ---- persistence
    def _load(self) -> None:
        try:
            raw = json.loads(CACHE_FILE.read_text())
            for key, v in raw.items():
                self.history[key] = {"fetched": v.get("fetched", 0), "local": v.get("local", False),
                                     "data": {int(h): r for h, r in v["data"].items()},
                                     "n": {int(h): c for h, c in v.get("n", {}).items()}}
            log.info("loaded history cache: %d legs", len(self.history))
        except FileNotFoundError:
            pass
        except Exception as exc:  # noqa: BLE001
            log.warning("history cache unreadable, starting fresh: %s", exc)

    def save(self) -> None:
        with self.lock:
            blob = json.dumps({k: v for k, v in self.history.items()})
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_FILE.with_suffix(".tmp")
        tmp.write_text(blob)
        tmp.replace(CACHE_FILE)

    # ---- helpers
    @staticmethod
    def key(m: Market) -> str:
        return f"{m.venue}|{m.raw}"

    def hist(self, m: Market) -> dict[int, float] | None:
        h = self.history.get(self.key(m))
        return h["data"] if h and h["data"] else None

    def record_local(self, m: Market) -> None:
        """Running hourly mean of snapshots for venues without a history API."""
        k = self.key(m)
        h = self.history.setdefault(k, {"fetched": 0, "local": True, "data": {}, "n": {}})
        hr = hour_floor(time.time())
        n = h["n"].get(hr, 0)
        h["data"][hr] = (h["data"].get(hr, 0.0) * n + m.rate_h) / (n + 1)
        h["n"][hr] = n + 1
        if len(h["n"]) > 48:
            h["n"] = {x: c for x, c in h["n"].items() if x >= hr - 2 * HOUR}


STATE = State()


# --------------------------------------------------------------------------- snapshot loop


def refresh_once() -> None:
    results: dict[str, list[Market] | Exception] = {}

    def run(spec):
        t0 = time.time()
        try:
            results[spec.name] = spec.fetch()
        except Exception as exc:  # noqa: BLE001
            results[spec.name] = exc
        log.info("%s fetched in %.1fs", spec.name, time.time() - t0)

    with ThreadPoolExecutor(max_workers=len(VENUES)) as pool:
        list(pool.map(run, VENUES))

    now = time.time()
    with STATE.lock:
        for spec in VENUES:
            res = results.get(spec.name)
            if isinstance(res, Exception) or res is None:
                prev = STATE.status.get(spec.name, {})
                STATE.status[spec.name] = {**prev, "ok": False, "error": str(res)[:300], "checked": now}
                continue
            # drop old markets of this family, keep enrichment from the previous snapshot
            fam = [k for k in STATE.markets if spec_for(k[0]).name == spec.name]
            old = {k: STATE.markets.pop(k) for k in fam}
            for m in res:
                prev_m = old.get((m.venue, m.raw))
                if prev_m and spec.enrich:
                    m.bid = m.bid if m.bid is not None else prev_m.bid
                    m.ask = m.ask if m.ask is not None else prev_m.ask
                    m.oi_usd = m.oi_usd if m.oi_usd is not None else prev_m.oi_usd
                STATE.markets[(m.venue, m.raw)] = m
                if spec.history is None:
                    STATE.record_local(m)
            STATE.status[spec.name] = {"ok": True, "count": len(res), "error": None, "checked": now,
                                       "history": "api" if spec.history else "ghi local"}
        STATE.updated = now
        STATE._rows_cache = None
        _mark_rwa()
        STATE.queue = _candidates()


def _mark_rwa() -> None:
    qfex_syms = {m.symbol for m in STATE.markets.values() if m.venue == "QFEX"}
    rwa = qfex_syms | RWA_STATIC
    for m in STATE.markets.values():
        if m.symbol in rwa:
            m.rwa = True


def _candidates() -> list[tuple[str, str]]:
    pairs = metrics.build_pairs(STATE.markets.values())

    def ok(p):
        a, b = p
        oi_ok = all(x.oi_usd is None or x.oi_usd >= MIN_CANDIDATE_OI for x in p)
        return oi_ok and metrics.apr(b.rate_h - a.rate_h) >= MIN_CANDIDATE_APR

    good = sorted(filter(ok, pairs), key=lambda p: p[1].rate_h - p[0].rate_h, reverse=True)
    focus = [p for p in good if p[0].venue in FOCUS_VENUES or p[1].venue in FOCUS_VENUES]
    chosen = focus[: MAX_HISTORY_PAIRS // 2] + good[:MAX_HISTORY_PAIRS]
    legs: list[tuple[str, str]] = []
    seen = set()
    for a, b in chosen:
        for m in (a, b):
            k = (m.venue, m.raw)
            if k not in seen:
                seen.add(k)
                legs.append(k)
    return legs


def snapshot_loop() -> None:
    last_save = time.time()
    while True:
        t0 = time.time()
        try:
            refresh_once()
        except Exception:  # noqa: BLE001
            log.exception("refresh failed")
        if time.time() - last_save > 300:
            try:
                STATE.save()
            except Exception as exc:  # noqa: BLE001
                log.warning("save failed: %s", exc)
            last_save = time.time()
        time.sleep(max(5.0, REFRESH_S - (time.time() - t0)))


# --------------------------------------------------------------------------- history / enrich workers


def history_worker(family: str) -> None:
    spec = next(v for v in VENUES if v.name == family)
    while True:
        did = False
        with STATE.lock:
            legs = [k for k in STATE.queue if spec_for(k[0]).name == family]
        for vk in legs:
            with STATE.lock:
                m = STATE.markets.get(vk)
            if m is None:
                continue
            now = time.time()
            if spec.enrich and now - STATE.enriched.get(STATE.key(m), 0) > ENRICH_TTL_S:
                try:
                    spec.enrich(m)
                except Exception as exc:  # noqa: BLE001
                    log.debug("enrich %s failed: %s", vk, exc)
                STATE.enriched[STATE.key(m)] = now
                did = True
                time.sleep(spec.min_gap_s)
            if spec.history is None:
                continue
            h = STATE.history.get(STATE.key(m))
            if h and now - h["fetched"] < HISTORY_TTL_S:
                continue
            since = int(now - 30 * DAY)
            if h and h["data"]:
                since = max(since, max(h["data"]) - 3 * HOUR)
            try:
                data = spec.history(m, since)
                with STATE.lock:
                    h = STATE.history.setdefault(STATE.key(m), {"fetched": 0, "local": False, "data": {}, "n": {}})
                    h["data"].update(data)
                    cutoff = now - KEEP_S
                    h["data"] = {x: r for x, r in h["data"].items() if x >= cutoff}
                    h["fetched"] = now
                    STATE._rows_cache = None
            except Exception as exc:  # noqa: BLE001
                log.info("history %s failed: %s", vk, exc)
                with STATE.lock:
                    STATE.history.setdefault(STATE.key(m), {"fetched": 0, "local": False, "data": {}, "n": {}})
                    STATE.history[STATE.key(m)]["fetched"] = now - HISTORY_TTL_S + 300  # retry in 5 min
            did = True
            time.sleep(spec.min_gap_s)
        if not did:
            time.sleep(10)


# --------------------------------------------------------------------------- API payloads


def pair_id(a: Market, b: Market) -> str:
    return "~".join([a.symbol, a.venue, a.raw, b.venue, b.raw])


def build_rows() -> dict:
    with STATE.lock:
        cached = STATE._rows_cache
        if cached and time.time() - cached[0] < 15:
            return cached[1]
        pairs = metrics.build_pairs(STATE.markets.values())
        rows = []
        for a, b in pairs:
            st = metrics.pair_stats(a, b, STATE.hist(a), STATE.hist(b))
            if st["now_apr"] <= 0 and st["hist_hours"] == 0:
                continue
            ois = [x.oi_usd for x in (a, b) if x.oi_usd is not None]
            rows.append({
                "id": pair_id(a, b), "symbol": a.symbol, "rwa": a.rwa or b.rwa,
                "long": metrics.leg_view(a), "short": metrics.leg_view(b),
                "min_oi": min(ois) if ois else None, **st,
            })
        rows.sort(key=lambda r: (r["hist_hours"] > 0, r["now_apr"]), reverse=True)
        payload = {
            "updated": STATE.updated, "server_time": time.time(), "status": STATE.status,
            "venues": sorted({m.venue for m in STATE.markets.values()}),
            "history_queue": len(STATE.queue), "rows": rows[:MAX_ROWS],
        }
        STATE._rows_cache = (time.time(), payload)
        return payload


def pair_detail(pid: str) -> dict | None:
    parts = pid.split("~")
    if len(parts) != 5:
        return None
    _, va, ra, vb, rb = parts
    with STATE.lock:
        a, b = STATE.markets.get((va, ra)), STATE.markets.get((vb, rb))
        if not a or not b:
            return None
        ha, hb = STATE.hist(a) or {}, STATE.hist(b) or {}
        since = time.time() - 30 * DAY
        return {
            "id": pid, "spread": metrics.chart_series(ha, hb),
            "long_hist": [[h, round(metrics.apr(r), 3)] for h, r in sorted(ha.items()) if h >= since],
            "short_hist": [[h, round(metrics.apr(r), 3)] for h, r in sorted(hb.items()) if h >= since],
            "long_local": STATE.history.get(STATE.key(a), {}).get("local", False),
            "short_local": STATE.history.get(STATE.key(b), {}).get("local", False),
        }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quiet access log
        log.debug(fmt, *args)

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        url = urllib.parse.urlparse(self.path)
        if url.path in ("/", "/index.html"):
            return self._send(200, (ROOT / "static" / "index.html").read_bytes(), "text/html; charset=utf-8")
        if url.path == "/api/opps":
            return self._send(200, json.dumps(build_rows()).encode(), "application/json")
        if url.path == "/api/pair":
            pid = urllib.parse.parse_qs(url.query).get("id", [""])[0]
            detail = pair_detail(pid)
            if detail is None:
                return self._send(404, b'{"error":"pair not found"}', "application/json")
            return self._send(200, json.dumps(detail).encode(), "application/json")
        if url.path == "/healthz":
            return self._send(200, b"ok", "text/plain")
        return self._send(404, b"not found", "text/plain")


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    threading.Thread(target=snapshot_loop, daemon=True, name="snapshot").start()
    for spec in VENUES:
        threading.Thread(target=history_worker, args=(spec.name,), daemon=True, name=f"hist-{spec.name}").start()
    port = int(os.environ.get("PORT", "8787"))
    host = os.environ.get("HOST", "0.0.0.0")
    log.info("serving on http://%s:%d", "localhost" if host == "0.0.0.0" else host, port)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
