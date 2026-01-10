"""
Backtest Reporter
==================
Generates backtest performance reports.
"""
import pandas as pd
from decimal import Decimal


class BacktestReporter:
    """Generate performance reports from backtest results."""
    
    def __init__(self, exchange, initial_balance: float = 1000.0):
        self.exchange = exchange
        self.initial_balance = Decimal(str(initial_balance))

    def generate_report(self) -> None:
        """Generate and print backtest summary report."""
        trades = self.exchange.trade_history
        if not trades:
            print("No trades executed.")
            return

        df = pd.DataFrame(trades)
        print(df.head()) # Debug: show first few trades

        # Calculate metrics
        final_balance = self.exchange.get_balance()
        profit = float(final_balance) - float(self.initial_balance)
        profit_pct = (profit / float(self.initial_balance)) * 100

        # Pair trades for win/loss calculation
        buys = df[df['side'] == 'BUY'].reset_index(drop=True)
        sells = df[df['side'] == 'SELL'].reset_index(drop=True)

        wins = 0
        losses = 0

        min_len = min(len(buys), len(sells))
        for i in range(min_len):
            b = buys.iloc[i]
            s = sells.iloc[i]
            pnl = s['cost_or_revenue'] - b['cost_or_revenue']
            if pnl > 0:
                wins += 1
            else:
                losses += 1

        total_trades = min_len
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

        # Report
        print("\n" + "=" * 40)
        print("         BACKTEST SUMMARY")
        print("=" * 40)
        print(f"Initial Balance:     ${float(self.initial_balance):.2f}")
        print(f"Final Balance:       ${float(final_balance):.2f}")
        print(f"Profit/Loss:         ${profit:.2f} ({profit_pct:+.2f}%)")
        print("-" * 40)
        print(f"Total Trades:        {len(trades)}")
        print(f"Round Trips:         {total_trades}")
        print(f"Win Rate:            {win_rate:.1f}% ({wins}W / {losses}L)")
        print(f"Open Positions:      {len(self.exchange.positions)}")
        print("=" * 40 + "\n")

        # Save logs
        df.to_csv("backtest_logs.csv", index=False)
        print("Detailed logs saved to backtest_logs.csv")
