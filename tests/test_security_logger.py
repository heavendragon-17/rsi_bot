import unittest
import logging
import os
import io
import re
from unittest.mock import patch

from app.utils.logger import setup_logger

class TestSecurityLogger(unittest.TestCase):
    def setUp(self):
        # Set fake secrets in environment
        self.fake_secrets = {
            'TELEGRAM_BOT_TOKEN': '123456:SECRET_TOKEN_TELEGRAM',
            'BINANCE_API_KEY': 'vmPUZE6mv9sd5VNHk4HlWFsOr6aKE2zvsw0MuI7QlTrehjdJqW8574g',
            'BINANCE_SECRET_KEY': 'NhqPtmdSJYdKjPEvQDOL7xrXkxAm4StcdAnFOqKS8f9eKea664323uL',
            'LIGHTER_SECRET_KEY': '0x123456789abcdef123456789abcdef123456789abcdef123456789abcdef12'
        }
        self.patcher = patch.dict(os.environ, self.fake_secrets)
        self.patcher.start()

        # Setup logger capture
        self.log_capture_string = io.StringIO()
        self.logger = setup_logger(name='test_security_bot')

        # Clear existing handlers to avoid duplicates/confusion and ensure we capture output
        self.logger.handlers = []

        # Create handler with the same formatter as setup_logger would use
        # We need to manually re-create the formatter because setup_logger attaches it to file/stream handlers
        # but we are attaching a string IO handler.
        # However, setup_logger logic calls get_redacted_patterns() internally.
        # We can't easily extract the formatter from the function return without accessing handlers.

        # Let's call setup_logger and assume it attaches handlers we can inspect or replace.
        # Actually, setup_logger adds handlers. Let's inspect them.
        logger_for_setup = setup_logger(name='test_security_bot_setup')
        formatter = logger_for_setup.handlers[0].formatter

        ch = logging.StreamHandler(self.log_capture_string)
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)
        self.logger.setLevel(logging.INFO)

    def tearDown(self):
        self.patcher.stop()
        # Clean up logger
        self.logger.handlers = []

    def test_redaction_direct_logging(self):
        """Test that secrets logged directly are redacted."""
        secret = self.fake_secrets['TELEGRAM_BOT_TOKEN']
        self.logger.info(f"The token is {secret}")

        logs = self.log_capture_string.getvalue()
        self.assertNotIn(secret, logs)
        self.assertIn("[TELEGRAM_BOT_TOKEN_REDACTED]", logs)

    def test_redaction_exception(self):
        """Test that secrets in exception messages are redacted."""
        secret = self.fake_secrets['BINANCE_API_KEY']
        try:
            raise ValueError(f"Failed with key {secret}")
        except ValueError as e:
            self.logger.error(f"Exception occurred: {e}")

        logs = self.log_capture_string.getvalue()
        self.assertNotIn(secret, logs)
        self.assertIn("[BINANCE_API_KEY_REDACTED]", logs)

    def test_redaction_multiple_secrets(self):
        """Test redacting multiple secrets in one message."""
        s1 = self.fake_secrets['BINANCE_SECRET_KEY']
        s2 = self.fake_secrets['LIGHTER_SECRET_KEY']

        self.logger.warning(f"Leaking {s1} and {s2}")

        logs = self.log_capture_string.getvalue()
        self.assertNotIn(s1, logs)
        self.assertNotIn(s2, logs)
        self.assertIn("[BINANCE_SECRET_KEY_REDACTED]", logs)
        self.assertIn("[LIGHTER_SECRET_KEY_REDACTED]", logs)

if __name__ == '__main__':
    unittest.main()
