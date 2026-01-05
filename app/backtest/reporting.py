import pandas as pd

class BacktestReporter:
    def __init__(self, portfolio):
        self.portfolio = portfolio

    def generate_report(self):
        trades = self.portfolio.trade_history
        if not trades:
            print("No trades executed.")
            return

        df = pd.DataFrame(trades)

        # Calculate Metrics
        total_trades = len(df[df['side'] == 'SELL'])
        wins = len(df[(df['side'] == 'SELL') & (df['pnl'] > 0)])
        losses = len(df[(df['side'] == 'SELL') & (df['pnl'] <= 0)])
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        total_pnl = df[df['side'] == 'SELL']['pnl'].sum()
        final_balance = self.portfolio.balance
        return_pct = ((final_balance - self.portfolio.initial_balance) / self.portfolio.initial_balance) * 100

        print("\n=== Backtest Summary ===")
        print(f"Total Trades: {total_trades}")
        print(f"Win Rate: {win_rate:.2f}% ({wins}W / {losses}L)")
        print(f"Total PnL: ${total_pnl:.2f}")
        print(f"Final Balance: ${final_balance:.2f} ({return_pct:.2f}%)")
        print("========================\n")

        # Save logs
        df.to_csv("backtest_logs.csv", index=False)
        print("Detailed logs saved to backtest_logs.csv")
