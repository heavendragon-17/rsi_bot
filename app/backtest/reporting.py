"""
Backtest Reporter (Enhanced)
============================
Generates comprehensive backtest performance reports with:
- Console output with key metrics
- HTML report with pie chart for TP/SL distribution
- CSV export with per-trade details
"""
import pandas as pd
import numpy as np
from decimal import Decimal
from datetime import datetime
import os


class BacktestReporter:
    """Generate performance reports from backtest results."""
    
    def __init__(self, exchange, config: dict, initial_balance: float = 1000.0, symbol: str = "N/A", timeframe: str = "N/A", strategy_name: str = "N/A"):
        self.exchange = exchange
        # Get settings
        initial_balance = config.get('backtest', {}).get('initial_balance', initial_balance)
        try:
            self.initial_balance = Decimal(str(initial_balance))
        except Exception as e:
            print(f"DEBUG ERROR: initial_balance value: {initial_balance!r}, type: {type(initial_balance)}")
            raise e
        self.symbol = symbol
        self.timeframe = timeframe
        self.strategy_name = strategy_name
        self.leverage = config.get('risk', {}).get('leverage', 1)

    def _build_round_trips(self, trades_df: pd.DataFrame) -> pd.DataFrame:
        """
        Pair BUY entries with subsequent SELL exits to form round-trips.
        Each round-trip may have multiple partial sells (TP1, TP2, TP3, SL).
        Returns a DataFrame with one row per complete trade cycle.
        """
        if trades_df.empty:
            return pd.DataFrame()
        
        round_trips = []
        current_entry = None
        partial_exits = []
        total_pnl = 0.0
        total_exit_amount = 0.0
        
        for _, trade in trades_df.iterrows():
            if trade['side'] == 'BUY':
                # If we had a previous incomplete entry, finalize it
                if current_entry is not None and partial_exits:
                    round_trips.append(self._create_round_trip(
                        current_entry, partial_exits, total_pnl, total_exit_amount
                    ))
                # Start new entry
                current_entry = trade
                partial_exits = []
                total_pnl = 0.0
                total_exit_amount = 0.0
            elif trade['side'] == 'SELL' and current_entry is not None:
                partial_exits.append(trade)
                if trade['pnl'] is not None:
                    total_pnl += trade['pnl']
                total_exit_amount += trade['amount']
        
        # Finalize last trade if exits exist
        if current_entry is not None and partial_exits:
            round_trips.append(self._create_round_trip(
                current_entry, partial_exits, total_pnl, total_exit_amount
            ))
        
        return pd.DataFrame(round_trips) if round_trips else pd.DataFrame()

    def _create_round_trip(self, entry, exits, total_pnl, total_exit_amount) -> dict:
        """Create a round-trip record from entry and exit trades."""
        first_exit = exits[0]
        last_exit = exits[-1]
        
        # Helper to get exit_reason from info dict (CCXT standard)
        def get_exit_reason(e):
            return e.get('info', {}).get('exit_reason') or ''
        
        # Determine final exit reason (highest TP level reached or SL)
        exit_reasons = [get_exit_reason(e) for e in exits if get_exit_reason(e)]
        final_exit_reason = self._get_highest_exit_reason(exit_reasons)
        
        # Calculate hold duration
        hold_duration_seconds = None
        if entry.get('time') is not None and last_exit.get('time') is not None:
            try:
                entry_time = pd.to_datetime(entry['time'])
                exit_time = pd.to_datetime(last_exit['time'])
                hold_duration_seconds = (exit_time - entry_time).total_seconds()
            except Exception:
                pass
        
        # Calculate average exit price (volume-weighted)
        total_revenue = sum(e.get('price', 0) * e.get('amount', 0) for e in exits)
        avg_exit_price = total_revenue / total_exit_amount if total_exit_amount > 0 else 0
        
        # Get margin/notional (for futures compatibility)
        # Try margin first (futures), fall back to cost_or_revenue (spot), then notional
        entry_margin = entry.get('margin', entry.get('cost_or_revenue', entry.get('notional', 1)))
        entry_notional = entry.get('notional', entry.get('cost_or_revenue', entry_margin))
        leverage = entry.get('leverage', 1)
        
        # PnL % based on margin (capital at risk)
        pnl_pct = (total_pnl / entry_margin) * 100 if entry_margin and entry_margin > 0 else 0
        
        return {
            'entry_time': entry.get('time'),
            'exit_time': last_exit.get('time'),
            'symbol': entry.get('symbol'),
            'entry_price': entry.get('price'),
            'exit_price': last_exit.get('price'),
            'avg_exit_price': float(avg_exit_price),
            'amount': entry.get('amount'),
            'exit_amount': total_exit_amount,
            'margin': entry_margin,
            'notional': entry_notional,
            'leverage': leverage,
            'pnl': total_pnl,
            'pnl_pct': pnl_pct,
            'hold_duration_seconds': hold_duration_seconds,
            'hold_duration_hours': hold_duration_seconds / 3600 if hold_duration_seconds else None,
            'exit_reason': final_exit_reason,
            'num_partial_exits': len(exits),
            'hit_tp1': any(get_exit_reason(e) == 'TP1' for e in exits),
            'hit_tp2': any(get_exit_reason(e) == 'TP2' for e in exits),
            'hit_tp3': any(get_exit_reason(e) == 'TP3' for e in exits),
            'hit_sl': any(get_exit_reason(e) in ('SL', 'STOP_LOSS') for e in exits),
        }

    def _get_highest_exit_reason(self, exit_reasons: list) -> str:
        """Get the highest TP level or SL from exit reasons."""
        if any(r in ('SL', 'STOP_LOSS') for r in exit_reasons):
            # Check if any TP was hit before SL
            has_tp = any(r and r.startswith('TP') for r in exit_reasons)
            if has_tp:
                # Return highest TP level reached
                for tp in ['TP3', 'TP2', 'TP1']:
                    if tp in exit_reasons:
                        return f"{tp}+SL"
            return 'SL'
        
        for tp in ['TP3', 'TP2', 'TP1']:
            if tp in exit_reasons:
                return tp
        
        return exit_reasons[0] if exit_reasons else 'UNKNOWN'

    def _calculate_metrics(self, round_trips: pd.DataFrame) -> dict:
        """Calculate comprehensive trading metrics."""
        if round_trips.empty:
            return {}
        
        # Basic counts
        total_trades = len(round_trips)
        
        # Win/Loss based on PnL (profit = win)
        wins = round_trips[round_trips['pnl'] > 0]
        losses = round_trips[round_trips['pnl'] <= 0]
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0
        
        # PnL stats
        total_pnl = round_trips['pnl'].sum()
        avg_pnl = round_trips['pnl'].mean()
        avg_win = wins['pnl'].mean() if len(wins) > 0 else 0
        avg_loss = losses['pnl'].mean() if len(losses) > 0 else 0
        largest_win = round_trips['pnl'].max()
        largest_loss = round_trips['pnl'].min()
        
        # Profit Factor
        gross_profit = wins['pnl'].sum() if len(wins) > 0 else 0
        gross_loss = abs(losses['pnl'].sum()) if len(losses) > 0 else 0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')
        
        # Risk/Reward Ratio
        risk_reward = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
        
        # Expectancy
        expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss)
        
        # Hold duration stats
        hold_hours = round_trips['hold_duration_hours'].dropna()
        avg_hold_hours = hold_hours.mean() if len(hold_hours) > 0 else 0
        
        # TP/SL Distribution
        tp1_count = round_trips['hit_tp1'].sum()
        tp2_count = round_trips['hit_tp2'].sum()
        tp3_count = round_trips['hit_tp3'].sum()
        sl_count = round_trips['hit_sl'].sum()
        
        # For pie chart: final exit reason counts
        exit_reason_counts = round_trips['exit_reason'].value_counts().to_dict()
        
        # Consecutive wins/losses
        pnl_signs = (round_trips['pnl'] > 0).astype(int)
        max_consec_wins = self._max_consecutive(pnl_signs, 1)
        max_consec_losses = self._max_consecutive(pnl_signs, 0)
        
        return {
            'total_trades': total_trades,
            'win_count': win_count,
            'loss_count': loss_count,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'largest_win': largest_win,
            'largest_loss': largest_loss,
            'profit_factor': profit_factor,
            'risk_reward': risk_reward,
            'expectancy': expectancy,
            'avg_hold_hours': avg_hold_hours,
            'tp1_count': tp1_count,
            'tp2_count': tp2_count,
            'tp3_count': tp3_count,
            'sl_count': sl_count,
            'exit_reason_counts': exit_reason_counts,
            'max_consec_wins': max_consec_wins,
            'max_consec_losses': max_consec_losses,
            'gross_profit': gross_profit,
            'gross_loss': gross_loss,
        }

    def _max_consecutive(self, series, value) -> int:
        """Calculate max consecutive occurrences of a value."""
        max_count = 0
        current = 0
        for v in series:
            if v == value:
                current += 1
                max_count = max(max_count, current)
            else:
                current = 0
        return max_count

    def _calculate_drawdown(self, round_trips: pd.DataFrame) -> dict:
        """Calculate maximum drawdown from round-trip equity curve."""
        if round_trips.empty or 'pnl' not in round_trips.columns:
            return {
                'max_drawdown_pct': 0, 'max_drawdown_value': 0, 
                'equity_curve': [float(self.initial_balance)],
                'max_dd_duration': 0, 'avg_drawdown_pct': 0
            }
        
        # Build equity curve from cumulative PnL of closed trades
        initial = float(self.initial_balance)
        cumulative_pnl = round_trips['pnl'].cumsum().tolist()
        equity_curve = [initial] + [initial + pnl for pnl in cumulative_pnl]
        
        # Calculate drawdown metrics from equity curve
        peak = equity_curve[0]
        max_dd = 0
        max_dd_value = 0
        current_dd_start = 0
        max_dd_duration = 0
        current_dd_duration = 0
        all_drawdowns = []
        
        for i, val in enumerate(equity_curve):
            if val > peak:
                peak = val
                # End of drawdown period
                if current_dd_duration > 0:
                    max_dd_duration = max(max_dd_duration, current_dd_duration)
                current_dd_duration = 0
            else:
                # In drawdown
                dd = (peak - val) / peak if peak > 0 else 0
                if dd > 0:
                    all_drawdowns.append(dd * 100)
                    current_dd_duration += 1
                if dd > max_dd:
                    max_dd = dd
                    max_dd_value = peak - val
        
        # Final duration check
        if current_dd_duration > 0:
            max_dd_duration = max(max_dd_duration, current_dd_duration)
        
        # Average drawdown (when in drawdown)
        avg_drawdown = sum(all_drawdowns) / len(all_drawdowns) if all_drawdowns else 0
        
        return {
            'max_drawdown_pct': max_dd * 100,
            'max_drawdown_value': max_dd_value,
            'equity_curve': equity_curve,
            'max_dd_duration': max_dd_duration,
            'avg_drawdown_pct': avg_drawdown
        }

    def _calculate_risk_metrics(self, round_trips: pd.DataFrame, drawdown: dict) -> dict:
        """Calculate risk-adjusted performance metrics."""
        if round_trips.empty:
            return {
                'sharpe_ratio': 0,
                'sortino_ratio': 0,
                'calmar_ratio': 0,
                'volatility': 0,
                'var_95': 0
            }
        
        # Get returns from round trips (as percentages)
        returns = round_trips['pnl_pct'].values / 100  # Convert to decimal
        
        if len(returns) < 2:
            return {
                'sharpe_ratio': 0,
                'sortino_ratio': 0,
                'calmar_ratio': 0,
                'volatility': 0,
                'var_95': 0
            }
        
        # Risk-free rate (annualized, assume 0 for crypto)
        risk_free_rate = 0
        
        # Mean return
        mean_return = np.mean(returns)
        
        # Standard deviation of returns (Volatility)
        std_return = np.std(returns, ddof=1) if len(returns) > 1 else 0
        volatility = std_return * 100  # As percentage
        
        # Sharpe Ratio = (Mean Return - Risk Free Rate) / Std Dev
        sharpe_ratio = (mean_return - risk_free_rate) / std_return if std_return > 0 else 0
        
        # Sortino Ratio = (Mean Return - Risk Free Rate) / Downside Deviation
        negative_returns = returns[returns < 0]
        downside_std = np.std(negative_returns, ddof=1) if len(negative_returns) > 1 else 0
        sortino_ratio = (mean_return - risk_free_rate) / downside_std if downside_std > 0 else 0
        
        # Value at Risk (VaR) - 95% confidence
        # The 5th percentile of returns
        var_95 = np.percentile(returns, 5) * 100 if len(returns) >= 5 else min(returns) * 100
        
        # Calmar Ratio = Total Return / Max Drawdown
        # Use realized PnL for consistency with equity curve
        realized_pnl = round_trips['pnl'].sum() if not round_trips.empty else 0.0
        total_return = (realized_pnl / float(self.initial_balance)) * 100
        max_dd = drawdown.get('max_drawdown_pct', 0)
        calmar_ratio = total_return / max_dd if max_dd > 0 else 0
        
        return {
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'calmar_ratio': calmar_ratio,
            'volatility': volatility,
            'var_95': var_95
        }

    def _format_duration(self, hours: float) -> str:
        """Format hours into human-readable duration."""
        if hours is None or np.isnan(hours):
            return "N/A"
        if hours < 1:
            return f"{hours * 60:.0f}m"
        if hours < 24:
            return f"{hours:.1f}h"
        days = hours / 24
        return f"{days:.1f}d"

    def _calculate_monthly_returns(self, round_trips: pd.DataFrame) -> dict:
        """Calculate monthly returns from round trips."""
        if round_trips.empty or 'exit_time' not in round_trips.columns:
            return {}
        
        # Convert exit_time to datetime if needed
        df = round_trips.copy()
        df['exit_time'] = pd.to_datetime(df['exit_time'])
        df['month'] = df['exit_time'].dt.to_period('M')
        
        # Group by month and sum PnL
        monthly = df.groupby('month').agg({
            'pnl': 'sum',
            'exit_time': 'count'  # Count trades
        }).rename(columns={'exit_time': 'trades'})
        
        # Calculate monthly return percentage (relative to initial balance)
        initial = float(self.initial_balance)
        monthly['pnl_pct'] = (monthly['pnl'] / initial) * 100
        
        # Convert to dict with string keys for JSON serialization
        result = {}
        for period, row in monthly.iterrows():
            result[str(period)] = {
                'pnl': float(row['pnl']),
                'pnl_pct': float(row['pnl_pct']),
                'trades': int(row['trades'])
            }
        return result

    def generate_report(self, output_dir: str = ".") -> str | None:
        """Generate and output backtest summary report."""
        trades = self.exchange.trade_history
        if not trades:
            print("No trades executed.")
            return

        df = pd.DataFrame(trades)
        
        # Build round trips
        round_trips = self._build_round_trips(df)
        
        # Calculate metrics
        metrics = self._calculate_metrics(round_trips)
        drawdown = self._calculate_drawdown(round_trips)
        risk_metrics = self._calculate_risk_metrics(round_trips, drawdown)
        monthly_returns = self._calculate_monthly_returns(round_trips)
        
        # Final balance
        bal_data = self.exchange.fetch_balance()
        final_balance = Decimal(str(bal_data.get("total", {}).get("USDT", 0)))
        # Use sum of round_trips PnL for consistency with equity curve
        realized_pnl = float(round_trips['pnl'].sum()) if not round_trips.empty else 0.0
        profit = realized_pnl
        profit_pct = (profit / float(self.initial_balance)) * 100

        # Console Report
        self._print_console_report(metrics, drawdown, risk_metrics, final_balance, profit, profit_pct, round_trips)
        
        # HTML Report
        report_path = self._generate_html_report(metrics, drawdown, risk_metrics, monthly_returns, final_balance, profit, profit_pct, round_trips, output_dir=output_dir)
        
        # CSV Exports
        self._export_csv(df, round_trips, output_dir=output_dir)
        
        return report_path

    def _print_console_report(self, metrics: dict, drawdown: dict, risk_metrics: dict,
                              final_balance, profit, profit_pct, round_trips: pd.DataFrame) -> None:
        """Print formatted console report."""
        print("\n" + "=" * 50)
        print(f"         BACKTEST: {self.symbol} ({self.timeframe})")
        print("=" * 50)
        
        # Performance
        print("\n[PERFORMANCE]")
        print("-" * 50)
        print(f"  Initial Balance:     ${float(self.initial_balance):,.2f}")
        print(f"  Final Balance:       ${float(final_balance):,.2f}")
        print(f"  Net Profit/Loss:     ${profit:+,.2f} ({profit_pct:+.2f}%)")
        print(f"  Max Drawdown:        {drawdown.get('max_drawdown_pct', 0):.2f}%")
        print(f"  Avg Drawdown:        {drawdown.get('avg_drawdown_pct', 0):.2f}%")
        print(f"  Max DD Duration:     {drawdown.get('max_dd_duration', 0)} trades")
        
        if not metrics:
            print("\n  No completed trades to analyze.")
            print("=" * 50 + "\n")
            return
        
        # Trade Statistics
        print("\n[TRADE STATISTICS]")
        print("-" * 50)
        print(f"  Total Round-Trips:   {metrics['total_trades']}")
        print(f"  Win Rate:            {metrics['win_rate']:.1f}% ({metrics['win_count']}W / {metrics['loss_count']}L)")
        print(f"  Profit Factor:       {metrics['profit_factor']:.2f}" if metrics['profit_factor'] != float('inf') else "  Profit Factor:       INF")
        print(f"  Expectancy:          ${metrics['expectancy']:.2f}")
        
        # Risk-Adjusted Metrics
        print("\n[RISK-ADJUSTED METRICS]")
        print("-" * 50)
        print(f"  Sharpe Ratio:        {risk_metrics.get('sharpe_ratio', 0):.2f}")
        print(f"  Sortino Ratio:       {risk_metrics.get('sortino_ratio', 0):.2f}")
        print(f"  Calmar Ratio:        {risk_metrics.get('calmar_ratio', 0):.2f}")
        print(f"  Volatility:          {risk_metrics.get('volatility', 0):.2f}%")
        print(f"  VaR (95%):           {risk_metrics.get('var_95', 0):.2f}%")
        
        # PnL Details
        print("\n[PNL DETAILS]")
        print("-" * 50)
        print(f"  Average Win:         ${metrics['avg_win']:.2f}")
        print(f"  Average Loss:        ${metrics['avg_loss']:.2f}")
        print(f"  Largest Win:         ${metrics['largest_win']:.2f}")
        print(f"  Largest Loss:        ${metrics['largest_loss']:.2f}")
        print(f"  Risk/Reward:         {metrics['risk_reward']:.2f}" if metrics['risk_reward'] != float('inf') else "  Risk/Reward:         INF")
        
        # Streaks
        print("\n[STREAKS]")
        print("-" * 50)
        print(f"  Max Consecutive Wins:   {metrics['max_consec_wins']}")
        print(f"  Max Consecutive Losses: {metrics['max_consec_losses']}")
        
        # Hold Duration
        print("\n[HOLD DURATION]")
        print("-" * 50)
        print(f"  Average Hold Time:   {self._format_duration(metrics['avg_hold_hours'])}")
        
        # Exit Distribution
        print("\n[EXIT DISTRIBUTION]")
        print("-" * 50)
        total = metrics['total_trades']
        print(f"  TP1 Reached:         {metrics['tp1_count']} ({metrics['tp1_count']/total*100:.1f}%)")
        print(f"  TP2 Reached:         {metrics['tp2_count']} ({metrics['tp2_count']/total*100:.1f}%)")
        print(f"  TP3 Reached:         {metrics['tp3_count']} ({metrics['tp3_count']/total*100:.1f}%)")
        print(f"  SL Hit:              {metrics['sl_count']} ({metrics['sl_count']/total*100:.1f}%)")
        
        print("\n" + "=" * 50 + "\n")

    def _generate_html_report(self, metrics: dict, drawdown: dict, risk_metrics: dict,
                              monthly_returns: dict, final_balance, profit, profit_pct, round_trips: pd.DataFrame, return_only: bool = False, output_dir: str = ".") -> str | None:
        """Generate HTML report with charts."""
        safe_symbol = self.symbol.replace('/', '')
        
        # Pre-compute values that may have infinity
        profit_factor_display = f"{metrics['profit_factor']:.2f}" if metrics and metrics['profit_factor'] != float('inf') else 'INF'
        risk_reward_display = f"{metrics['risk_reward']:.2f}" if metrics and metrics['risk_reward'] != float('inf') else 'INF'
        
        # Prepare exit distribution data for pie chart
        exit_data = metrics.get('exit_reason_counts', {}) if metrics else {}
        labels = list(exit_data.keys()) if exit_data else ['No Trades']
        values = list(exit_data.values()) if exit_data else [1]
        
        # Color mapping for exit reasons - more contrasting colors
        colors = {
            'TP1': '#22C55E',      # Bright Green
            'TP2': '#3B82F6',      # Bright Blue
            'TP3': '#8B5CF6',      # Purple
            'FULL_TP': '#10B981',  # Emerald (Full TP hit)
            'SL': '#EF4444',       # Bright Red
            'STOP_LOSS': '#EF4444',
            'BREAKEVEN': '#F59E0B', # Amber (Moved SL triggered)
            'MANUAL': '#6B7280',   # Gray
            'EOD': '#6B7280',      # End of Data
            'CLOSE_BY_CANDLE': '#F59E0B',
            'TP1+SL': '#F59E0B',   # Amber/Orange
            'TP2+SL': '#3B82F6',   # Cyan
            'TP3+SL': '#EC4899',   # Pink
            'UNKNOWN': '#64748B',  # Slate
            'No Trades': '#9CA3AF',
        }
        pie_colors = [colors.get(l, '#64748B') for l in labels]
        
        # Build trades table HTML
        trades_table_html = ""
        if not round_trips.empty:
            trades_table_html = """
            <table class="trades-table">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Entry Time</th>
                        <th>Exit Time</th>
                        <th>Entry $</th>
                        <th>Exit $</th>
                        <th>Avg Exit $</th>
                        <th>PnL</th>
                        <th>PnL %</th>
                        <th>Hold Time</th>
                        <th>Exit Reason</th>
                    </tr>
                </thead>
                <tbody>
            """
            for i, row in round_trips.iterrows():
                pnl_class = 'positive' if row['pnl'] > 0 else 'negative'
                # Get color from mapping for inline style (most robust)
                r = str(row['exit_reason'])
                # Handle TP1+SL styles by checking common prefixes
                base_r = r.split('+')[0] if '+' in r else r
                bg_color = colors.get(r, colors.get(base_r, '#6B7280'))
                
                trades_table_html += f"""
                    <tr>
                        <td>{i+1}</td>
                        <td>{row['entry_time']}</td>
                        <td>{row['exit_time']}</td>
                        <td>${row['entry_price']:.6f}</td>
                        <td>${row['exit_price']:.6f}</td>
                        <td>${row['avg_exit_price']:.6f}</td>
                        <td class="{pnl_class}">${row['pnl']:.2f}</td>
                        <td class="{pnl_class}">{row['pnl_pct']:.2f}%</td>
                        <td>{self._format_duration(row['hold_duration_hours'])}</td>
                        <td><span class="badge" style="background-color: {bg_color}; color: white; border: 1px solid rgba(255,255,255,0.2); display: inline-block;">{row['exit_reason']}</span></td>
                    </tr>
                """
            trades_table_html += "</tbody></table>"
        else:
            trades_table_html = "<p>No completed trades.</p>"

        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Backtest Report</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        h1 {{
            text-align: center;
            font-size: 2.5rem;
            margin-bottom: 30px;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .metric-card {{
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            padding: 24px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.1);
        }}
        .metric-card h3 {{
            color: #888;
            font-size: 0.9rem;
            text-transform: uppercase;
            margin-bottom: 8px;
        }}
        .metric-card .value {{
            font-size: 2rem;
            font-weight: bold;
        }}
        .positive {{ color: #4CAF50; }}
        .negative {{ color: #F44336; }}
        .chart-container {{
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 30px;
            display: flex;
            justify-content: center;
        }}
        .chart-wrapper {{
            max-width: 300px;
            width: 100%;
            margin: 0 auto;
        }}
        .section-title {{
            font-size: 1.5rem;
            margin: 30px 0 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid rgba(255,255,255,0.1);
        }}
        .trades-table {{
            width: 100%;
            border-collapse: collapse;
            background: rgba(255,255,255,0.02);
            border-radius: 12px;
            overflow: hidden;
        }}
        .trades-table th, .trades-table td {{
            padding: 12px 16px;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }}
        .trades-table th {{
            background: rgba(255,255,255,0.05);
            font-weight: 600;
            color: #888;
            text-transform: uppercase;
            font-size: 0.8rem;
        }}
        .trades-table tr:hover {{
            background: rgba(255,255,255,0.03);
        }}
        .badge {{
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
        }}
        .badge-tp1 {{ background: #4CAF50; color: white; }}
        .badge-tp2 {{ background: #8BC34A; color: white; }}
        .badge-tp3 {{ background: #CDDC39; color: #333; }}
        .badge-full-tp {{ background: #10B981; color: white; }}
        .badge-sl, .badge-stop-loss {{ background: #F44336; color: white; }}
        .badge-breakeven {{ background: #F59E0B; color: white; }}
        .badge-manual {{ background: #9E9E9E; color: white; }}
        .badge-tp1-sl {{ background: #FF9800; color: white; }}
        .badge-tp2-sl {{ background: #06B6D4; color: white; }}
        .badge-tp3-sl {{ background: #EC4899; color: white; }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
        }}
        .stat-item {{
            background: rgba(255,255,255,0.03);
            padding: 16px;
            border-radius: 8px;
        }}
        .stat-item .label {{ color: #888; font-size: 0.85rem; }}
        .stat-item .val {{ font-size: 1.25rem; font-weight: 600; margin-top: 4px; }}
        .report-time {{
            text-align: center;
            color: #666;
            margin-top: 30px;
            font-size: 0.85rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{self.symbol} ({self.timeframe})</h1>
        <p style="text-align:center; color:#888; margin-top:-20px; margin-bottom:10px;">Backtest Report</p>
        <p style="text-align:center; margin-bottom:30px;">
            <span style="background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); padding: 6px 16px; border-radius: 20px; font-size: 0.9rem; font-weight: 600; margin-right: 10px;">Strategy: {self.strategy_name}</span>
            <span style="background: linear-gradient(90deg, #f093fb 0%, #f5576c 100%); padding: 6px 16px; border-radius: 20px; font-size: 0.9rem; font-weight: 600;">Leverage: {self.leverage}x</span>
        </p>
        
        <div class="metrics-grid">
            <div class="metric-card">
                <h3>Initial Balance</h3>
                <div class="value">${float(self.initial_balance):,.2f}</div>
            </div>
            <div class="metric-card">
                <h3>Final Balance</h3>
                <div class="value">${float(final_balance):,.2f}</div>
            </div>
            <div class="metric-card">
                <h3>Net Profit/Loss</h3>
                <div class="value {'positive' if profit >= 0 else 'negative'}">${profit:+,.2f} ({profit_pct:+.1f}%)</div>
            </div>
            <div class="metric-card">
                <h3>Max Drawdown</h3>
                <div class="value negative">{drawdown.get('max_drawdown_pct', 0):.2f}%</div>
            </div>
            <div class="metric-card">
                <h3>Avg Drawdown</h3>
                <div class="value negative">{drawdown.get('avg_drawdown_pct', 0):.2f}%</div>
            </div>
            <div class="metric-card">
                <h3>Max DD Duration</h3>
                <div class="value">{drawdown.get('max_dd_duration', 0)} trades</div>
            </div>
        </div>
        
        <h2 class="section-title">Risk-Adjusted Metrics</h2>
        <div class="metrics-grid">
            <div class="metric-card">
                <h3>Sharpe Ratio</h3>
                <div class="value">{risk_metrics.get('sharpe_ratio', 0):.2f}</div>
                <div style="color:#888; font-size:0.75rem; margin-top:4px;">Risk-adjusted return</div>
            </div>
            <div class="metric-card">
                <h3>Sortino Ratio</h3>
                <div class="value">{risk_metrics.get('sortino_ratio', 0):.2f}</div>
                <div style="color:#888; font-size:0.75rem; margin-top:4px;">Downside risk-adjusted</div>
            </div>
            <div class="metric-card">
                <h3>Calmar Ratio</h3>
                <div class="value">{risk_metrics.get('calmar_ratio', 0):.2f}</div>
                <div style="color:#888; font-size:0.75rem; margin-top:4px;">Return vs max drawdown</div>
            </div>
            <div class="metric-card">
                <h3>Volatility</h3>
                <div class="value">{risk_metrics.get('volatility', 0):.2f}%</div>
                <div style="color:#888; font-size:0.75rem; margin-top:4px;">Trade return std dev</div>
            </div>
            <div class="metric-card">
                <h3>VaR (95%)</h3>
                <div class="value negative">{risk_metrics.get('var_95', 0):.2f}%</div>
                <div style="color:#888; font-size:0.75rem; margin-top:4px;">Max loss at 95% confidence</div>
            </div>
        </div>
        
        {'<div class="metrics-grid">' + f"""
            <div class="metric-card">
                <h3>Win Rate</h3>
                <div class="value">{metrics['win_rate']:.1f}%</div>
                <div style="color:#888; margin-top:4px;">{metrics['win_count']}W / {metrics['loss_count']}L</div>
            </div>
            <div class="metric-card">
                <h3>Profit Factor</h3>
                <div class="value">{profit_factor_display}</div>
            </div>
            <div class="metric-card">
                <h3>Expectancy</h3>
                <div class="value">${metrics['expectancy']:.2f}</div>
            </div>
            <div class="metric-card">
                <h3>Avg Hold Time</h3>
                <div class="value">{self._format_duration(metrics['avg_hold_hours'])}</div>
            </div>
        """ + '</div>' if metrics else ''}
        
        <h2 class="section-title">Exit Distribution</h2>
        <div class="metrics-grid" style="margin-bottom: 20px;">
            <div class="metric-card" style="border-left: 5px solid #10B981; background: rgba(16, 185, 129, 0.1);">
                <h3 style="color: #10B981;">FULL_TP Exits</h3>
                <div class="value">{exit_data.get('FULL_TP', 0)}</div>
                <div style="color:#888; font-size:0.75rem; margin-top:4px;">Target reached</div>
            </div>
            <div class="metric-card" style="border-left: 5px solid #F59E0B; background: rgba(245, 158, 11, 0.1);">
                <h3 style="color: #F59E0B;">BREAKEVEN Exits</h3>
                <div class="value">{exit_data.get('BREAKEVEN', 0)}</div>
                <div style="color:#888; font-size:0.75rem; margin-top:4px;">Profit protected</div>
            </div>
            <div class="metric-card" style="border-left: 5px solid #EF4444; background: rgba(239, 68, 68, 0.1);">
                <h3 style="color: #EF4444;">STOP_LOSS Exits</h3>
                <div class="value">{exit_data.get('STOP_LOSS', exit_data.get('SL', 0))}</div>
                <div style="color:#888; font-size:0.75rem; margin-top:4px;">Initial risk hit</div>
            </div>
        </div>
        <div class="chart-container">
            <div class="chart-wrapper">
                <canvas id="exitPieChart_{safe_symbol}"></canvas>
            </div>
        </div>
        
        <h2 class="section-title">Equity Curve</h2>
        <div class="chart-container" style="height: 300px;">
            <canvas id="equityChart_{safe_symbol}"></canvas>
        </div>
        
        <h2 class="section-title">Monthly Returns</h2>
        <div style="overflow-x: auto;">
            <table class="trades-table">
                <thead>
                    <tr>
                        <th>Month</th>
                        <th>Trades</th>
                        <th>PnL ($)</th>
                        <th>Return (%)</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(f'''<tr>
                        <td>{month}</td>
                        <td>{data['trades']}</td>
                        <td class="{'positive' if data['pnl'] >= 0 else 'negative'}">${data['pnl']:.2f}</td>
                        <td class="{'positive' if data['pnl_pct'] >= 0 else 'negative'}">{data['pnl_pct']:+.2f}%</td>
                    </tr>''' for month, data in monthly_returns.items()) if monthly_returns else '<tr><td colspan="4" style="text-align:center;color:#888;">No monthly data</td></tr>'}
                </tbody>
            </table>
        </div>
        
        {'<h2 class="section-title">📈 Additional Stats</h2><div class="metrics-grid">' + f"""
            <div class="metric-card">
                <h3>Average Win</h3>
                <div class="value positive">${metrics['avg_win']:.2f}</div>
            </div>
            <div class="metric-card">
                <h3>Average Loss</h3>
                <div class="value negative">${metrics['avg_loss']:.2f}</div>
            </div>
            <div class="metric-card">
                <h3>Largest Win</h3>
                <div class="value positive">${metrics['largest_win']:.2f}</div>
            </div>
            <div class="metric-card">
                <h3>Largest Loss</h3>
                <div class="value negative">${metrics['largest_loss']:.2f}</div>
            </div>
            <div class="metric-card">
                <h3>Risk/Reward</h3>
                <div class="value">{risk_reward_display}</div>
            </div>
            <div class="metric-card">
                <h3>Max Consec. Wins</h3>
                <div class="value">{metrics['max_consec_wins']}</div>
            </div>
            <div class="metric-card">
                <h3>Max Consec. Losses</h3>
                <div class="value">{metrics['max_consec_losses']}</div>
            </div>
            <div class="metric-card">
                <h3>Gross Profit</h3>
                <div class="value positive">${metrics['gross_profit']:.2f}</div>
            </div>
            <div class="metric-card">
                <h3>Gross Loss</h3>
                <div class="value negative">${metrics['gross_loss']:.2f}</div>
            </div>
        """ + '</div>' if metrics else ''}
        
        <h2 class="section-title">📋 Trade Details</h2>
        <div style="overflow-x: auto;">
            {trades_table_html}
        </div>
        
        <p class="report-time">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
    
    <script>
        (function() {{
        const ctx = document.getElementById('exitPieChart_{safe_symbol}').getContext('2d');
        new Chart(ctx, {{
            type: 'pie',
            data: {{
                labels: {labels},
                datasets: [{{
                    data: {values},
                    backgroundColor: {pie_colors},
                    borderColor: 'rgba(255,255,255,0.2)',
                    borderWidth: 3
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    legend: {{
                        position: 'bottom',
                        labels: {{ 
                            color: '#eee', 
                            padding: 20,
                            font: {{ size: 14, weight: 'bold' }}
                        }}
                    }},
                    title: {{
                        display: true,
                        text: 'Exit Reasons Distribution',
                        color: '#eee',
                        font: {{ size: 18, weight: 'bold' }}
                    }},
                    tooltip: {{
                        callbacks: {{
                            label: function(context) {{
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const value = context.parsed;
                                const percentage = ((value / total) * 100).toFixed(1);
                                return context.label + ': ' + percentage + '%';
                            }}
                        }}
                    }}
                }}
            }}
        }});
        
        // Equity Curve Line Chart
        const equityCtx = document.getElementById('equityChart_{safe_symbol}').getContext('2d');
        new Chart(equityCtx, {{
            type: 'line',
            data: {{
                labels: {list(range(len(drawdown.get('equity_curve', [float(self.initial_balance)]))))},
                datasets: [{{
                    label: 'Portfolio Value ($)',
                    data: {drawdown.get('equity_curve', [float(self.initial_balance)])},
                    borderColor: '#3B82F6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    fill: true,
                    tension: 0.2,
                    pointRadius: 3,
                    pointHoverRadius: 6
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }},
                    title: {{
                        display: true,
                        text: 'Equity Curve (After Each Trade)',
                        color: '#eee',
                        font: {{ size: 16 }}
                    }}
                }},
                scales: {{
                    x: {{
                        title: {{ display: true, text: 'Trade #', color: '#888' }},
                        ticks: {{ color: '#888' }},
                        grid: {{ color: 'rgba(255,255,255,0.05)' }}
                    }},
                    y: {{
                        title: {{ display: true, text: 'Balance ($)', color: '#888' }},
                        ticks: {{ color: '#888' }},
                        grid: {{ color: 'rgba(255,255,255,0.05)' }}
                    }}
                }}
            }}
        }});
        }})();
    </script>
</body>
</html>
"""
        
        # Save HTML report
        if return_only:
            return html_content
        
        # Save HTML report
        safe_symbol = self.symbol.replace('/', '')
        html_dir = os.path.join(output_dir, "html")
        os.makedirs(html_dir, exist_ok=True)
        report_path = os.path.join(html_dir, f"backtest_report_{safe_symbol}_{self.timeframe}.html")
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"HTML report saved to: {report_path}")
        return report_path

    def _export_csv(self, trades_df: pd.DataFrame, round_trips: pd.DataFrame, output_dir: str = ".") -> None:
        """Export trade data to CSV files."""
        # Raw trades log
        safe_symbol = self.symbol.replace('/', '')
        csv_dir = os.path.join(output_dir, "csv")
        os.makedirs(csv_dir, exist_ok=True)
        
        log_path = os.path.join(csv_dir, f"backtest_logs_{safe_symbol}_{self.timeframe}.csv")
        trades_df.to_csv(log_path, index=False)
        print(f"Raw trades saved to: {log_path}")
        
        # Round-trip trades with PnL
        if not round_trips.empty:
            trades_path = os.path.join(csv_dir, f"backtest_trades_{safe_symbol}_{self.timeframe}.csv")
            round_trips.to_csv(trades_path, index=False)
            print(f"Trade details saved to: {trades_path}")
            print(f"Trade details saved to: {trades_path}")
