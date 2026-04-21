"""Tests for backtest config_builder."""

from app.backtest.config_builder import build_backtest_config


class TestConfigBuilder:
    def test_basic_no_yaml(self):
        c = build_backtest_config(
            symbol="BTC/USDT",
            timeframe="5m",
            strategy_name="rsi_no_retest",
            load_yaml=False,
        )
        assert c["symbols"] == ["BTC/USDT"]
        assert c["timeframe"] == "5m"
        assert c["strategy"] == "rsi_no_retest"
        assert c["bot"]["timeframe"] == "5m"
        assert c["backtest"]["initial_balance"] == 10000.0
        assert c["risk"]["leverage"] == 10

    def test_custom_risk_params(self):
        c = build_backtest_config(
            symbol="ETH/USDT",
            timeframe="1h",
            strategy_name="rsi_momentum",
            load_yaml=False,
            initial_balance=5000,
            leverage=5,
            risk_per_trade_pct=0.01,
            tp1_close_pct=0.5,
            tp2_close_pct=1.0,
            max_position_size_pct=0.3,
            min_sl_distance_pct=0.005,
            use_risk_based_sizing=True,
            use_initial_capital_for_risk=False,
            taker_fee=0.0005,
            maker_fee=0.0002,
        )
        assert c["backtest"]["initial_balance"] == 5000
        assert c["risk"]["tp1_close_pct"] == 0.5
        assert c["risk"]["tp2_close_pct"] == 1.0
        assert c["risk"]["max_position_size_pct"] == 0.3
        assert c["risk"]["min_sl_distance_pct"] == 0.005
        assert c["risk"]["use_risk_based_sizing"] is True
        assert c["risk"]["use_initial_capital_for_risk"] is False
        assert c["risk"]["taker_fee"] == 0.0005
        assert c["risk"]["maker_fee"] == 0.0002

    def test_strategy_params_merge(self):
        c = build_backtest_config(
            symbol="BTC/USDT",
            timeframe="5m",
            strategy_name="rsi_no_retest",
            load_yaml=False,
            params={"nr_max_above_ema21": 3},
        )
        assert c["strategy_params"]["nr_max_above_ema21"] == 3

    def test_slippage_always_written(self):
        c = build_backtest_config(
            symbol="BTC/USDT",
            timeframe="5m",
            strategy_name="s",
            load_yaml=False,
            slippage_pct=0.001,
        )
        assert c["slippage_pct"] == 0.001

    def test_load_yaml_from_path(self, tmp_path):
        import yaml
        cfg = {"backtest": {"duration_days": 30}, "extra": "preserved"}
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(yaml.dump(cfg))
        c = build_backtest_config(
            symbol="BTC/USDT",
            timeframe="5m",
            strategy_name="s",
            load_yaml=True,
            base_config_path=str(cfg_file),
        )
        # Fields from yaml are preserved
        assert c["extra"] == "preserved"
        assert c["backtest"]["duration_days"] == 30
        # Core fields overridden
        assert c["symbols"] == ["BTC/USDT"]

    def test_missing_yaml_path_falls_back_to_empty(self):
        c = build_backtest_config(
            symbol="BTC/USDT",
            timeframe="5m",
            strategy_name="s",
            load_yaml=True,
            base_config_path="/nonexistent/config.yaml",
        )
        # Should not crash, just use empty base
        assert c["symbols"] == ["BTC/USDT"]
