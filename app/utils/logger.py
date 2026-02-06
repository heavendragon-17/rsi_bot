import sys
import logging

def setup_logger(name='rsi_bot', log_file='bot.log', level=logging.INFO, stream=sys.stdout):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False # Prevent propagation to root logger (avoid duplicate logs)
    
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Avoid adding handlers multiple times
    if not logger.handlers:
        fh = logging.FileHandler(log_file)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        
        ch = logging.StreamHandler(stream)
        ch.setFormatter(formatter)
        logger.addHandler(ch)
        
    return logger
