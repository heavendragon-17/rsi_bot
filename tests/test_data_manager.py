"""Tests for DataManager - file management + download trigger."""

import os
from unittest.mock import MagicMock, patch

import pandas as pd

from app.backtest.data.manager import DataManager


def _write_csv(path, rows):
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)


class TestPathHelpers:
    def test_get_csv_path(self, tmp_path):
        mgr = DataManager(data_dir=str(tmp_path), timeframe="5m")
        assert mgr.get_csv_path("BTC/USDT").endswith("BTCUSDT_5m.csv")


class TestNeedsDownload:
    def test_missing_file(self, tmp_path):
        mgr = DataManager(data_dir=str(tmp_path), timeframe="5m")
        assert mgr.needs_download("BTC/USDT", 100) is True

    def test_too_short(self, tmp_path):
        mgr = DataManager(data_dir=str(tmp_path), timeframe="5m")
        path = mgr.get_csv_path("BTC/USDT")
        rows = [{"timestamp": pd.Timestamp.utcnow() + pd.Timedelta(hours=7), "close": 1}] * 5
        _write_csv(path, rows)
        assert mgr.needs_download("BTC/USDT", 100) is True

    def test_fresh_and_long_enough(self, tmp_path):
        mgr = DataManager(data_dir=str(tmp_path), timeframe="5m")
        path = mgr.get_csv_path("BTC/USDT")
        now = pd.Timestamp.utcnow().tz_localize(None) + pd.Timedelta(hours=7)
        # Oldest first, most-recent LAST (matches _is_stale_or_short which checks last_line)
        rows = [{"timestamp": now - pd.Timedelta(minutes=(99 - i) * 5), "close": 1.0} for i in range(100)]
        _write_csv(path, rows)
        assert mgr.needs_download("BTC/USDT", 90) is False

    def test_stale_last_timestamp(self, tmp_path):
        mgr = DataManager(data_dir=str(tmp_path), timeframe="5m")
        path = mgr.get_csv_path("BTC/USDT")
        # All rows stamped with old time
        rows = [{"timestamp": "2020-01-01 00:00:00", "close": 1.0} for _ in range(100)]
        _write_csv(path, rows)
        assert mgr.needs_download("BTC/USDT", 50) is True


class TestEnsureData:
    def test_no_download_when_fresh(self, tmp_path, monkeypatch):
        mgr = DataManager(data_dir=str(tmp_path), timeframe="5m")
        path = mgr.get_csv_path("BTC/USDT")
        now = pd.Timestamp.utcnow().tz_localize(None) + pd.Timedelta(hours=7)
        rows = [{"timestamp": now - pd.Timedelta(minutes=(99 - i) * 5), "close": 1.0} for i in range(100)]
        _write_csv(path, rows)
        dl = MagicMock()
        monkeypatch.setattr("app.backtest.data.manager.download_data", dl)
        result = mgr.ensure_data("BTC/USDT", 50)
        assert result == path
        dl.assert_not_called()

    def test_triggers_download_when_missing(self, tmp_path, monkeypatch):
        mgr = DataManager(data_dir=str(tmp_path), timeframe="5m")

        def fake_dl(safe, tf, limit, data_dir, **kwargs):
            now = pd.Timestamp.utcnow().tz_localize(None) + pd.Timedelta(hours=7)
            rows = [{"timestamp": now, "close": 1.0} for _ in range(100)]
            _write_csv(mgr.get_csv_path("BTC/USDT"), rows)

        monkeypatch.setattr("app.backtest.data.manager.download_data", fake_dl)
        path = mgr.ensure_data("BTC/USDT", 50)
        assert os.path.exists(path)

    def test_download_failed_raises(self, tmp_path, monkeypatch):
        import pytest

        mgr = DataManager(data_dir=str(tmp_path), timeframe="5m")

        def fake_dl(*args, **kwargs):
            pass  # don't write file

        monkeypatch.setattr("app.backtest.data.manager.download_data", fake_dl)
        with pytest.raises(FileNotFoundError):
            mgr.ensure_data("BTC/USDT", 50)


class TestEnsureBulkData:
    def test_returns_mapping(self, tmp_path, monkeypatch):
        mgr = DataManager(data_dir=str(tmp_path), timeframe="5m")

        def fake_dl(safe, tf, limit, data_dir, **kwargs):
            now = pd.Timestamp.utcnow().tz_localize(None) + pd.Timedelta(hours=7)
            rows = [{"timestamp": now, "close": 1.0} for _ in range(100)]
            path = os.path.join(data_dir, f"{safe}_{tf}.csv")
            _write_csv(path, rows)

        # Provide a shared_exchange stub
        mgr._shared_exchange = MagicMock()
        monkeypatch.setattr("app.backtest.data.manager.download_data", fake_dl)
        result = mgr.ensure_bulk_data(["BTC/USDT", "ETH/USDT"], 50)
        assert "BTC/USDT" in result
        assert "ETH/USDT" in result


class TestSharedExchange:
    def test_lazy_created_once(self, tmp_path):
        mgr = DataManager(data_dir=str(tmp_path), timeframe="5m")
        with patch("ccxt.binanceusdm") as MockCcxt:
            exchange = MagicMock()
            MockCcxt.return_value = exchange
            e1 = mgr._get_shared_exchange()
            e2 = mgr._get_shared_exchange()
            assert e1 is e2  # cached
            MockCcxt.assert_called_once()
