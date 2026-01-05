from .rsi_wma_retest import RsiWmaRetestStrategy

def load_strategy(config):
    # Future improvement: Load dynamically based on config name
    return RsiWmaRetestStrategy(config)
