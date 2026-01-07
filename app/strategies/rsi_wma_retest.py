from .base import BaseStrategy
from app.utils.indicators import Indicators
from app.core.events import SignalEvent

class RsiWmaRetestStrategy(BaseStrategy):
    def __init__(self, config):
        super().__init__(config)
        
        # Get Config Parameters (with defaults)
        rsi_period = self.config.get('strategy', {}).get('rsi_period', 14)
        rsi_ema_length = self.config.get('strategy', {}).get('rsi_ema_length', 9)
        rsi_wma_length = self.config.get('strategy', {}).get('rsi_wma_length', 45)
        price_ema_fast = self.config.get('strategy', {}).get('price_ema_fast', 21)
        price_ema_slow = self.config.get('strategy', {}).get('price_ema_slow', 200)
        
        # Instantiate Indicators class
        self.indicators = Indicators(
            rsi_length=rsi_period,
            rsi_ema_length=rsi_ema_length,
            rsi_wma_length=rsi_wma_length,
            price_ema_fast=price_ema_fast,
            price_ema_slow=price_ema_slow
        )
        
        # Store thresholds
        self.rsi_buy = self.config.get('strategy', {}).get('rsi_buy', 30)
        self.rsi_sell = self.config.get('strategy', {}).get('rsi_sell', 80)

    def analyze(self, symbol, df):
        if df is None or len(df) < 50:
            return None
        
        # Compute all indicators using the class
        df_with_indicators = self.indicators.compute(df, symbol=symbol)
        
        # Get last row values
        last = Indicators.last(df_with_indicators)
        last_rsi = last.get('rsi')
        
        if last_rsi is None:
            return None
        
        # Entry Logic (Buy)
        if last_rsi < self.rsi_buy:
            return SignalEvent(
                symbol=symbol, 
                signal_type='BUY', 
                price=last.get('close'),
                timestamp=df.index[-1], 
                reason=f"RSI OVERSOLD ({last_rsi:.2f} < {self.rsi_buy})"
            )

        # Exit Logic (Sell)
        if last_rsi > self.rsi_sell:
            return SignalEvent(
                symbol=symbol,
                signal_type='SELL',
                price=last.get('close'),
                timestamp=df.index[-1],
                reason=f"RSI OVERBOUGHT ({last_rsi:.2f} > {self.rsi_sell})"
            )
            
        return None
