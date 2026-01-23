import pytest
import os
import logging
from unittest.mock import patch
from app.utils.logger import setup_logger

def test_sensitive_data_redaction(caplog, tmp_path):
    """
    Test that sensitive data from environment variables is redacted in logs.
    """
    sensitive_value = "super_secret_token_123"
    log_file = tmp_path / "test_security.log"

    # We patch os.environ to include a sensitive variable
    # Keys with SECRET, KEY, TOKEN, PASSWORD, PWD, AUTH should be targeted
    with patch.dict(os.environ, {"API_SECRET_KEY": sensitive_value}):
        # Setup logger
        # We use a unique name to ensure we get a fresh logger or handle existing one
        logger = setup_logger(name="security_test_logger", log_file=str(log_file), level=logging.INFO)

        # Log a message containing the sensitive value
        logger.info(f"Connecting with key: {sensitive_value}")

        # Check if the sensitive value is in the captured logs
        # We expect the sensitive value to be ABSENT
        assert sensitive_value not in caplog.text, f"Sensitive value '{sensitive_value}' was found in logs: {caplog.text}"

        # We expect [REDACTED] to be PRESENT
        assert "[REDACTED]" in caplog.text, "Redaction placeholder not found in logs!"

def test_multiple_sensitive_vars(caplog, tmp_path):
    """Test redaction of multiple different sensitive variables"""

    log_file = tmp_path / "test_security_2.log"
    env_vars = {
        "DB_PASSWORD": "password123",
        "AUTH_TOKEN": "token456"
    }

    with patch.dict(os.environ, env_vars):
        logger = setup_logger(name="security_test_logger_2", log_file=str(log_file), level=logging.INFO)

        logger.info(f"Login with {env_vars['DB_PASSWORD']} and {env_vars['AUTH_TOKEN']}")

        for val in env_vars.values():
            assert val not in caplog.text, f"Sensitive value '{val}' found in logs"

        assert caplog.text.count("[REDACTED]") >= 2, "Should have redacted multiple times"
