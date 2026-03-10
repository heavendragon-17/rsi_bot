import math
import json
"""
Backtest Reporter (Thin Formatter)
====================================
Formats pre-computed results dict from BacktestEngine.compute_results() into:
- HTML report with charts
- CSV export of round-trip trades

All metric computation lives in BacktestEngine. This class is purely a formatter.
"""
import pandas as pd
import numpy as np
import structlog
from datetime import datetime
import os

logger = structlog.get_logger()


class BacktestReporter:
    """Format and export backtest results. Receives a pre-computed results dict."""

    def __init__(
        self,
        results: dict,
        symbol: str,
        timeframe: str,
        strategy_name: str,
        leverage: int = 1,
    ):
        self.results = results
        self.symbol = symbol
        self.timeframe = timeframe
        self.strategy_name = strategy_name
        self.leverage = leverage

    @staticmethod
    def _format_duration(hours: float) -> str:
        """Format hours into human-readable duration."""
        if hours is None or (isinstance(hours, float) and np.isnan(hours)):
            return "N/A"
        if hours < 1:
            return f"{hours * 60:.0f}m"
        if hours < 24:
            return f"{hours:.1f}h"
        days = hours / 24
        return f"{days:.1f}d"

    def generate_report(self, output_dir: str = ".") -> str | None:
        """Generate HTML and CSV reports from pre-computed results."""
        round_trips = self.results.get("round_trips", [])
        if not round_trips and self.results.get("metrics", {}).get("total_trades", 0) == 0:
            logger.info("no_trades_executed")
            return None

        os.makedirs(output_dir, exist_ok=True)
        report_path = self._generate_html_report(return_only=False, output_dir=output_dir)
        self._export_csv(output_dir=output_dir)
        return report_path

    def _generate_html_report(
        self, return_only: bool = False, output_dir: str = "."
    ) -> str | None:
        """Generate HTML report. If return_only=True, returns HTML string without saving."""
        r = self.results
        metrics = r.get("metrics", {})
        drawdown = r.get("drawdown", {})
        risk_metrics = r.get("risk_metrics", {})
        monthly_returns = r.get("monthly_returns", {})
        initial_balance = r.get("initial_balance", 0.0)
        final_balance = r.get("final_balance", 0.0)
        profit = r.get("net_profit", 0.0)
        profit_pct = r.get("net_profit_pct", 0.0)

        # Equity curve (dated format: [{date, balance}])
        equity_curve_pts = r.get("equity_curve", [{"date": "", "balance": initial_balance}])
        chart_dates = [pt["date"] for pt in equity_curve_pts]
        chart_balances = [pt["balance"] for pt in equity_curve_pts]

        # Round trips as DataFrame for table rendering
        rt_list = r.get("round_trips", [])
        round_trips_df = pd.DataFrame(rt_list) if rt_list else pd.DataFrame()

        safe_symbol = self.symbol.replace("/", "")

        # Pre-compute display values that may have infinity
        profit_factor_display = (
            f"{metrics['profit_factor']:.2f}"
            if metrics and metrics.get("profit_factor") != float("inf")
            else "INF"
        )
        risk_reward_display = (
            f"{metrics['risk_reward']:.2f}"
            if metrics and metrics.get("risk_reward") != float("inf")
            else "INF"
        )

        # Pie chart data
        exit_data = metrics.get("exit_reason_counts", {}) if metrics else {}
        labels = list(exit_data.keys()) if exit_data else ["No Trades"]
        values = list(exit_data.values()) if exit_data else [1]

        colors = {
            "TP1": "#22C55E",
            "TP2": "#3B82F6",
            "TP3": "#8B5CF6",
            "FULL_TP": "#10B981",
            "SL": "#EF4444",
            "STOP_LOSS": "#EF4444",
            "BREAKEVEN": "#F59E0B",
            "MANUAL": "#6B7280",
            "TP1+SL": "#F59E0B",
            "TP2+SL": "#06B6D4",
            "TP3+SL": "#EC4899",
            "UNKNOWN": "#64748B",
            "No Trades": "#9CA3AF",
        }
        pie_colors = [colors.get(lbl, "#64748B") for lbl in labels]

        unique_symbols = []
        best_ticker_name = "N/A"
        best_ticker_pnl = "$0.00"
        worst_ticker_name = "N/A"
        worst_ticker_pnl = "$0.00"
        per_symbol_stats_html = ""
        ticker_pills_html = ""
        pnl_by_ticker = {}

        if not round_trips_df.empty and "symbol" in round_trips_df.columns:
            unique_symbols = sorted(round_trips_df["symbol"].unique().tolist())
            
            # Precompute color map based on hash of symbol name
            def get_color(sym):
                colors = ["#3B82F6", "#EF4444", "#10B981", "#F59E0B", "#8B5CF6", "#EC4899", "#06B6D4", "#F97316", "#14B8A6", "#84CC16"]
                return colors[hash(sym) % len(colors)]

            ticker_colors = {sym: get_color(sym) for sym in unique_symbols}
            
            pnl_series = round_trips_df.groupby("symbol")["pnl"].sum()
            pnl_by_ticker = pnl_series.to_dict()
            
            if len(pnl_series) > 0:
                best_sym = pnl_series.idxmax()
                worst_sym = pnl_series.idxmin()
                best_ticker_name = best_sym
                best_ticker_pnl = f"${pnl_series[best_sym]:+.2f}"
                worst_ticker_name = worst_sym
                worst_ticker_pnl = f"${pnl_series[worst_sym]:+.2f}"

            # Generate stats panel HTMl
            per_symbol_stats_html = '<div class="side-panel"><h3>Stats by Ticker</h3><div class="side-panel-inner">'
            for sym in unique_symbols:
                sym_df = round_trips_df[round_trips_df["symbol"] == sym]
                sym_trades = len(sym_df)
                sym_wins = len(sym_df[sym_df["pnl"] > 0])
                sym_wr = (sym_wins / sym_trades * 100) if sym_trades > 0 else 0
                sym_pnl = sym_df["pnl"].sum()
                sym_hold = sym_df["hold_duration_hours"].mean()
                pnl_class = "positive" if sym_pnl >= 0 else "negative"
                
                per_symbol_stats_html += f"""
                <div class="sym-stat-card" data-symbol="{sym}">
                    <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                        <span class="ticker-badge" style="background-color: {ticker_colors[sym]}">{sym}</span>
                        <span class="{pnl_class}" style="font-weight:bold;">${sym_pnl:.2f}</span>
                    </div>
                    <div style="color:#888; font-size:0.8rem;">
                        {sym_trades} trades | {sym_wr:.1f}% WR | {self._format_duration(sym_hold)} avg hold
                    </div>
                </div>
                """
            per_symbol_stats_html += '</div></div>'
            
            # Generate Filter Pills
            ticker_pills_html = '<div class="filter-bar"><button class="filter-pill active" data-symbol="ALL">All Tickers</button>'
            for sym in unique_symbols:
                ticker_pills_html += f'<button class="filter-pill" data-symbol="{sym}">{sym}</button>'
            ticker_pills_html += '</div>'

        # Build trades table HTML
        if not round_trips_df.empty:
            trades_table_html = f"""
            {ticker_pills_html}
            <div class="trades-layout">
            <div class="trades-table-container">
            <table class="trades-table" id="tradesTable">
                <thead>
                    <tr>
                        <th>#</th>
                        {"<th>Symbol</th>" if "symbol" in round_trips_df.columns else ""}
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
            for i, row in round_trips_df.iterrows():
                pnl_class = "positive" if row["pnl"] > 0 else "negative"
                hold_hours = row.get("hold_duration_hours")
                exit_reason = str(row.get("exit_reason", "UNKNOWN"))
                
                sym_col = ""
                row_attr = ""
                if "symbol" in row:
                    sym = row['symbol']
                    sym_col = f'<td><span class="ticker-badge" style="background-color: {ticker_colors.get(sym, "#666")}">{sym}</span></td>'
                    row_attr = f'data-symbol="{sym}"'
                    
                trades_table_html += f"""
                    <tr {row_attr}>
                        <td>{i + 1}</td>
                        {sym_col}
                        <td>{row['entry_time']}</td>
                        <td>{row['exit_time']}</td>
                        <td>${row['entry_price']:.6f}</td>
                        <td>${row['exit_price']:.6f}</td>
                        <td>${row['avg_exit_price']:.6f}</td>
                        <td class="{pnl_class}">${row['pnl']:.2f}</td>
                        <td class="{pnl_class}">{row['pnl_pct']:.2f}%</td>
                        <td>{self._format_duration(hold_hours)}</td>
                        <td><span class="badge badge-{exit_reason.lower().replace('+', '-')}">{exit_reason}</span></td>
                    </tr>
                """
            trades_table_html += "</tbody></table></div>" + per_symbol_stats_html + "</div>"
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
        .chart-wrapper-pie {{
            max-width: 300px;
            width: 100%;
            margin: 0 auto;
        }}
        .trades-layout {{
            display: flex;
            gap: 20px;
            align-items: flex-start;
        }}
        .trades-table-container {{
            flex: 1;
            overflow-x: auto;
        }}
        .side-panel {{
            width: 300px;
            background: rgba(255,255,255,0.02);
            border-radius: 12px;
            padding: 16px;
            border: 1px solid rgba(255,255,255,0.05);
            flex-shrink: 0;
            max-height: 800px;
            overflow-y: auto;
        }}
        .side-panel::-webkit-scrollbar {{
            width: 8px;
        }}
        .side-panel::-webkit-scrollbar-thumb {{
            background-color: rgba(255,255,255,0.1);
            border-radius: 4px;
        }}
        .side-panel h3 {{
            margin-bottom: 16px;
            padding-bottom: 10px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        .sym-stat-card {{
            background: rgba(255,255,255,0.03);
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 12px;
            transition: opacity 0.2s;
        }}
        .ticker-badge {{
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: bold;
            color: white;
            display: inline-block;
        }}
        .filter-bar {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 16px;
        }}
        .filter-pill {{
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            color: #ccc;
            padding: 6px 16px;
            border-radius: 20px;
            cursor: pointer;
            transition: all 0.2s;
            font-size: 0.85rem;
        }}
        .filter-pill:hover {{
            background: rgba(255,255,255,0.1);
            color: white;
        }}
        .filter-pill.active {{
            background: #3B82F6;
            color: white;
            border-color: #3B82F6;
        }}
        .chart-wrapper {{
            width: 100%;
            margin: 0 auto;
        }}
        @media (max-width: 1000px) {{
            .trades-layout {{ flex-direction: column; }}
            .side-panel {{ width: 100%; }}
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
        .badge-full_tp {{ background: #10B981; color: white; }}
        .badge-sl, .badge-stop_loss {{ background: #F44336; color: white; }}
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
                <div class="value">${initial_balance:,.2f}</div>
            </div>
            <div class="metric-card">
                <h3>Final Balance</h3>
                <div class="value">${final_balance:,.2f}</div>
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
                <h3>Total Symbols</h3>
                <div class="value">{len(unique_symbols)}</div>
                <div style="color:#888; font-size:0.75rem; margin-top:4px;">Traded in period</div>
            </div>
            <div class="metric-card">
                <h3>Avg Trades/Symbol</h3>
                <div class="value">{metrics.get('total_trades', 0) / len(unique_symbols) if len(unique_symbols) > 0 else 0:.1f}</div>
                <div style="color:#888; font-size:0.75rem; margin-top:4px;">Activity balance</div>
            </div>
        </div>

        <div class="metrics-grid">
            <div class="metric-card">
                <h3>Total Trades</h3>
                <div class="value">{metrics.get('total_trades', 0)}</div>
                <div style="color:#888; font-size:0.75rem; margin-top:4px;">Period volume</div>
            </div>
            <div class="metric-card">
                <h3>Best Ticker</h3>
                <div class="value positive">{best_ticker_name}</div>
                <div style="color:#888; font-size:0.75rem; margin-top:4px;">{best_ticker_pnl}</div>
            </div>
            <div class="metric-card">
                <h3>Worst Ticker</h3>
                <div class="value negative">{worst_ticker_name}</div>
                <div style="color:#888; font-size:0.75rem; margin-top:4px;">{worst_ticker_pnl}</div>
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
        <div class="chart-container">
            <div class="chart-wrapper-pie">
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
                    {''.join(f"""<tr>
                        <td>{month}</td>
                        <td>{data['trades']}</td>
                        <td class="{'positive' if data['pnl'] >= 0 else 'negative'}">${data['pnl']:.2f}</td>
                        <td class="{'positive' if data['pnl_pct'] >= 0 else 'negative'}">{data['pnl_pct']:+.2f}%</td>
                    </tr>""" for month, data in monthly_returns.items()) if monthly_returns else '<tr><td colspan="4" style="text-align:center;color:#888;">No monthly data</td></tr>'}
                </tbody>
            </table>
        </div>

        {'<h2 class="section-title">Additional Stats</h2><div class="metrics-grid">' + f"""
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

        <h2 class="section-title">Per-Symbol PnL</h2>
        <div class="chart-container" style="height: {max(300, len(unique_symbols) * 30)}px;">
            <canvas id="tickerPnlChart_{safe_symbol}"></canvas>
        </div>

        <h2 class="section-title">Trade Details</h2>
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

        // Equity Curve Line Chart (dated)
        const equityCtx = document.getElementById('equityChart_{safe_symbol}').getContext('2d');
        new Chart(equityCtx, {{
            type: 'line',
            data: {{
                labels: {chart_dates},
                datasets: [{{
                    label: 'Portfolio Value ($)',
                    data: {chart_balances},
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
                        text: 'Equity Curve',
                        color: '#eee',
                        font: {{ size: 16 }}
                    }}
                }},
                scales: {{
                    x: {{
                        title: {{ display: true, text: 'Date', color: '#888' }},
                        ticks: {{ color: '#888', maxTicksLimit: 12 }},
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

        // Ticker filter logic
        document.querySelectorAll('.filter-pill').forEach(pill => {{
            pill.addEventListener('click', (e) => {{
                // Update active state
                document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
                e.target.classList.add('active');
                
                const selectedSym = e.target.getAttribute('data-symbol');
                const rows = document.querySelectorAll('#tradesTable tbody tr');
                
                rows.forEach(row => {{
                    if (selectedSym === 'ALL' || row.getAttribute('data-symbol') === selectedSym) {{
                        row.style.display = '';
                    }} else {{
                        row.style.display = 'none';
                    }}
                }});

                // Also dim the non-selected stats in the side panel
                const cards = document.querySelectorAll('.sym-stat-card');
                cards.forEach(card => {{
                    if (selectedSym === 'ALL' || card.getAttribute('data-symbol') === selectedSym) {{
                        card.style.opacity = '1';
                    }} else {{
                        card.style.opacity = '0.3';
                    }}
                }});
            }});
        }});

        // Ticker PnL Bar Chart
        const tickerPnlData = {json.dumps(pnl_by_ticker)};
        if (Object.keys(tickerPnlData).length > 0) {{
            // Sort by PnL
            const sortedTickers = Object.entries(tickerPnlData).sort((a, b) => b[1] - a[1]);
            const tLabels = sortedTickers.map(t => t[0]);
            const tData = sortedTickers.map(t => t[1]);
            const tColors = tData.map(v => v >= 0 ? 'rgba(76, 175, 80, 0.7)' : 'rgba(244, 67, 54, 0.7)');
            const tBorder = tData.map(v => v >= 0 ? '#4CAF50' : '#F44336');

            const barCtx = document.getElementById('tickerPnlChart_{safe_symbol}').getContext('2d');
            new Chart(barCtx, {{
                type: 'bar',
                data: {{
                    labels: tLabels,
                    datasets: [{{
                        label: 'Net PnL ($)',
                        data: tData,
                        backgroundColor: tColors,
                        borderColor: tBorder,
                        borderWidth: 1
                    }}]
                }},
                options: {{
                    indexAxis: 'y',
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{ display: false }},
                        title: {{
                            display: true,
                            text: 'PnL by Ticker',
                            color: '#eee',
                            font: {{ size: 16 }}
                        }}
                    }},
                    scales: {{
                        x: {{
                            title: {{ display: true, text: 'PnL ($)', color: '#888' }},
                            ticks: {{ color: '#888' }},
                            grid: {{ color: 'rgba(255,255,255,0.05)' }}
                        }},
                        y: {{
                            ticks: {{ color: '#888' }},
                            grid: {{ display: false }}
                        }}
                    }}
                }}
            }});
        }}
        }})();
    </script>
</body>
</html>
"""

        if return_only:
            return html_content

        safe_symbol = self.symbol.replace("/", "")
        html_dir = os.path.join(output_dir, "html")
        os.makedirs(html_dir, exist_ok=True)
        report_path = os.path.join(
            html_dir, f"backtest_report_{safe_symbol}_{self.timeframe}.html"
        )
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        logger.info("html_report_saved", path=report_path)
        return report_path

    def _export_csv(self, output_dir: str = ".") -> None:
        """Export round-trip trades to CSV."""
        rt_list = self.results.get("round_trips", [])
        if not rt_list:
            return

        safe_symbol = self.symbol.replace("/", "")
        csv_dir = os.path.join(output_dir, "csv")
        os.makedirs(csv_dir, exist_ok=True)

        round_trips_df = pd.DataFrame(rt_list)
        trades_path = os.path.join(
            csv_dir, f"backtest_trades_{safe_symbol}_{self.timeframe}.csv"
        )
        round_trips_df.to_csv(trades_path, index=False)
        logger.info("csv_exported", path=trades_path)
