"""Tests for data availability + download routes (M13 coverage gap)."""
import pytest
import threading
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


class TestDataStatus:
    @patch("app.api.routes.data.os.path.exists", return_value=False)
    def test_status_unavailable(self, mock_exists):
        resp = client.get("/api/data/status", params={"symbol": "BTC/USDT", "timeframe": "5m"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is False
        assert data["symbol"] == "BTC/USDT"
        assert data["timeframe"] == "5m"

    @patch("app.api.routes.data.pd.read_csv")
    @patch("app.api.routes.data.os.path.exists", return_value=True)
    def test_status_available(self, mock_exists, mock_read_csv):
        import pandas as pd
        mock_read_csv.return_value = pd.DataFrame({
            "timestamp": pd.to_datetime(["2023-01-01", "2023-01-02", "2023-01-03"]),
        })
        resp = client.get("/api/data/status", params={"symbol": "BTC/USDT", "timeframe": "1h"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is True
        assert data["candle_count"] == 3
        assert data["date_range"] is not None


class TestDownload:
    @patch("threading.Thread")
    def test_download_starts_job(self, mock_thread_cls):
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread

        resp = client.post("/api/data/download", json={
            "symbol": "ETH/USDT", "timeframe": "5m", "limit": 1000
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        assert data["status"] == "downloading"
