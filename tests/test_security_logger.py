import os
import logging
import pytest
from app.utils.logger import setup_logger

def test_logger_redacts_sensitive_env_vars(caplog):
    """
    Verify that the logger redacts values of environment variables
    that contain sensitive keywords (KEY, SECRET, TOKEN, etc).
    """
    # 1. Setup sensitive environment variable
    secret_value = "supersecret123"
    os.environ["MY_SECRET_KEY"] = secret_value

    # 2. Setup logger
    # Ensure we get a fresh logger setup for the test
    logger = logging.getLogger('rsi_bot')
    logger.handlers = []  # Clear existing handlers

    # Re-initialize logger (which should now attach the RedactingFilter)
    logger = setup_logger(name='rsi_bot', level=logging.INFO)

    # 3. Log the secret
    logger.info(f"The secret is {secret_value}")

    # 4. Verify redaction
    # The secret should NOT be present
    assert secret_value not in caplog.text, "CRITICAL: Secret value was leaked in logs!"

    # The redacted placeholder SHOULD be present
    assert "***REDACTED***" in caplog.text, "Redaction placeholder not found!"

    # Cleanup
    del os.environ["MY_SECRET_KEY"]
