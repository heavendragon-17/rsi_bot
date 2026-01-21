import logging
import os

class RedactingFormatter(logging.Formatter):
    """
    Formatter that removes sensitive information from log records.
    """
    def __init__(self, fmt=None, datefmt=None, style='%'):
        super().__init__(fmt, datefmt, style)
        self.sensitive_patterns = self._load_sensitive_patterns()

    def _load_sensitive_patterns(self):
        """
        Identify sensitive values from environment variables.
        """
        patterns = []
        # Keywords to look for in env var names
        keywords = ['KEY', 'SECRET', 'TOKEN', 'PASSWORD', 'PWD', 'AUTH']

        for key, value in os.environ.items():
            if not value or len(value) < 5:  # Skip empty or very short values
                continue

            # Check if key contains any keyword
            if any(k in key.upper() for k in keywords):
                patterns.append(value)

        return patterns

    def format(self, record):
        """
        Format the record and redact sensitive info.
        """
        original_msg = super().format(record)

        # Redact known sensitive values
        for secret in self.sensitive_patterns:
            if secret in original_msg:
                original_msg = original_msg.replace(secret, "[REDACTED]")

        return original_msg

def setup_logger(name='rsi_bot', log_file='bot.log', level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Use RedactingFormatter instead of standard Formatter
    formatter = RedactingFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Avoid adding handlers multiple times
    if not logger.handlers:
        fh = logging.FileHandler(log_file)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        logger.addHandler(ch)
        
    return logger
