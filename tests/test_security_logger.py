import os
import logging
import io
import unittest
from app.utils.logger import setup_logger

class TestSecurityLogger(unittest.TestCase):
    def setUp(self):
        # Set a dummy secret in environment
        self.secret_key = "secret_12345_very_sensitive"
        os.environ["TEST_API_KEY"] = self.secret_key
        self.log_file = "test_security.log"

        # Capture logs
        self.log_capture = io.StringIO()
        self.handler = logging.StreamHandler(self.log_capture)

        # Reset logger
        self.logger = logging.getLogger("security_test_logger")
        # Close existing handlers
        for h in self.logger.handlers:
            h.close()
        self.logger.handlers = []

        # Call setup_logger. It will add FileHandler and StreamHandler.
        setup_logger(name="security_test_logger", log_file=self.log_file)

        # Now find the StreamHandler
        self.stream_handler = None
        for h in self.logger.handlers:
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
                self.stream_handler = h
                break

        # Hijack the stream to capture output
        if self.stream_handler:
            self.stream_handler.stream = self.log_capture
        else:
            # Fallback
            self.logger.addHandler(self.handler)

    def tearDown(self):
        # Clean up handlers
        for h in self.logger.handlers:
            h.close()
        self.logger.handlers = []

        if "TEST_API_KEY" in os.environ:
            del os.environ["TEST_API_KEY"]
        if os.path.exists(self.log_file):
            try:
                os.remove(self.log_file)
            except OSError:
                pass

    def test_redaction(self):
        # Log the secret
        self.logger.info(f"Connecting with key: {self.secret_key}")

        # Flush handlers
        for h in self.logger.handlers:
            h.flush()

        log_contents = self.log_capture.getvalue()

        # Check if secret is leaked
        if self.secret_key in log_contents:
            self.fail(f"SECURITY ALERT: Secret key was found in logs! Log: {log_contents.strip()}")

        # Verify it WAS redacted
        if "[REDACTED]" not in log_contents:
             self.fail(f"Redaction failed. Expected '[REDACTED]' but got: {log_contents.strip()}")

if __name__ == '__main__':
    unittest.main()
