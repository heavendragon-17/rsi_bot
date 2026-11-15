"""Offline tests for the funding screener (research/funding_screener).

No network: venue adapters are fed fixture payloads shaped like the live
responses observed on 2026-11-15.
"""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research" / "funding_screener"))

import metrics  # noqa: E402
import venues  # noqa: E402
from venues import DAY, HOUR, Market  # noqa: E402


def _mk(venue, rate_h, mark=100.0, oi=1e6, symbol="BTC"):
    return Market(venue=venue, symbol=symbol, raw=symbol, rate_h=rate_h, mark=mark, oi_usd=oi)


@pytest.mark.parametrize("raw,expected", [
    ("BTC-USD", ("BTC", 1.0)), ("BTC-USD-PERP", ("BTC", 1.0)), ("BTCUSDT", ("BTC", 1.0)),
    ("kPEPE", ("PEPE", 1000.0)), ("1000PEPEUSDT", ("PEPE", 1000.0)), ("xyz:TSLA", ("TSLA", 1.0)),
    ("XAU-PERP", ("GOLD", 1.0)), ("AAPL-USD", ("AAPL", 1.0)), ("TSLAUSD", ("TSLA", 1.0)),
])
def test_normalise(raw, expected):
    assert venues.normalise(raw) == expected


def test_pair_direction_and_signed_spread():
    a, b = _mk("Lighter", -0.0001), _mk("QFEX", 0.0002)
    (long_leg, short_leg), = metrics.build_pairs([a, b])
    assert long_leg.venue == "Lighter" and short_leg.venue == "QFEX"
    st = metrics.pair_stats(long_leg, short_leg, None, None)
    assert st["now_apr"] == pytest.approx(0.0003 * 8760 * 100)


def test_same_sign_rates_are_not_summed():
    # Both negative: the KOL mistake would add |a|+|b|. Correct carry is the difference.
    a, b = _mk("Variational", -0.0019), _mk("Lighter", -0.0015)
    (long_leg, short_leg), = metrics.build_pairs([a, b])
    st = metrics.pair_stats(long_leg, short_leg, None, None)
    assert st["now_apr"] == pytest.approx(0.0004 * 8760 * 100)


def test_price_mismatch_drops_pair():
    assert metrics.build_pairs([_mk("A", 0.0, mark=100), _mk("B", 0.001, mark=150)]) == []


def _hist(rates):
    now = int(time.time()) // HOUR * HOUR
    return {now - i * HOUR: r for i, r in enumerate(rates)}


def test_sustainability_and_drop_rules():
    n = 30 * 24
    long_h = _hist([0.0] * n)
    # 50% of hours positive, average positive -> dropped by sustainability <= 61%
    short_h = _hist([0.0002 if i % 2 else -0.00005 for i in range(n)])
    st = metrics.pair_stats(_mk("A", 0.0), _mk("B", 0.0002), long_h, short_h)
    assert st["sust30"] == pytest.approx(50, abs=0.5)
    assert st["drop"] and "Sustainability" in st["drop_reason"]

    steady = _hist([0.00005] * n)
    st = metrics.pair_stats(_mk("A", 0.0), _mk("B", 0.00005), long_h, steady)
    assert st["sust30"] == 100 and not st["drop"] and st["risk"] == "LOW" and not st["spike"]


def test_negative_30d_average_dropped_and_spike_flag():
    n = 30 * 24
    long_h = _hist([0.0] * n)
    short_h = _hist([-0.0001] * n)
    st = metrics.pair_stats(_mk("A", 0.0), _mk("B", 0.001), long_h, short_h)
    assert st["drop"] and st["drop_reason"] == "TB 30 ngày âm"
    assert st["spike"]  # now 876% vs negative averages


def test_expand_interval_8h():
    out = venues.expand_interval([(8 * HOUR * 1000 * 10, 0.0008)], 8)
    assert len(out) == 8 and all(v == pytest.approx(0.0001) for v in out.values())


def test_lighter_adapter_units(monkeypatch):
    def fake(url, body=None, params=None):
        if url.endswith("orderBookDetails"):
            return {"code": 200, "order_book_details": [
                {"symbol": "BTC", "market_id": 1, "status": "active", "mark_price": "65000",
                 "last_trade_price": 65001, "open_interest": 10, "open_interest_usd": "650000",
                 "daily_quote_token_volume": 1e7, "taker_fee": "0.0000", "maker_fee": "0.0000"}]}
        if url.endswith("funding-rates"):
            return {"code": 200, "funding_rates": [
                {"market_id": 1, "exchange": "binance", "symbol": "BTC", "rate": 0.00003319},
                {"market_id": 1, "exchange": "lighter", "symbol": "BTC", "rate": 0.000064}]}
        if url.endswith("fundings"):
            return {"code": 200, "fundings": [
                {"timestamp": 1792036800, "value": "0.7", "rate": "0.0009", "direction": "long"},
                {"timestamp": 1792040400, "value": "0.9", "rate": "0.0012", "direction": "short"}]}
        raise AssertionError(url)

    monkeypatch.setattr(venues, "http_json", fake)
    (m,) = venues.fetch_lighter()
    assert m.rate_h == pytest.approx(0.000008) and m.oi_usd == 650000
    h = venues.history_lighter(m, 0)
    assert h[1792036800] == pytest.approx(0.000009) and h[1792040400] == pytest.approx(-0.000012)


def test_qfex_adapter(monkeypatch):
    def fake(url, body=None, params=None):
        if url.endswith("/md/contracts"):
            return {"data": [
                {"ticker_id": "AAPL-USD", "target_currency": "USD", "last_price": "357.06", "funding_rate": "0.00001",
                 "next_funding_rate": "0.00002", "funding_interval_minutes": 60, "open_interest_usd": "120000"},
                {"ticker_id": "HYUNDAI-KRW", "target_currency": "KRW", "funding_rate": "0.0001"}]}
        if "/funding/" in url:
            return {"data": [{"symbol": "AAPL-USD", "intervalMinutes": 60, "windowStart": "2026-11-14T00:00:00Z",
                              "rate": -0.00000287}], "count": 1}
        if "/md/orderbook/" in url:
            return {"bids": [["353.66", "1.4"], ["353.65", "2"]], "asks": [["353.74", "0"], ["353.75", "10"]]}
        raise AssertionError(url)

    monkeypatch.setattr(venues, "http_json", fake)
    (m,) = venues.fetch_qfex()
    assert m.symbol == "AAPL" and m.rate_h == pytest.approx(0.00002) and m.rwa
    assert list(venues.history_qfex(m, 0).values()) == [pytest.approx(-0.00000287)]
    venues.enrich_qfex(m)
    assert (m.bid, m.ask) == (353.66, 353.75)


def test_hyperliquid_and_variational(monkeypatch):
    def fake(url, body=None, params=None):
        if url == venues.HL_URL and body["type"] == "perpDexs":
            return [None, {"name": "xyz"}]
        if url == venues.HL_URL and body["type"] == "metaAndAssetCtxs":
            name = "xyz:TSLA" if body.get("dex") else "BTC"
            return [{"universe": [{"name": name}]},
                    [{"markPx": "100", "funding": "0.0000125", "openInterest": "50", "impactPxs": ["99.9", "100.1"],
                      "dayNtlVlm": "1000"}]]
        if url.endswith("/metadata/v2/stats"):
            return {"listings": [{"ticker": "BTC-PERP", "contract_type": "perpetual", "mark_price": "100",
                                  "funding": {"next": {"annualized_rate": "0.0876", "interval_rate": "0.00008"},
                                              "interval_seconds": 28800},
                                  "open_interest": {"long_open_interest": "1000", "short_open_interest": "500"},
                                  "quotes": {"base": {"bid": "99.95", "ask": "100.05"}}}]}
        raise AssertionError(url)

    monkeypatch.setattr(venues, "http_json", fake)
    hl = venues.fetch_hyperliquid()
    assert {m.venue for m in hl} == {"Hyperliquid", "HL:xyz"}
    assert hl[0].oi_usd == 5000 and hl[0].spread_rel == pytest.approx(0.002)
    (v,) = venues.fetch_variational()
    assert v.rate_h == pytest.approx(0.00001) and v.interval_h == 8 and v.oi_usd == 1500


def test_daily_flips():
    series = [(d * DAY + h * HOUR, (1 if d % 2 else -1) * 1e-5) for d in range(6) for h in range(24)]
    assert metrics.daily_flips(series) == 5
