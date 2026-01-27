import os
import logging
import pytest
from app.utils.logger import setup_logger

def test_sensitive_data_redaction(tmp_path):
    """
    Verifies that sensitive environment variables are redacted from logs.
    """
    # Setup
    secret_value = "super_secret_api_key_123"
    os.environ["MOCK_API_KEY"] = secret_value

    # Use a unique logger name to avoid conflicts with other tests
    logger_name = f"security_test_logger_{os.getpid()}"
    log_file = tmp_path / "test_security.log"

    logger = setup_logger(name=logger_name, log_file=str(log_file), level=logging.INFO)

    # Act
    logger.info(f"Connecting with key: {secret_value}")

    # Force flush and close to ensure write
    for handler in logger.handlers:
        handler.flush()
        handler.close()

    # Read log
    with open(str(log_file), 'r') as f:
        log_content = f.read()

    # Clean up environment
    del os.environ["MOCK_API_KEY"]

    # Verification
    # The secret should NOT be in the log
    assert secret_value not in log_content, f"SECURITY VULNERABILITY: Secret value '{secret_value}' found in logs!"

    # The redacted placeholder SHOULD be in the log
    assert "[REDACTED]" in log_content, "Redaction placeholder '[REDACTED]' not found in logs."
