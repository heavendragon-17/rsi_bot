import logging
import os

class RedactingFormatter(logging.Formatter):
    """
    Formatter that removes sensitive information from log messages.
    """
    def __init__(self, fmt=None, datefmt=None, style='%', validate=True):
        # Handle 3.10+ validate arg or ignore it if older python (not strictly needed for just fmt)
        # But safest is to just match signature or use *args, **kwargs
        if 'validate' in logging.Formatter.__init__.__code__.co_varnames:
             super().__init__(fmt, datefmt, style, validate)
        else:
             super().__init__(fmt, datefmt, style)

        self.sensitive_values = []
        # Pre-calculate sensitive values to avoid iterating os.environ on every log
        # and to ensure thread safety (avoid RuntimeError during iteration)
        for key, value in list(os.environ.items()):
            # Skip empty values or very short values to avoid false positives
            if not value or len(value) < 5:
                continue

            if any(s in key.upper() for s in ['KEY', 'SECRET', 'TOKEN', 'PASSWORD', 'PWD', 'AUTH']):
                self.sensitive_values.append(value)

    def format(self, record):
        msg = super().format(record)
        for value in self.sensitive_values:
            if value in msg:
                msg = msg.replace(value, '[REDACTED]')
        return msg

def setup_logger(name='rsi_bot', log_file='bot.log', level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
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
