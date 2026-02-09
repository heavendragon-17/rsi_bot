from datetime import datetime
from decimal import Decimal
import pandas as pd
import numpy as np
from app.core.events import SignalEvent

class BacktestEngine:
    def __init__(self, data_path, strategy_class, config):
        self.data_path = data_path
        self.strategy_class = strategy_class
        self.config = config
        self.symbol = config.get("symbol", "UNKNOWN")
        self.timeframe = config.get("timeframe", "UNKNOWN")
        self.initial_balance = Decimal(str(config.get("backtest", {}).get("initial_balance", 10000)))
        
        self.trades = []
        self.equity_curve = []
        self.drawdown_curve = []
        self.results = {}
        self.start_date = None
        self.end_date = None

    def load_data(self):
        """Load and preprocess data."""
        df = pd.read_csv(self.data_path)
        # Ensure correct types
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = df[col].astype(float)
        
        # Sort and reset index
        df = df.sort_values('timestamp').reset_index(drop=True)
        return df

    def run(self):
        """Execute the backtest (Event-Driven)."""
        df = self.load_data()
        if not df.empty:
            self.start_date = df['timestamp'].iloc[0].to_pydatetime()
            self.end_date = df['timestamp'].iloc[-1].to_pydatetime()
            
        strategy = self.strategy_class(self.config)
        
        balance = self.initial_balance
        position = None
        entry_price = Decimal('0')
        entry_time = None
        quantity = Decimal('0')
        trade_meta = {}
        
        # Start from a sufficient index to allow indicators to warm up
        # Strategy checks for 220 rows
        start_index = 250 
        if len(df) <= start_index:
             # Just run on what we have, strategy handles the check
             start_index = 10 

        for i in range(start_index, len(df) + 1):
            # Window of data up to current point
            window = df.iloc[:i].copy() # Copy to avoid SettingWithCopy warnings
            
            # Current candle (last one in window)
            current_row = window.iloc[-1]
            timestamp = current_row['timestamp']
            current_price = Decimal(str(current_row['close']))
            
            # Analyze
            signal = strategy.analyze(self.symbol, window)
            
            # Process Signal
            if signal:
                # ENTRY
                if signal.signal_type == "BUY" and not position:
                    position = 'LONG'
                    entry_price = signal.price
                    entry_time = timestamp
                    quantity = balance / entry_price
                    trade_meta = {
                        "tp1": signal.tp1_price,
                        "tp2": signal.tp2_price,
                        "tp3": signal.tp3_price,
                        "sl": signal.sl_price
                    }

                # EXIT
                elif signal.signal_type == "SELL" and position == 'LONG':
                    exit_price = signal.price
                    pnl = (exit_price - entry_price) * quantity
                    balance += pnl
                    
                    self.trades.append({
                        "symbol": self.symbol,
                        "side": position,
                        "entry_time": entry_time,
                        "exit_time": timestamp,
                        "entry_price": float(entry_price),
                        "exit_price": float(exit_price),
                        "quantity": float(quantity),
                        "pnl": float(pnl),
                        "pnl_pct": float((pnl / (entry_price * quantity)) * 100),
                        "exit_reason": signal.reason,
                        "hold_time_hours": (timestamp - entry_time).total_seconds() / 3600
                    })
                    
                    position = None
                    quantity = Decimal('0')
            
            # Update Equity Curve
            # If in position, mark-to-market
            current_equity = balance
            if position:
                current_pnl = (current_price - entry_price) * quantity
                current_equity += current_pnl
            
            self.equity_curve.append({
                "timestamp": timestamp.isoformat(),
                "equity": float(current_equity)
            })

        self.calculate_metrics()

    def calculate_metrics(self):
        """Calculate performance metrics."""
        if not self.trades:
            self.results = {
                "net_profit": 0,
                "net_profit_pct": 0,
                "win_rate": 0,
                "profit_factor": 0,
                "sharpe_ratio": 0,
                "max_drawdown_pct": 0,
                "total_trades": 0
            }
            return self.results

        df_trades = pd.DataFrame(self.trades)
        net_profit = df_trades['pnl'].sum()
        wins = df_trades[df_trades['pnl'] > 0]
        losses = df_trades[df_trades['pnl'] <= 0]
        
        win_rate = len(wins) / len(df_trades)
        profit_factor = abs(wins['pnl'].sum() / losses['pnl'].sum()) if len(losses) > 0 else float('inf')
        
        # Drawdown calculation
        equity_vals = [x['equity'] for x in self.equity_curve]
        if not equity_vals:
             max_drawdown = 0
        else:
            equity_series = pd.Series(equity_vals)
            rolling_max = equity_series.cummax()
            drawdown = (equity_series - rolling_max) / rolling_max
            max_drawdown = drawdown.min() * 100 # percentage

        self.results = {
            "net_profit": float(net_profit),
            "net_profit_pct": float((net_profit / self.initial_balance) * 100),
            "win_rate": float(win_rate),
            "profit_factor": float(profit_factor),
            "sharpe_ratio": 0.0,
            "max_drawdown_pct": float(max_drawdown),
            "total_trades": len(df_trades)
        }
        return self.results
