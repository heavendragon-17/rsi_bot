"""Tests for CliProgressBar CLI widget."""

import io
import sys

from app.backtest.runners.progress import CliProgressBar, _fmt_time


class TestFmtTime:
    def test_under_minute(self):
        assert _fmt_time(42.5) == "0:42"

    def test_minutes(self):
        assert _fmt_time(125) == "2:05"

    def test_hours(self):
        assert _fmt_time(3665) == "1:01:05"


class TestProgressBar:
    def test_update_and_finish(self, monkeypatch):
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stderr", buf)
        bar = CliProgressBar("Test", bar_width=80)
        bar.update(25)
        bar.update(50)
        bar.finish()
        assert "Test" in buf.getvalue()
        assert "%" in buf.getvalue()

    def test_update_dict(self, monkeypatch):
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stderr", buf)
        bar = CliProgressBar("T", bar_width=60)
        bar.update({"pct": 42})
        assert " 42%" in buf.getvalue()

    def test_same_pct_skipped(self, monkeypatch):
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stderr", buf)
        bar = CliProgressBar("T", bar_width=40)
        bar.update(10)
        out1 = buf.getvalue()
        bar.update(10)
        out2 = buf.getvalue()
        assert out1 == out2  # no additional write

    def test_clamps_to_0_100(self, monkeypatch):
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stderr", buf)
        bar = CliProgressBar("T", bar_width=40)
        bar.update(-5)
        bar.update(150)
        assert "100%" in buf.getvalue()

    def test_finish_with_extra(self, monkeypatch):
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stderr", buf)
        bar = CliProgressBar("T", bar_width=40)
        bar.update(100)
        bar.finish(extra="3 symbols")
        assert "done in" in buf.getvalue()
        assert "3 symbols" in buf.getvalue()
