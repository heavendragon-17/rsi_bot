import pandas as pd

class BacktestReporter:
    def __init__(self, exchange):
        self.exchange = exchange

    def generate_report(self):
        trades = self.exchange.trade_history
        if not trades:
            print("No trades executed.")
            return

        df = pd.DataFrame(trades)

        # Calculate PnL per trade cycle (Buy -> Sell)
        # Simple reconstruction for MVP:
        # PnL = Revenue - Cost.
        # But trades are separate rows.
        # We can calculate Total PnL = Sum(Sell Revenue) - Sum(Buy Cost)
        # (assuming 0 positions at end, or we mark-to-market remaining).

        total_buy_cost = df[df['side'] == 'BUY']['cost_or_revenue'].sum()
        total_sell_revenue = df[df['side'] == 'SELL']['cost_or_revenue'].sum()

        # Adjust for open positions (if any)
        # Not handled in simple calc, assumes closed loop or checks balance diff.

        final_balance = self.exchange.get_balance()
        initial_balance = 1000.0 # Should pass this in or store in exchange
        # Actually exchange.balance is reliable.

        profit = final_balance - initial_balance # Approximation if initial unknown, but we know it.
        # Better:
        # Win Rate calculation requires pairing buys and sells.

        buys = df[df['side'] == 'BUY'].reset_index(drop=True)
        sells = df[df['side'] == 'SELL'].reset_index(drop=True)

        wins = 0
        losses = 0

        # Pair them up (naive FIFO)
        min_len = min(len(buys), len(sells))
        for i in range(min_len):
            b = buys.iloc[i]
            s = sells.iloc[i]
            pnl = s['cost_or_revenue'] - b['cost_or_revenue']
            if pnl > 0: wins += 1
            else: losses += 1

        total_trades = min_len
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

        print("\n=== Backtest Summary ===")
        print(f"Total Trades (Round Trip): {total_trades}")
        print(f"Win Rate: {win_rate:.2f}% ({wins}W / {losses}L)")
        print(f"Final Balance: ${final_balance:.2f}")
        print("========================\n")

        # Save logs
        df.to_csv("backtest_logs.csv", index=False)
        print("Detailed logs saved to backtest_logs.csv")
