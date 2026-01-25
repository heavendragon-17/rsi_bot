import os
import logging
import pytest
import importlib
from app.utils import logger as logger_module

def test_logger_file_redaction(tmp_path):
    """
    Test that the logger redacts sensitive information from environment variables
    containing 'SECRET', 'KEY', 'TOKEN', etc.
    """
    secret = "fail_check_secret_123"
    os.environ["TEST_API_SECRET"] = secret

    # Reload to ensure the module picks up the environment variable if initialized at module level
    # (My planned implementation initializes in Formatter.__init__, so this is safe)
    importlib.reload(logger_module)

    log_file = tmp_path / "test_security.log"

    # Use a unique logger name to avoid conflicts
    logger = logger_module.setup_logger(name="sec_test_logger", log_file=str(log_file))

    logger.info(f"Leaking {secret} now")

    # Force flush handlers
    for h in logger.handlers:
        h.flush()
        h.close()

    content = log_file.read_text()

    # Assertions
    # 1. The secret should NOT be in the log
    assert secret not in content, f"SECURITY VULNERABILITY: Secret '{secret}' found in logs!"

    # 2. The placeholder [REDACTED] SHOULD be in the log
    assert "[REDACTED]" in content, "Redaction placeholder not found."
