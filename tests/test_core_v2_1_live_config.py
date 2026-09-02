"""Tests for production-safe Core V2.1 routing configuration."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_live_cli_reads_chat_and_topic_from_yaml(monkeypatch, tmp_path: Path) -> None:
    import app.signal.core_v2_1.live as live_cli

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "telegram:\n  group_id: -100123\n"
        "core_v2_1:\n  active: true\n  telegram_topic_id: 4242\n",
        encoding="utf-8",
    )
    calls: list[dict] = []

    class _Runtime:
        def start(self):
            return type("Result", (), {"hydrated_candles": 0})()

        def stop(self):
            pass

    def fake_build(**kwargs):
        calls.append(kwargs)
        return _Runtime()

    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("CORE_V2_1_TOPIC_ID", raising=False)
    monkeypatch.setattr(live_cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        live_cli.CoreV21LiveSignalRuntime,
        "with_public_venues_and_telegram",
        staticmethod(fake_build),
    )
    monkeypatch.setattr(live_cli.signal, "signal", lambda *_args: None)
    monkeypatch.setattr(live_cli.threading.Event, "wait", lambda *_args: True)

    assert live_cli.main(["--config", str(config_path)]) == 0
    assert calls[0]["telegram_chat_id"] == -100123
    assert calls[0]["topic_by_symbol"]["ETHUSDT"] == 4242


def test_live_cli_exits_cleanly_when_yaml_disables_core(monkeypatch, tmp_path: Path) -> None:
    import app.signal.core_v2_1.live as live_cli

    config_path = tmp_path / "config.yaml"
    config_path.write_text("core_v2_1:\n  active: false\n", encoding="utf-8")
    monkeypatch.setattr(live_cli, "load_dotenv", lambda: None)

    assert live_cli.main(["--config", str(config_path)]) == 0


def test_live_cli_requires_topic_when_yaml_enables_core(
    monkeypatch, tmp_path: Path
) -> None:
    import app.signal.core_v2_1.live as live_cli

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "telegram:\n  group_id: -100123\n"
        "core_v2_1:\n  active: true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(live_cli, "load_dotenv", lambda: None)

    with pytest.raises(SystemExit):
        live_cli.main(["--config", str(config_path)])
