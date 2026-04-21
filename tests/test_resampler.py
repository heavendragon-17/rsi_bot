"""Unit tests for resample_dataframe — pandas OHLC aggregation."""

import pandas as pd

from app.data.resampler import resample_dataframe


def _mk_df(rows):
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df.set_index("timestamp")


class TestResampler:
    def test_empty_returns_empty(self):
        out = resample_dataframe(pd.DataFrame(), "1h")
        assert out.empty

    def test_none_returns_empty(self):
        out = resample_dataframe(None, "1h")
        assert out.empty

    def test_1m_to_5m_aggregation(self):
        rows = []
        base = pd.Timestamp("2024-01-01 00:00:00")
        for i in range(10):
            rows.append({
                "timestamp": base + pd.Timedelta(minutes=i),
                "open": 100 + i,
                "high": 105 + i,
                "low": 95 + i,
                "close": 102 + i,
                "volume": 10,
            })
        df = _mk_df(rows)
        out = resample_dataframe(df, "5m")
        assert len(out) == 2
        # first 5m group: open=100, high=109, low=95, close=106, volume=50
        assert out.iloc[0]["open"] == 100
        assert out.iloc[0]["high"] == 109
        assert out.iloc[0]["low"] == 95
        assert out.iloc[0]["close"] == 106
        assert out.iloc[0]["volume"] == 50

    def test_hours_resample(self):
        rows = []
        base = pd.Timestamp("2024-01-01 00:00:00")
        for i in range(120):  # 2 hours of 1-minute bars
            rows.append({
                "timestamp": base + pd.Timedelta(minutes=i),
                "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 1,
            })
        df = _mk_df(rows)
        out = resample_dataframe(df, "1h")
        assert len(out) == 2

    def test_timestamp_column_not_index(self):
        rows = []
        base = pd.Timestamp("2024-01-01")
        for i in range(10):
            rows.append({
                "timestamp": base + pd.Timedelta(minutes=i),
                "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 1,
            })
        df = pd.DataFrame(rows)
        out = resample_dataframe(df, "5m")
        assert len(out) == 2
