import logging
import os

class RedactingFilter(logging.Filter):
    """
    Filter that redacts sensitive information from log messages.
    Modifies the record in-place so all handlers receive redacted messages.
    """
    SENSITIVE_KEYWORDS = ['KEY', 'SECRET', 'TOKEN', 'PASSWORD', 'PWD', 'AUTH']

    def filter(self, record):
        # Handle cases where arguments are passed separately (e.g. logger.info("Msg %s", arg))
        if record.args:
            try:
                record.msg = record.getMessage()
                record.args = ()
            except Exception:
                # If formatting fails, fallback to original behavior but don't crash
                pass

        if not isinstance(record.msg, str):
            return True

        for key, value in os.environ.items():
            if not value or len(value) < 3:
                continue

            if any(keyword in key.upper() for keyword in self.SENSITIVE_KEYWORDS):
                if value in record.msg:
                    record.msg = record.msg.replace(value, '[REDACTED]')

        return True

def setup_logger(name='rsi_bot', log_file='bot.log', level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Add RedactingFilter if not already present
    # We check by class name to avoid duplicates
    if not any(isinstance(f, RedactingFilter) for f in logger.filters):
        logger.addFilter(RedactingFilter())

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Avoid adding handlers multiple times
    if not logger.handlers:
        fh = logging.FileHandler(log_file)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        logger.addHandler(ch)
        
    return logger
