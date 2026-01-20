import logging
import os
import re

class RedactingFormatter(logging.Formatter):
    """
    Log formatter that redacts sensitive information like API keys and tokens.
    """
    def __init__(self, patterns=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.patterns = patterns or []

    def format(self, record):
        msg = super().format(record)
        for pattern, replacement in self.patterns:
            msg = re.sub(pattern, replacement, msg)
        return msg

def get_redacted_patterns():
    """
    Identify patterns to redact based on environment variables.
    """
    patterns = []

    # Common keys to look for
    keys_to_redact = [
        'TELEGRAM_BOT_TOKEN',
        'BINANCE_API_KEY',
        'BINANCE_SECRET_KEY',
        'BINANCE_TESTNET_API_KEY',
        'BINANCE_TESTNET_SECRET_KEY',
        'LIGHTER_SECRET_KEY'
    ]

    for key in keys_to_redact:
        value = os.getenv(key)
        if value and len(value) > 5: # Don't redact short/empty strings
            # Redact the value wherever it appears
            patterns.append((re.escape(value), f"[{key}_REDACTED]"))

    return patterns

def setup_logger(name='rsi_bot', log_file='bot.log', level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Get patterns to redact
    patterns = get_redacted_patterns()

    # Create formatter with redaction
    formatter = RedactingFormatter(patterns, '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Avoid adding handlers multiple times
    if not logger.handlers:
        fh = logging.FileHandler(log_file)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        logger.addHandler(ch)
        
    return logger
