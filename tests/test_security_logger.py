import os
import logging
import pytest
import io
from app.utils.logger import setup_logger

def test_redacting_formatter_secrets(monkeypatch):
    """
    Test that the logger redacts values of environment variables
    that look like secrets.
    """
    # 1. Setup secret environment variables
    secret_key = "very_secret_value_123"
    api_token = "abcdef_token_456"

    monkeypatch.setenv("MY_API_KEY", secret_key)
    monkeypatch.setenv("SERVICE_TOKEN", api_token)
    monkeypatch.setenv("PUBLIC_INFO", "not_a_secret")

    # 2. Setup logger with a string stream
    log_stream = io.StringIO()
    logger = logging.getLogger("test_security_logger")
    logger.setLevel(logging.INFO)

    # We need to manually invoke the setup logic or just use the one from app/utils/logger.py
    # But since we want to test the *actual implementation*, we should rely on setup_logger
    # implementing the RedactingFormatter.
    # However, setup_logger configures handlers. We might need to reset handlers for this logger first.
    logger.handlers = []

    # Re-import to ensure we get the updated module if we were doing this in a live session,
    # but for pytest, it's fine.

    # Call the actual setup function (which we will modify)
    # We pass a unique name so we don't conflict with other tests
    # Use a dummy log file
    test_logger = setup_logger(name="test_security_logger", log_file="test_log.log")

    # Replace the handlers' stream with our StringIO for capturing
    # setup_logger creates a FileHandler and a StreamHandler.
    # We'll just add a StreamHandler with the SAME formatter used by the logger.

    # In the current implementation, setup_logger returns a logger with handlers.
    # We want to verify the formatter on those handlers redacts.

    # Let's attach our own stream handler using the logger's formatter
    handler = logging.StreamHandler(log_stream)
    if test_logger.handlers:
        handler.setFormatter(test_logger.handlers[0].formatter)
    else:
        # If no handlers (shouldn't happen), we default to basic
        pass

    test_logger.addHandler(handler)

    # 3. Log a message containing the secrets
    msg = f"Connecting with key={secret_key} and token={api_token}. Public={os.environ['PUBLIC_INFO']}"
    test_logger.info(msg)

    log_output = log_stream.getvalue()

    # 4. Verify secrets are NOT in the output
    assert secret_key not in log_output, "Secret key was leaked in logs!"
    assert api_token not in log_output, "API token was leaked in logs!"

    # 5. Verify redaction occurred
    assert "[REDACTED]" in log_output

    # 6. Verify non-secrets are present
    assert "Public=not_a_secret" in log_output

def test_redacting_formatter_standard_keys(monkeypatch):
    """
    Test standard sensitive keys like PASSWORD, SECRET, AUTH.
    """
    monkeypatch.setenv("DB_PASSWORD", "super_secret_pw")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws_key_123")

    log_stream = io.StringIO()
    logger = setup_logger(name="test_security_logger_2", log_file="test_log_2.log")

    handler = logging.StreamHandler(log_stream)
    if logger.handlers:
        handler.setFormatter(logger.handlers[0].formatter)
    logger.addHandler(handler)

    logger.info("DB pass is super_secret_pw and AWS is aws_key_123")

    output = log_stream.getvalue()
    assert "super_secret_pw" not in output
    assert "aws_key_123" not in output
    assert "[REDACTED]" in output
