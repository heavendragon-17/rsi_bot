"""Tests for Telegram /force_deploy, /deploy_status, /cancel_deploy, /bot_version handlers."""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

from app.notification.deploy_commands import (
    _read_json,
    handle_bot_version,
    handle_cancel_deploy,
    handle_deploy_status,
    handle_force_deploy,
)


class TestReadJson:
    def test_missing(self):
        assert _read_json("/nonexistent/path/xyz") is None

    def test_invalid(self, tmp_path):
        p = tmp_path / "f.json"
        p.write_text("not json")
        assert _read_json(str(p)) is None

    def test_valid(self, tmp_path):
        p = tmp_path / "f.json"
        p.write_text(json.dumps({"a": 1}))
        assert _read_json(str(p)) == {"a": 1}


class TestForceDeploy:
    def test_writes_flag(self, tmp_path, monkeypatch):
        flag = tmp_path / "force"
        monkeypatch.setattr("app.notification.deploy_commands.FORCE_DEPLOY_FLAG", str(flag))
        send = MagicMock()
        handle_force_deploy(send, chat_id="cid")
        assert flag.exists()
        send.assert_called_once()

    def test_write_failure(self, monkeypatch):
        monkeypatch.setattr(
            "app.notification.deploy_commands.FORCE_DEPLOY_FLAG",
            "/nonexistent/nested/path/flag",
        )
        send = MagicMock()
        handle_force_deploy(send, chat_id="cid")
        # Error message should be sent
        call = send.call_args
        assert "Failed" in call[0][0]


class TestDeployStatus:
    def test_no_state(self, monkeypatch):
        monkeypatch.setattr(
            "app.notification.deploy_commands.DEPLOY_STATE_PATH",
            "/nonexistent",
        )
        send = MagicMock()
        handle_deploy_status(send, chat_id="cid")
        send.assert_called_once()
        assert "No deploy state" in send.call_args[0][0]

    def test_waiting_state_with_bot_status(self, tmp_path, monkeypatch):
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({
            "state": "waiting",
            "tag": "v1.0.0",
            "waiting_since": datetime.now(UTC).isoformat(),
            "last_error": "note text",
        }))
        status_file = tmp_path / "status.json"
        status_file.write_text(json.dumps({"position_count": 2}))

        monkeypatch.setattr(
            "app.notification.deploy_commands.DEPLOY_STATE_PATH", str(state_file)
        )
        monkeypatch.setattr(
            "app.notification.deploy_commands.STATUS_FILE_PATH", str(status_file)
        )

        send = MagicMock()
        handle_deploy_status(send, chat_id="cid")
        msg = send.call_args[0][0]
        assert "waiting" in msg
        assert "v1.0.0" in msg
        assert "2" in msg  # position count
        assert "note text" in msg

    def test_with_last_deploy(self, tmp_path, monkeypatch):
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({
            "state": "idle",
            "last_deploy": "2024-01-01T12:00:00",
            "last_result": "success",
        }))
        monkeypatch.setattr(
            "app.notification.deploy_commands.DEPLOY_STATE_PATH", str(state_file)
        )
        send = MagicMock()
        handle_deploy_status(send, chat_id="cid")
        msg = send.call_args[0][0]
        assert "success" in msg


class TestCancelDeploy:
    def test_no_pending_deploy(self, monkeypatch):
        monkeypatch.setattr(
            "app.notification.deploy_commands.DEPLOY_STATE_PATH", "/nonexistent"
        )
        send = MagicMock()
        handle_cancel_deploy(send, chat_id="cid")
        assert "No pending deploy" in send.call_args[0][0]

    def test_cannot_cancel_deploying(self, tmp_path, monkeypatch):
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({"state": "deploying"}))
        monkeypatch.setattr(
            "app.notification.deploy_commands.DEPLOY_STATE_PATH", str(state_file)
        )
        send = MagicMock()
        handle_cancel_deploy(send, chat_id="cid")
        assert "already in progress" in send.call_args[0][0]

    def test_writes_cancel_flag_when_waiting(self, tmp_path, monkeypatch):
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({"state": "waiting", "tag": "v1"}))
        flag = tmp_path / "cancel"
        monkeypatch.setattr(
            "app.notification.deploy_commands.DEPLOY_STATE_PATH", str(state_file)
        )
        monkeypatch.setattr(
            "app.notification.deploy_commands.CANCEL_DEPLOY_FLAG", str(flag)
        )
        send = MagicMock()
        handle_cancel_deploy(send, chat_id="cid")
        assert flag.exists()
        assert "Cancel requested" in send.call_args[0][0]


class TestBotVersion:
    def test_no_version_no_status(self, monkeypatch):
        monkeypatch.setattr(
            "app.notification.deploy_commands._VERSION_FILE", "/nonexistent"
        )
        monkeypatch.setattr(
            "app.notification.deploy_commands.STATUS_FILE_PATH", "/nonexistent"
        )
        send = MagicMock()
        handle_bot_version(send, chat_id="cid")
        msg = send.call_args[0][0]
        assert "dev" in msg or "unknown" in msg

    def test_with_version_and_status(self, tmp_path, monkeypatch):
        vf = tmp_path / "v"
        vf.write_text(json.dumps({"tag": "v1.0", "sha": "abc", "deployed_at": "2024-01-01T00:00:00"}))
        sf = tmp_path / "s"
        sf.write_text(json.dumps({
            "status": "running",
            "uptime_seconds": 120,
            "position_count": 1,
            "pid": 1234,
            "updated_at": datetime.now(UTC).isoformat(),
        }))
        monkeypatch.setattr(
            "app.notification.deploy_commands._VERSION_FILE", str(vf)
        )
        monkeypatch.setattr(
            "app.notification.deploy_commands.STATUS_FILE_PATH", str(sf)
        )
        send = MagicMock()
        handle_bot_version(send, chat_id="cid")
        msg = send.call_args[0][0]
        assert "v1.0" in msg
        assert "running" in msg
        assert "1234" in msg

    def test_stale_status(self, tmp_path, monkeypatch):
        sf = tmp_path / "s"
        sf.write_text(json.dumps({
            "status": "running",
            "uptime_seconds": 120,
            "position_count": 0,
            "pid": 1,
            "updated_at": "2000-01-01T00:00:00+00:00",  # Old
        }))
        monkeypatch.setattr(
            "app.notification.deploy_commands._VERSION_FILE", "/nonexistent"
        )
        monkeypatch.setattr(
            "app.notification.deploy_commands.STATUS_FILE_PATH", str(sf)
        )
        send = MagicMock()
        handle_bot_version(send, chat_id="cid")
        msg = send.call_args[0][0]
        assert "stale" in msg.lower()
