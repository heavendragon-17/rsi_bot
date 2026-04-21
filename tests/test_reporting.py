"""Unit tests for backtest reporting: reporter, html, export, batch_report."""

import json
import os
from datetime import datetime

import pandas as pd

from app.backtest.reporting.batch_report import BatchHtmlGenerator
from app.backtest.reporting.export import (
    _safe_serialize,
    _safe_value,
    export_combined_signals,
    export_json_report,
    export_signals_to_csv,
)
from app.backtest.reporting.html import (
    _build_ticker_data,
    _build_trades_table,
    _render_params_badges,
    format_duration,
    generate_html_report,
)
from app.backtest.reporting.reporter import BacktestReporter


def _mk_results_dict():
    """A minimal populated results dict as produced by BacktestEngine."""
    return {
        "initial_balance": 1000.0,
        "final_balance": 1150.0,
        "net_profit": 150.0,
        "net_profit_pct": 15.0,
        "metrics": {
            "total_trades": 3,
            "win_count": 2,
            "loss_count": 1,
            "win_rate": 66.7,
            "profit_factor": 3.0,
            "risk_reward": 2.0,
            "expectancy": 50.0,
            "avg_hold_hours": 5.5,
            "avg_win": 100.0,
            "avg_loss": -50.0,
            "largest_win": 150.0,
            "largest_loss": -50.0,
            "max_consec_wins": 2,
            "max_consec_losses": 1,
            "gross_profit": 200,
            "gross_loss": 50,
            "exit_reason_counts": {"TP1": 2, "SL": 1},
        },
        "drawdown": {"max_drawdown_pct": 5.0, "avg_drawdown_pct": 2.0, "max_dd_duration": 1},
        "risk_metrics": {
            "sharpe_ratio": 1.2,
            "sortino_ratio": 1.5,
            "calmar_ratio": 0.5,
            "volatility": 3.0,
        },
        "monthly_returns": {
            "2024-01": {"trades": 3, "pnl": 150.0, "pnl_pct": 15.0},
        },
        "equity_curve": [
            {"date": "2024-01-01", "balance": 1000.0},
            {"date": "2024-01-05", "balance": 1150.0},
        ],
        "round_trips": [
            {
                "symbol": "BTC/USDT",
                "entry_time": "2024-01-01 10:00",
                "exit_time": "2024-01-01 15:00",
                "entry_price": 50000.0,
                "exit_price": 51000.0,
                "avg_exit_price": 51000.0,
                "pnl": 100.0,
                "pnl_pct": 2.0,
                "hold_duration_hours": 5.0,
                "exit_reason": "TP1",
                "entry_rsi_ema9": 30.0,
                "entry_rsi_wma45": 40.0,
                "entry_spread": 10.0,
                "above_count": 2,
            },
            {
                "symbol": "ETH/USDT",
                "entry_time": "2024-01-02 10:00",
                "exit_time": "2024-01-02 16:00",
                "entry_price": 2000.0,
                "exit_price": 1950.0,
                "avg_exit_price": 1950.0,
                "pnl": -50.0,
                "pnl_pct": -2.5,
                "hold_duration_hours": 6.0,
                "exit_reason": "SL",
            },
            {
                "symbol": "BTC/USDT",
                "entry_time": "2024-01-03 10:00",
                "exit_time": "2024-01-03 14:00",
                "entry_price": 51000.0,
                "exit_price": 52000.0,
                "avg_exit_price": 52000.0,
                "pnl": 100.0,
                "pnl_pct": 1.96,
                "hold_duration_hours": 4.0,
                "exit_reason": "TP2",
            },
        ],
    }


class TestFormatDuration:
    def test_none_returns_na(self):
        assert format_duration(None) == "N/A"

    def test_nan_returns_na(self):
        assert format_duration(float("nan")) == "N/A"

    def test_minutes(self):
        assert format_duration(0.5) == "30m"

    def test_hours(self):
        assert format_duration(3.5) == "3.5h"

    def test_days(self):
        assert format_duration(48.0) == "2.0d"


class TestParamsBadges:
    def test_empty_params(self):
        out = _render_params_badges({})
        assert "<p" in out

    def test_nr_max_above_ema21(self):
        out = _render_params_badges({"nr_max_above_ema21": 5})
        assert "max_above_ema21: 5" in out

    def test_both_params(self):
        out = _render_params_badges({"nr_max_above_ema21": 3, "nr_rsi_spread_min": 2.5})
        assert "max_above_ema21" in out
        assert "rsi_spread_min" in out


class TestTickerData:
    def test_empty_df(self):
        out = _build_ticker_data(pd.DataFrame())
        assert out[0] == []
        assert out[2] == "N/A"

    def test_populated_df(self):
        df = pd.DataFrame([
            {"symbol": "BTC", "pnl": 100, "hold_duration_hours": 2.0},
            {"symbol": "ETH", "pnl": -50, "hold_duration_hours": 3.0},
            {"symbol": "BTC", "pnl": 50, "hold_duration_hours": 1.0},
        ])
        syms, pnl_map, best_name, _, worst_name, _, per_sym, pills = _build_ticker_data(df)
        assert "BTC" in syms and "ETH" in syms
        assert pnl_map["BTC"] == 150
        assert pnl_map["ETH"] == -50
        assert best_name == "BTC"
        assert worst_name == "ETH"
        assert "ticker-badge" in per_sym
        assert "filter-pill" in pills


class TestTradesTable:
    def test_empty(self):
        out = _build_trades_table(pd.DataFrame(), {}, "", "")
        assert "No completed trades" in out

    def test_with_optional_columns(self):
        df = pd.DataFrame([
            {
                "symbol": "BTC",
                "entry_time": "2024-01-01",
                "exit_time": "2024-01-02",
                "entry_price": 100.0,
                "exit_price": 110.0,
                "avg_exit_price": 110.0,
                "pnl": 10.0,
                "pnl_pct": 10.0,
                "hold_duration_hours": 2.0,
                "exit_reason": "TP1",
                "entry_rsi_ema9": 30.0,
                "entry_rsi_wma45": 40.0,
                "entry_spread": 10.0,
                "above_count": 3.0,
            }
        ])
        out = _build_trades_table(df, {"BTC": "#fff"}, "", "")
        assert "BTC" in out
        assert "TP1" in out


class TestGenerateHtmlReport:
    def test_returns_html_string(self):
        html = generate_html_report(
            results=_mk_results_dict(),
            symbol="BTC/USDT",
            timeframe="5m",
            strategy_name="rsi_momentum",
            return_only=True,
        )
        assert isinstance(html, str)
        assert "<html" in html
        assert "Backtest Report" in html

    def test_writes_file_when_return_only_false(self, tmp_path):
        path = generate_html_report(
            results=_mk_results_dict(),
            symbol="BTC/USDT",
            timeframe="5m",
            strategy_name="rsi_momentum",
            output_dir=str(tmp_path),
        )
        assert path is not None
        assert os.path.exists(path)

    def test_with_strategy_params(self):
        html = generate_html_report(
            results=_mk_results_dict(),
            symbol="BTC",
            timeframe="1h",
            strategy_name="test",
            strategy_params={"nr_max_above_ema21": 5},
            return_only=True,
        )
        assert "max_above_ema21: 5" in html

    def test_empty_monthly_returns(self):
        results = _mk_results_dict()
        results["monthly_returns"] = {}
        html = generate_html_report(results=results, symbol="BTC", timeframe="1m",
                                    strategy_name="s", return_only=True)
        assert "No monthly data" in html

    def test_infinite_profit_factor(self):
        results = _mk_results_dict()
        results["metrics"]["profit_factor"] = float("inf")
        results["metrics"]["risk_reward"] = float("inf")
        html = generate_html_report(results=results, symbol="BTC", timeframe="1m",
                                    strategy_name="s", return_only=True)
        assert "INF" in html


class TestReporter:
    def test_no_trades_returns_none(self, tmp_path):
        rep = BacktestReporter(
            results={"round_trips": [], "metrics": {"total_trades": 0}},
            symbol="BTC", timeframe="5m", strategy_name="s",
        )
        assert rep.generate_report(str(tmp_path)) is None

    def test_generates_report_and_csv(self, tmp_path):
        rep = BacktestReporter(
            results=_mk_results_dict(),
            symbol="BTC/USDT", timeframe="5m", strategy_name="rsi_momentum",
        )
        path = rep.generate_report(str(tmp_path))
        assert path is not None
        assert os.path.exists(path)
        # CSV was written to csv/ subfolder
        csv_files = list((tmp_path / "csv").glob("*.csv"))
        assert csv_files

    def test_private_html_delegation(self, tmp_path):
        rep = BacktestReporter(
            results=_mk_results_dict(),
            symbol="BTC", timeframe="5m", strategy_name="s",
        )
        html = rep._generate_html_report(return_only=True, output_dir=str(tmp_path))
        assert isinstance(html, str)


class TestExportSignalsToCsv:
    def test_no_history(self, tmp_path):
        class _Engine:
            strategy = type("S", (), {})()
            exchange = type("E", (), {})()
        assert export_signals_to_csv(_Engine(), "BTC", str(tmp_path)) is None

    def test_empty_signals(self, tmp_path):
        class _Engine:
            strategy = type("S", (), {"signal_history": []})()
            exchange = None
        assert export_signals_to_csv(_Engine(), "BTC", str(tmp_path)) is None

    def test_writes_csv_from_signal_history(self, tmp_path):
        class _Engine:
            strategy = type("S", (), {"signal_history": [
                {"timestamp": "2024-01-01", "signal_type": "ENTRY", "price": 100},
                {"timestamp": "2024-01-02", "signal_type": "EXIT", "price": 110},
            ]})()
            exchange = None
        path = export_signals_to_csv(_Engine(), "BTC/USDT", str(tmp_path))
        assert path is not None
        assert os.path.exists(path)

    def test_reconstructs_from_trade_history(self, tmp_path):
        class _Strategy:
            pass
        class _Exchange:
            trade_history = [
                {"timestamp": datetime(2024, 1, 1), "side": "buy", "price": 100, "amount": 1.0},
                {"id": 42, "side": "sell", "price": 110, "amount": 1.0},
            ]
        class _Engine:
            strategy = _Strategy()
            exchange = _Exchange()
        path = export_signals_to_csv(_Engine(), "BTC", str(tmp_path))
        assert path is not None


class TestExportCombinedSignals:
    def test_missing_files_returns_none(self, tmp_path):
        assert export_combined_signals(
            [{"symbol": "BTC"}], str(tmp_path)
        ) is None

    def test_combines_existing_csvs(self, tmp_path):
        df1 = pd.DataFrame([{"timestamp": "2024-01-01", "a": 1}])
        df2 = pd.DataFrame([{"timestamp": "2024-01-02", "a": 2}])
        df1.to_csv(tmp_path / "signals_BTC.csv", index=False)
        df2.to_csv(tmp_path / "signals_ETH.csv", index=False)
        path = export_combined_signals(
            [{"symbol": "BTC"}, {"symbol": "ETH"}], str(tmp_path)
        )
        assert path is not None
        combined = pd.read_csv(path)
        assert len(combined) == 2


class TestExportJsonReport:
    def test_writes_json(self, tmp_path):
        out = tmp_path / "out" / "report.json"
        export_json_report({"a": 1, "b": [1, 2, 3]}, str(out))
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["a"] == 1


class TestSafeHelpers:
    def test_safe_serialize_datetime(self):
        assert "2024" in _safe_serialize(datetime(2024, 1, 1))

    def test_safe_serialize_pd_timestamp(self):
        assert "2024" in _safe_serialize(pd.Timestamp("2024-01-01"))

    def test_safe_serialize_series(self):
        assert _safe_serialize(pd.Series([1, 2])) == [1, 2]

    def test_safe_value_decimal(self):
        from decimal import Decimal
        assert _safe_value(Decimal("1.5")) == 1.5

    def test_safe_value_primitives(self):
        assert _safe_value(1) == 1
        assert _safe_value("a") == "a"
        assert _safe_value(True) is True

    def test_safe_value_fallback(self):
        assert _safe_value(object()) != ""


class TestBatchHtmlGenerator:
    def _mk_result(self, sym, profit):
        html_doc = "<html><body>inner-content</body></html>"
        rt = pd.DataFrame([{
            "pnl": profit,
            "exit_time": "2024-01-02",
        }])
        return {
            "symbol": sym,
            "metrics": {"win_rate": 50.0},
            "html": html_doc,
            "profit": profit,
            "profit_pct": profit / 10.0,
            "initial_balance": 1000.0,
            "final_balance": 1000.0 + profit,
            "drawdown": {"avg_drawdown_pct": 1.5},
            "trades": 1,
            "round_trips": rt,
        }

    def test_generate_writes_file(self, tmp_path):
        gen = BatchHtmlGenerator([self._mk_result("BTC", 100), self._mk_result("ETH", -30)])
        out = tmp_path / "batch.html"
        gen.generate(filename=str(out))
        assert out.exists()
        text = out.read_text()
        assert "Portfolio Overview" in text
        assert "BTC" in text

    def test_empty_results_generate(self, tmp_path):
        gen = BatchHtmlGenerator([])
        out = tmp_path / "empty.html"
        gen.generate(filename=str(out))
        assert out.exists()

    def test_extract_body_content(self):
        gen = BatchHtmlGenerator([])
        assert gen._extract_body_content("<body>xyz</body>") == "xyz"
        assert gen._extract_body_content("no-body") == "no-body"

    def test_drawdown_as_float(self, tmp_path):
        r = self._mk_result("BTC", 10)
        r["drawdown"] = 2.5  # scalar, not dict
        gen = BatchHtmlGenerator([r])
        out = tmp_path / "f.html"
        gen.generate(filename=str(out))
        assert out.exists()
