import logging
import os

class RedactingFilter(logging.Filter):
    """
    Filter that scrubs sensitive environment variables from log messages.
    """
    def __init__(self):
        super().__init__()
        self.sensitive_keywords = ['KEY', 'SECRET', 'TOKEN', 'PASSWORD', 'PWD', 'AUTH']
        self.redactions = self._get_redactions()

    def _get_redactions(self):
        redactions = []
        for k, v in os.environ.items():
            if any(s in k.upper() for s in self.sensitive_keywords) and v:
                redactions.append(v)
        # Sort by length descending to handle overlapping secrets correctly
        return sorted(redactions, key=len, reverse=True)

    def filter(self, record):
        # logging.Filter.filter is meant to return True/False
        # But we can also modify the record in place.
        msg = record.getMessage()

        # Check if any secret is in the message
        # Optimization: only do replacement if we find a match
        modified = False
        for secret in self.redactions:
            if secret in msg:
                msg = msg.replace(secret, "***REDACTED***")
                modified = True

        if modified:
            record.msg = msg
            record.args = () # Clear args since we've baked them into msg

        return True

def setup_logger(name='rsi_bot', log_file='bot.log', level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Avoid adding handlers multiple times
    if not logger.handlers:
        # Initialize the security filter
        redactor = RedactingFilter()

        fh = logging.FileHandler(log_file)
        fh.setFormatter(formatter)
        fh.addFilter(redactor)
        logger.addHandler(fh)
        
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        ch.addFilter(redactor)
        logger.addHandler(ch)
        
    return logger
