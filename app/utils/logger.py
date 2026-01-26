import logging
import os
import re

class RedactingFormatter(logging.Formatter):
    """
    Formatter that scans os.environ for sensitive keys (containing KEY, SECRET, TOKEN, etc.)
    and redacts their values from the log output.
    """
    def __init__(self, fmt=None, datefmt=None, style='%'):
        super().__init__(fmt, datefmt, style)
        self.patterns = []
        sensitive_keywords = ['KEY', 'SECRET', 'TOKEN', 'PASSWORD', 'PWD', 'AUTH']

        for key, value in os.environ.items():
            if any(s in key.upper() for s in sensitive_keywords):
                # Avoid redacting empty strings or very short values that might be common words
                if value and len(value) >= 5:
                    self.patterns.append(re.escape(value))

        # Sort patterns by length descending to replace longest matches first
        self.patterns.sort(key=len, reverse=True)

        if self.patterns:
            self.regex = re.compile('|'.join(self.patterns))
        else:
            self.regex = None

    def format(self, record):
        original_msg = super().format(record)
        if self.regex:
            return self.regex.sub('[REDACTED]', original_msg)
        return original_msg

def setup_logger(name='rsi_bot', log_file='bot.log', level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    formatter = RedactingFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Avoid adding handlers multiple times
    if not logger.handlers:
        if log_file:
            fh = logging.FileHandler(log_file)
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        logger.addHandler(ch)
        
    return logger
