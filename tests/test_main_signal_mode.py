"""Entry-point tests for main.main() mode branching (slice 8)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import yaml


@pytest.fixture
def signal_config(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "bot": {"mode": "signal", "debug": True},
                "telegram": {"group_id": -100, "debug_topic_id": 99},
                "timeframe": "15m",
                "symbols": ["BTC/USDT"],
                "risk": {
                    "risk_per_trade_pct": 0.002,
                    "max_position_size_pct": 0.99,
                    "leverage": 10,
                    "tp1_close_pct": 1,
                    "tp2_close_pct": 0,
                    "min_sl_distance_pct": 0.003,
                },
                "strategies": [
                    {
                        "name": "rsi_no_retest",
                        "active": True,
                        "telegram_topic_id": 42,
                    },
                ],
            }
        )
    )
    return str(path)


@pytest.fixture
def live_config(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "bot": {"mode": "sim", "debug": True},
                "exchange": {"name": "binanceusdm"},
                "timeframe": "15m",
                "symbols": ["BTC/USDT"],
                "strategy": "rsi_no_retest",
                "risk": {
                    "risk_per_trade_pct": 0.002,
                    "max_position_size_pct": 0.99,
                    "leverage": 10,
                    "tp1_close_pct": 1,
                    "tp2_close_pct": 0,
                    "min_sl_distance_pct": 0.003,
                },
                "backtest": {"initial_balance": 10000},
                "sim": {"initial_balance": 10000},
            }
        )
    )
    return str(path)


class TestSignalBranch:
    def test_signal_mode_routes_to_signal_runner(self, signal_config, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")

        import main

        with (
            patch("main.NotificationService") as MockNS,
            patch(
                "app.notification.telegram_notifier.TelegramBot"
            ) as MockBot,
            patch("app.signal.runner.SignalRunner") as MockRunner,
        ):
            MockBot.return_value = MagicMock()
            ns_instance = MagicMock()
            MockNS.return_value = ns_instance
            runner_instance = MagicMock()
            MockRunner.return_value = runner_instance

            main.main(config_path=signal_config)

            MockRunner.assert_called_once()
            runner_instance.start.assert_called_once()
            runner_instance.wait.assert_called_once()
            runner_instance.stop.assert_called_once()
            callbacks = ns_instance.start_command_polling.call_args.kwargs["extra_callbacks"]
            assert "/topics" in callbacks
            assert "/test_signal" in callbacks

    def test_signal_mode_missing_telegram_token_exits(
        self, signal_config, monkeypatch
    ):
        """Signal mode is useless without Telegram; missing token → exit 1."""
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

        import main

        with pytest.raises(SystemExit) as exc:
            main.main(config_path=signal_config)
        assert exc.value.code == 1

    def test_signal_mode_invalid_config_exits(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")

        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text(
            yaml.safe_dump(
                {
                    "bot": {"mode": "signal"},
                    "telegram": {"group_id": -100, "debug_topic_id": 99},
                    "timeframe": "15m",
                    "symbols": ["BTC/USDT"],
                    "strategies": [
                        # ghost_strategy not in STRATEGY_MAP → resolver raises
                        {
                            "name": "ghost_strategy",
                            "active": True,
                            "telegram_topic_id": 42,
                        },
                    ],
                }
            )
        )

        import main

        with (
            patch(
                "app.notification.telegram_notifier.TelegramBot"
            ) as MockBot,
        ):
            MockBot.return_value = MagicMock()
            with pytest.raises(SystemExit) as exc:
                main.main(config_path=str(bad_yaml))
            assert exc.value.code == 1


class TestLiveBranch:
    def test_live_mode_routes_to_multi_symbol_runner(self, live_config, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")

        import main

        with (
            patch("app.notification.telegram_notifier.TelegramBot") as MockBot,
            patch("main.NotificationService") as MockNS,
            patch("app.trading.runner.MultiSymbolRunner") as MockRunner,
            patch("app.trading.exchange.factory.create_exchange") as MockFactory,
            patch("app.trading.status_writer.StatusWriter") as MockWriter,
        ):
            MockBot.return_value = MagicMock()
            ns_instance = MagicMock()
            MockNS.return_value = ns_instance
            MockFactory.return_value = MagicMock()
            runner_instance = MagicMock()
            MockRunner.return_value = runner_instance
            MockWriter.return_value = MagicMock()

            main.main(config_path=live_config)

            MockRunner.assert_called_once()
            runner_instance.start.assert_called_once()
            runner_instance.wait.assert_called_once()
            runner_instance.stop.assert_called_once()


class TestMissingConfig:
    def test_missing_file_exits(self):
        import main

        with pytest.raises(SystemExit) as exc:
            main.main(config_path="/tmp/does-not-exist-a8f92.yaml")
        assert exc.value.code == 1


class TestBtcAlertStartupText:
    def _raw(self, strategies: list[dict]) -> dict:
        return {
            "bot": {"mode": "signal"},
            "telegram": {"group_id": -100, "debug_topic_id": 99},
            "timeframe": "15m",
            "symbols": ["ETH/USDT", "SOL/USDT"],
            "strategies": strategies,
        }

    def test_mixed_config_reports_btc_component_accurately(self):
        import main

        raw = self._raw(
            [
                {"name": "rsi_no_retest", "active": True, "telegram_topic_id": 42},
                {
                    "name": "btc_rsi_cross_alert",
                    "active": True,
                    "telegram_topic_id": 1007,
                    "symbol": "BTC/USDT",
                    "trigger_timeframes": ["5m", "15m"],
                    "trend_timeframe": "4h",
                    "rsi_period": 21,
                    "rsi_ema_period": 9,
                    "rsi_wma_period": 45,
                    "context_settle_seconds": 5,
                },
            ]
        )
        body = main._build_signal_startup_message(raw)
        assert "btc_rsi_cross_alert — topic 1007 · BTC/USDT · 5m,15m · H4 filter" in body
        # The BTC line must not borrow global timeframe/symbol-count fields.
        assert "2 symbols" not in body.split("btc_rsi_cross_alert")[1].split("\n")[0]
        assert "Active strategies: 2" in body

    def test_topic_entries_include_inactive_strategies_and_debug_topic(self):
        import main

        raw = self._raw(
            [
                {"name": "rsi_no_retest", "active": True, "telegram_topic_id": 42},
                {"name": "rsi_wma_retest", "active": False, "telegram_topic_id": 43},
            ]
        )

        assert main._build_signal_topic_entries(raw, 99) == [
            ("rsi_no_retest", 42, "active"),
            ("rsi_wma_retest", 43, "inactive"),
            ("debug", 99, "always"),
        ]

    def test_alert_only_mode_skips_fake_test_signal_callback(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")

        path = tmp_path / "alert_only.yaml"
        path.write_text(
            yaml.safe_dump(
                {
                    "bot": {"mode": "signal"},
                    "telegram": {"group_id": -100, "debug_topic_id": 99},
                    "strategies": [
                        {
                            "name": "btc_rsi_cross_alert",
                            "active": True,
                            "telegram_topic_id": 1007,
                            "symbol": "BTC/USDT",
                            "trigger_timeframes": ["5m", "15m"],
                            "trend_timeframe": "4h",
                            "rsi_period": 21,
                            "rsi_ema_period": 9,
                            "rsi_wma_period": 45,
                            "context_settle_seconds": 5,
                        }
                    ],
                }
            )
        )

        import main

        with (
            patch("main.NotificationService") as MockNS,
            patch("app.notification.telegram_notifier.TelegramBot") as MockBot,
            patch("app.signal.runner.SignalRunner") as MockRunner,
            patch("app.trading.status_writer.StatusWriter") as MockWriter,
        ):
            MockBot.return_value = MagicMock()
            ns_instance = MagicMock()
            MockNS.return_value = ns_instance
            runner_instance = MagicMock()
            # Alert-only runtime: no ordinary strategies resolved.
            runner_instance.strategies = []
            MockRunner.return_value = runner_instance
            MockWriter.return_value = MagicMock()

            main.main(config_path=str(path))

            ns_instance.start_command_polling.assert_called_once()
            callbacks = ns_instance.start_command_polling.call_args.kwargs["extra_callbacks"]
            assert "/topics" in callbacks
            assert "/test_signal" not in callbacks
