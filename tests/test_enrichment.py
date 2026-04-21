"""Unit tests for enrich_round_trips — single-source-of-truth enrichment."""

import pandas as pd

from app.backtest.enrichment import enrich_round_trips


class TestEnrichRoundTrips:
    def test_empty_round_trips(self):
        results = {"round_trips": []}
        debug = [{"symbol": "BTC", "signal": "BUY", "rsi_ema9": 30}]
        out = enrich_round_trips(results, debug)
        assert out == results

    def test_no_matching_debug(self):
        results = {"round_trips": [{"symbol": "BTC", "entry_time": "2024-01-01"}]}
        out = enrich_round_trips(results, [])
        assert out == results

    def test_enriches_fields_on_match(self):
        entry_ts = pd.Timestamp("2024-01-01 12:00:00")
        results = {
            "round_trips": [
                {"symbol": "BTC", "entry_time": entry_ts},
            ]
        }
        debug = [
            {
                "symbol": "BTC",
                "timestamp": str(entry_ts),
                "signal": "BUY",
                "rsi_ema9": 30.12345,
                "rsi_wma45": 40.98765,
                "spread": 1.5,
                "above_count": 3,
            }
        ]
        out = enrich_round_trips(results, debug)
        enriched = out["round_trips"][0]
        assert enriched["entry_rsi_ema9"] == round(30.12345, 4)
        assert enriched["entry_rsi_wma45"] == round(40.98765, 4)
        assert enriched["entry_spread"] == 1.5
        assert enriched["above_count"] == 3

    def test_no_match_fields_are_none(self):
        results = {
            "round_trips": [
                {"symbol": "ETH", "entry_time": "2024-01-01"},
            ]
        }
        debug = [
            {
                "symbol": "BTC",
                "timestamp": "2024-01-01",
                "signal": "BUY",
                "rsi_ema9": 1,
                "rsi_wma45": 2,
                "spread": 3,
                "above_count": 4,
            }
        ]
        out = enrich_round_trips(results, debug)
        enriched = out["round_trips"][0]
        assert enriched["entry_rsi_ema9"] is None
        assert enriched["entry_rsi_wma45"] is None
        assert enriched["entry_spread"] is None
        assert enriched["above_count"] is None

    def test_only_buy_signals_considered(self):
        entry_ts = pd.Timestamp("2024-01-01")
        results = {"round_trips": [{"symbol": "BTC", "entry_time": entry_ts}]}
        debug = [
            {
                "symbol": "BTC",
                "timestamp": str(entry_ts),
                "signal": "SELL",  # not BUY
                "rsi_ema9": 99,
            }
        ]
        out = enrich_round_trips(results, debug)
        # SELL isn't in the lookup, results should be unchanged
        assert out == results
