"""Tests for StatusWriter + helpers (atomic writes, version read)."""

import json
import os
import threading
from datetime import UTC, datetime
from unittest.mock import patch

from app.trading.status_writer import (
    StatusWriter,
    _build_status,
    _read_version,
    _write_atomic,
)


class TestReadVersion:
    def test_missing_file_returns_defaults(self):
        with patch("app.trading.status_writer._VERSION_FILE", "/tmp/nonexistent_version_file_xyz"):
            tag, sha = _read_version()
            assert tag == "dev"
            assert sha == "unknown"

    def test_valid_version_file(self, tmp_path):
        vf = tmp_path / "VERSION"
        vf.write_text(json.dumps({"tag": "v1.2.3", "sha": "abc123"}))
        with patch("app.trading.status_writer._VERSION_FILE", str(vf)):
            tag, sha = _read_version()
            assert tag == "v1.2.3"
            assert sha == "abc123"

    def test_corrupt_json_returns_defaults(self, tmp_path):
        vf = tmp_path / "VERSION"
        vf.write_text("not-json")
        with patch("app.trading.status_writer._VERSION_FILE", str(vf)):
            tag, sha = _read_version()
            assert tag == "dev"


class TestWriteAtomic:
    def test_writes_json_successfully(self, tmp_path):
        path = str(tmp_path / "status.json")
        _write_atomic(path, {"a": 1})
        assert os.path.exists(path)
        assert json.loads(open(path).read())["a"] == 1

    def test_overwrites_existing(self, tmp_path):
        path = str(tmp_path / "status.json")
        _write_atomic(path, {"v": 1})
        _write_atomic(path, {"v": 2})
        assert json.loads(open(path).read())["v"] == 2


class TestBuildStatus:
    def test_builds_status_dict(self):
        started = datetime.now(UTC)
        with patch("app.trading.status_writer._VERSION_FILE", "/tmp/nonexistent"):
            status = _build_status([], started)
        assert "version" in status
        assert status["position_count"] == 0
        assert status["status"] == "running"
        assert status["open_positions"] == []

    def test_includes_open_positions(self):
        positions = [
            {"symbol": "BTC", "side": "BUY", "size": 1.5, "entry_price": 100.0},
        ]
        status = _build_status(positions, datetime.now(UTC))
        assert status["position_count"] == 1
        assert status["open_positions"][0]["symbol"] == "BTC"
        assert status["open_positions"][0]["side"] == "BUY"


class TestStatusWriter:
    def test_start_stop_lifecycle(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.trading.status_writer.STATUS_FILE_PATH", str(tmp_path / "status.json"))
        monkeypatch.setattr("app.trading.status_writer.STATUS_WRITE_INTERVAL", 0.1)

        writer = StatusWriter(lambda: [])
        writer.start()
        threading.Event().wait(0.2)
        writer.stop()
        assert os.path.exists(str(tmp_path / "status.json"))

    def test_loop_invokes_snapshot_hook(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.trading.status_writer.STATUS_FILE_PATH", str(tmp_path / "status.json"))
        monkeypatch.setattr("app.trading.status_writer.STATUS_WRITE_INTERVAL", 0.1)

        hook_calls: list[int] = []

        def hook() -> None:
            hook_calls.append(1)

        writer = StatusWriter(lambda: [], snapshot_hook=hook)
        writer.start()
        threading.Event().wait(0.2)
        writer.stop()
        assert len(hook_calls) >= 1

    def test_position_provider_populates_status(self, tmp_path, monkeypatch):
        status_path = tmp_path / "status.json"
        monkeypatch.setattr("app.trading.status_writer.STATUS_FILE_PATH", str(status_path))
        monkeypatch.setattr("app.trading.status_writer.STATUS_WRITE_INTERVAL", 0.1)

        positions = [{"symbol": "BTC", "side": "BUY", "size": 1.0, "entry_price": 100.0}]
        writer = StatusWriter(lambda: positions)
        writer.start()
        threading.Event().wait(0.2)
        writer.stop()

        data = json.loads(status_path.read_text())
        assert data["position_count"] == 1
        assert data["open_positions"][0]["symbol"] == "BTC"
