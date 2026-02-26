import pytest
import threading
import time
from typing import Dict, Callable
from unittest.mock import MagicMock, patch
from requests.exceptions import Timeout

from app.services.notification.telegram_bot import TelegramBot

class MockResponse:
    def __init__(self, json_data, status_code=200):
        self.json_data = json_data
        self.status_code = status_code
        self.text = str(json_data)

    def json(self):
        return self.json_data

@pytest.fixture
def mock_bot(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    bot = TelegramBot()
    # Mock the logger to avoid test spam
    bot.logger = MagicMock()
    return bot

def test_telegram_polling_success(mock_bot):
    """Test that start_polling loops and dispatches commands correctly."""
    
    # Track if our callback was executed
    callback_executed = threading.Event()
    received_chat_id = None
    
    def my_callback(chat_id: str):
        nonlocal received_chat_id
        received_chat_id = chat_id
        callback_executed.set()

    callbacks = {"/testcmd": my_callback}
    
    # We want requests.get to return a valid update the first time,
    # then raise a Timeout (normal for long-polling), and then we stop the bot.
    call_count = 0
    def mock_get(url, params, timeout):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return MockResponse({
                "ok": True,
                "result": [
                    {
                        "update_id": 1001,
                        "message": {
                            "chat": {"id": 9876},
                            "text": "/testcmd hello"
                        }
                    }
                ]
            })
        else:
            # Simulate the long-polling timeout
            raise Timeout("Mock timeout")

    with patch('requests.get', side_effect=mock_get):
        mock_bot.start_polling(callbacks)
        
        # Wait up to 2 seconds for the thread to process the first (mocked) update
        executed = callback_executed.wait(timeout=2.0)
        
        mock_bot.stop_polling()
        
    assert executed is True, "Callback was not executed"
    assert received_chat_id == "9876", "Did not receive correct chat ID from the message"

def test_telegram_polling_ignores_non_commands(mock_bot):
    """Test that regular text messages do not trigger callbacks."""
    callback_executed = threading.Event()
    
    def my_callback(chat_id: str):
        callback_executed.set()

    callbacks = {"/testcmd": my_callback}
    
    call_count = 0
    def mock_get(url, params, timeout):
        nonlocal call_count
        call_count += 1
        return MockResponse({
            "ok": True,
            "result": [
                {
                    "update_id": 1002,
                    "message": {
                        "chat": {"id": 1111},
                        "text": "just a normal message"
                    }
                }
            ]
        })

    with patch('requests.get', side_effect=mock_get):
        mock_bot.start_polling(callbacks)
        
        # Give it a tiny bit of time to run one loop
        time.sleep(0.5)
        mock_bot.stop_polling()
        
    assert not callback_executed.is_set(), "Callback should not have been executed"
