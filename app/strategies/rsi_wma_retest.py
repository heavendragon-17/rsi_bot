from .base import BaseStrategy
from app.utils.indicators import Indicators
from app.core.events import SignalEvent

class RsiWmaRetestStrategy(BaseStrategy):
    def analyze(self, symbol, df):
        if df is None or len(df) < 50:
            return None
        
        # Get Config Parameters (with defaults)
        rsi_period = self.config.get('strategy', {}).get('rsi_period', 14)
        rsi_buy = self.config.get('strategy', {}).get('rsi_buy', 30)
        rsi_sell = self.config.get('strategy', {}).get('rsi_sell', 80)

        # Calculate Indicators
        rsi = Indicators.calculate_rsi(df['close'], length=rsi_period)
        # wma = Indicators.calculate_wma(df['close']) # Not used in simple logic yet
        
        last_rsi = rsi.iloc[-1]
        
        # Entry Logic (Buy)
        if last_rsi < rsi_buy:
            return SignalEvent(
                symbol=symbol, 
                signal_type='BUY', 
                price=df.iloc[-1]['close'], 
                timestamp=df.index[-1], 
                reason=f"RSI OVERSOLD ({last_rsi:.2f} < {rsi_buy})"
            )

        # Exit Logic (Sell)
        if last_rsi > rsi_sell:
            return SignalEvent(
                symbol=symbol,
                signal_type='SELL',
                price=df.iloc[-1]['close'],
                timestamp=df.index[-1],
                reason=f"RSI OVERBOUGHT ({last_rsi:.2f} > {rsi_sell})"
            )
            
        return None
