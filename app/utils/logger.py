import logging
import os

class RedactingFormatter(logging.Formatter):
    """
    Formatter that redacts sensitive information from log messages.
    Scans environment variables for keys containing 'KEY', 'SECRET', 'TOKEN', etc.
    and replaces their values with [REDACTED].
    """
    def __init__(self, fmt=None, datefmt=None, style='%'):
        super().__init__(fmt, datefmt, style)
        self.patterns = []

        # Scan environment variables for potential secrets
        sensitive_keywords = ['KEY', 'SECRET', 'TOKEN', 'PASSWORD', 'PWD', 'AUTH']

        for key, value in os.environ.items():
            if not value:
                continue

            # Check if key contains any sensitive keyword
            if any(keyword in key.upper() for keyword in sensitive_keywords):
                # Avoid redacting short common strings (e.g., '1', 'true')
                if len(value) > 4:
                    self.patterns.append(value)

    def format(self, record):
        # Format the message using the parent class
        original_msg = super().format(record)

        # Redact secrets
        redacted_msg = original_msg
        for pattern in self.patterns:
            if pattern in redacted_msg:
                redacted_msg = redacted_msg.replace(pattern, "[REDACTED]")

        return redacted_msg

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
