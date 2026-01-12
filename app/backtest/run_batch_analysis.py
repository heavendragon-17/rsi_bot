
import os
import sys
import yaml
import pandas as pd
import re
import webbrowser
import argparse
from decimal import Decimal
from decimal import Decimal
from datetime import datetime
import copy
# Determine paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

# Ensure we can import from app
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from app.backtest.engine import BacktestEngine
from app.backtest.reporting import BacktestReporter
from app.strategies.rsi_wma_retest import RsiWmaRetestStrategy
from app.strategies.rsi_no_retest import RsiNoRetestStrategy
from app.backtest.download_data import download_data

# Strategy mapping
STRATEGY_MAP = {
    "rsi_wma_retest": RsiWmaRetestStrategy,
    "rsi_no_retest": RsiNoRetestStrategy,
}

# Path constants
SYMBOLS_PATH = os.path.join(SCRIPT_DIR, "symbols.txt")
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.yaml")
REPORT_DIR = os.path.join(SCRIPT_DIR, "report")
DATA_DIR = os.path.join(SCRIPT_DIR, "data")


def load_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)

class BatchHtmlGenerator:
    def __init__(self, batch_results):
        """
        batch_results: list of dicts {
            'symbol': str,
            'metrics': dict,
            'html': str,
            'profit': float,
            'profit_pct': float,
            'drawdown': float,
            'trades': int,
            'round_trips': pd.DataFrame
        }
        """
        self.results = batch_results

    def _extract_body_content(self, html_doc):
        """Extract content inside <body> tags."""
        match = re.search(r'<body.*?>(.*?)</body>', html_doc, re.DOTALL)
        if match:
            return match.group(1)
        return html_doc

    def generate(self, filename="batch_report.html"):
        # Calculate Aggregates
        total_pnl = sum(r['profit'] for r in self.results)
        total_initial = sum(r['initial_balance'] for r in self.results)
        total_final = sum(r['final_balance'] for r in self.results)
        total_fees = sum(r.get('total_fees', 0) for r in self.results)
        total_volume = sum(r.get('total_volume', 0) for r in self.results)
        portfolio_return = ((total_final - total_initial) / total_initial) * 100 if total_initial > 0 else 0
        
        avg_drawdown = sum(r['drawdown'] for r in self.results) / len(self.results) if self.results else 0
        total_trades = sum(r['trades'] for r in self.results)
        
        # --- Prepare Equity Curve Data ---
        all_trades = []
        for r in self.results:
            if 'round_trips' in r and not r['round_trips'].empty:
                t = r['round_trips'].copy()
                t['symbol'] = r['symbol']
                # Ensure exit_time is datetime
                t['exit_time'] = pd.to_datetime(t['exit_time'])
                all_trades.append(t)

        equity_values = [total_initial]
        equity_labels = ["Start"] # Date strings

        if all_trades:
            combined = pd.concat(all_trades)
            # Sort by exit time to simulate portfolio equity evolution
            combined = combined.sort_values('exit_time')

            current_equity = total_initial

            for i, row in combined.iterrows():
                current_equity += row['pnl']
                equity_values.append(current_equity)
                # Use exit time as label
                equity_labels.append(row['exit_time'].strftime('%Y-%m-%d %H:%M'))

        # Build Navigation
        nav_html = """
        <div class="nav-sidebar">
            <div class="nav-brand">RSI Bot Batch</div>
            <button class="nav-item active" onclick="openTab(event, 'Overview')">
                <span class="icon">📊</span> Overview
            </button>
        """
        for i, res in enumerate(self.results):
            symbol_clean = res['symbol'].replace('/', '')
            pnl_class = "positive" if res['profit'] >= 0 else "negative"
            nav_html += f"""
            <button class="nav-item" onclick="openTab(event, '{symbol_clean}')">
                <span class="icon">📈</span> {res['symbol']}
                <span class="nav-badge {pnl_class}">{res['profit_pct']:+.1f}%</span>
            </button>
            """
        nav_html += "</div>"

        # Fee card HTML (only if fees paid)
        gross_pnl = total_pnl + total_fees
        fee_card_html = f'''
                <div class="metric-card">
                    <h3>Total Fees Paid</h3>
                    <div class="value negative">${total_fees:,.2f}</div>
                    <div style="color:#888; font-size:0.75rem; margin-top:4px;">Gross: ${gross_pnl:+,.2f}</div>
                </div>
        ''' if total_fees > 0 else ''

        # Build Content Areas
        content_html = f"""
        <div id="Overview" class="tab-content active" style="display:block;">
            <div class="header-section">
                <h1>Portfolio Overview</h1>
                <p>Aggregated performance across {len(self.results)} pairs</p>
            </div>
            
            <div class="metrics-grid">
                <div class="metric-card">
                    <h3>Total Net Profit</h3>
                    <div class="value {'positive' if total_pnl >= 0 else 'negative'}">${total_pnl:,.2f}</div>
                </div>
                <div class="metric-card">
                    <h3>Portfolio Return</h3>
                    <div class="value {'positive' if portfolio_return >= 0 else 'negative'}">{portfolio_return:+.2f}%</div>
                </div>
                {fee_card_html}
                <div class="metric-card">
                    <h3>Total Volume</h3>
                    <div class="value">${total_volume:,.0f}</div>
                </div>
                <div class="metric-card">
                    <h3>Avg Drawdown</h3>
                    <div class="value negative">{avg_drawdown:.2f}%</div>
                </div>
                <div class="metric-card">
                    <h3>Total Trades</h3>
                    <div class="value">{total_trades}</div>
                </div>
            </div>

            <!-- Portfolio Equity Curve -->
            <h2 class="section-title">Portfolio Equity Curve</h2>
            <div class="chart-container" style="height: 400px; position: relative;">
                <canvas id="portfolioEquityChart"></canvas>
            </div>
            
            <h2 class="section-title">Performance Comparison</h2>
            <div class="table-container">
                <table class="trades-table">
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>PnL ($)</th>
                            <th>Return (%)</th>
                            <th>Drawdown</th>
                            <th>Trades</th>
                            <th>Win Rate</th>
                        </tr>
                    </thead>
                    <tbody>
        """
        
        for res in self.results:
            pnl_class = 'positive' if res['profit'] >= 0 else 'negative'
            content_html += f"""
                <tr>
                    <td><strong>{res['symbol']}</strong></td>
                    <td class="{pnl_class}">${res['profit']:.2f}</td>
                    <td class="{pnl_class}">{res['profit_pct']:+.2f}%</td>
                    <td>{res['drawdown']:.2f}%</td>
                    <td>{res['trades']}</td>
                    <td>{res['metrics'].get('win_rate', 0.0):.1f}%</td>
                </tr>
            """
            
        content_html += """
                    </tbody>
                </table>
            </div>
        </div>
        """

        # Individual Reports
        for res in self.results:
            symbol_clean = res['symbol'].replace('/', '')
            body_content = self._extract_body_content(res['html'])
            
            # Wrap in tab div
            content_html += f"""
            <div id="{symbol_clean}" class="tab-content" style="display:none;">
                {body_content}
            </div>
            """

        # Full HTML Template
        full_html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Batch Backtest Report</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --bg-dark: #1a1a2e;
            --bg-card: rgba(255,255,255,0.05);
            --accent: #667eea;
            --text-main: #eee;
            --text-muted: #888;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-dark);
            color: var(--text-main);
            display: flex;
            min-height: 100vh;
        }}
        /* Custom Scrollbar - WebKit */
        ::-webkit-scrollbar {{
            width: 8px;
            height: 8px;
        }}
        ::-webkit-scrollbar-track {{
            background: rgba(0,0,0,0.2);
            border-radius: 4px;
        }}
        ::-webkit-scrollbar-thumb {{
            background: rgba(102, 126, 234, 0.4);
            border-radius: 4px;
        }}
        ::-webkit-scrollbar-thumb:hover {{
            background: rgba(102, 126, 234, 0.6);
        }}
        /* Firefox scrollbar */
        * {{
            scrollbar-width: thin;
            scrollbar-color: rgba(102, 126, 234, 0.4) rgba(0,0,0,0.2);
        }}
        /* Sidebar */
        .nav-sidebar {{
            width: 250px;
            background: rgba(0,0,0,0.2);
            border-right: 1px solid rgba(255,255,255,0.05);
            padding: 20px;
            height: 100vh;
            position: fixed;
            overflow-y: auto;
        }}
        .nav-brand {{
            font-size: 1.2rem;
            font-weight: bold;
            margin-bottom: 30px;
            color: var(--accent);
            text-align: center;
        }}
        .nav-item {{
            display: flex;
            align-items: center;
            width: 100%;
            padding: 12px 15px;
            background: transparent;
            border: none;
            color: var(--text-muted);
            cursor: pointer;
            text-align: left;
            border-radius: 8px;
            margin-bottom: 5px;
            transition: all 0.2s;
        }}
        .nav-item:hover, .nav-item.active {{
            background: var(--bg-card);
            color: var(--text-main);
        }}
        .nav-item .icon {{ margin-right: 10px; }}
        .nav-badge {{
            margin-left: auto;
            font-size: 0.75rem;
            padding: 2px 6px;
            border-radius: 4px;
        }}
        
        /* Main Content */
        .main-content {{
            margin-left: 250px;
            flex: 1;
            padding: 40px;
            overflow-x: hidden;
        }}
        
        /* Reusing Report Styles */
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .metric-card {{
            background: var(--bg-card);
            border-radius: 16px;
            padding: 24px;
            border: 1px solid rgba(255,255,255,0.1);
        }}
        .metric-card h3 {{ color: var(--text-muted); font-size: 0.9rem; margin-bottom: 10px; }}
        .metric-card .value {{ font-size: 1.8rem; font-weight: bold; }}
        .positive {{ color: #4CAF50 !important; }}
        .negative {{ color: #F44336 !important; }}
        .section-title {{
            font-size: 1.5rem;
            margin: 40px 0 20px;
            padding-bottom: 10px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        
        /* Table Styles */
        .trades-table {{
            width: 100%;
            border-collapse: collapse;
            background: var(--bg-card);
            border-radius: 12px;
            overflow: hidden;
        }}
        .trades-table th, .trades-table td {{
            padding: 15px;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }}
        .trades-table th {{ background: rgba(255,255,255,0.05); color: var(--text-muted); }}
        
        /* Utilities */
        .tab-content {{ animation: fadeIn 0.3s ease; }}
        @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: translateY(0); }} }}
        
        /* Copy from reporting.py specific styles to ensure embedded reports look good */
        .badge {{ padding: 4px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; display: inline-block; }}
        .badge-tp1 {{ background: #4CAF50; color: white; }}
        .badge-tp2 {{ background: #8BC34A; color: white; }}
        .badge-tp3 {{ background: #CDDC39; color: #333; }}
        .badge-sl, .badge-stop_loss {{ background: #F44336; color: white; }}
        .badge-manual {{ background: #9E9E9E; color: white; }}
        .badge-tp1-sl {{ background: #FF9800; color: white; }}
        .badge-tp2-sl {{ background: #06B6D4; color: white; }}
        .badge-tp3-sl {{ background: #EC4899; color: white; }}
        
        .chart-container {{
            background: var(--bg-card);
            padding: 20px;
            border-radius: 16px;
            margin-bottom: 30px;
            min-height: 300px;
        }}
        .header-section {{
            margin-bottom: 40px;
        }}
        .chart-wrapper {{
            max-width: 300px;
            width: 100%;
            margin: 0 auto;
        }}
    </style>
</head>
<body>
    {nav_html}
    
    <div class="main-content">
        {content_html}
    </div>

    <script>
        function openTab(evt, tabName) {{
            // Hide all tab content
            var i, tabcontent, tablinks;
            tabcontent = document.getElementsByClassName("tab-content");
            for (i = 0; i < tabcontent.length; i++) {{
                tabcontent[i].style.display = "none";
                tabcontent[i].classList.remove("active");
            }}

            // Remove active class from nav items
            tablinks = document.getElementsByClassName("nav-item");
            for (i = 0; i < tablinks.length; i++) {{
                tablinks[i].className = tablinks[i].className.replace(" active", "");
            }}

            // Show current tab and add active class to button
            document.getElementById(tabName).style.display = "block";
            document.getElementById(tabName).classList.add("active");
            evt.currentTarget.className += " active";
        }}

        // Portfolio Equity Chart
        document.addEventListener('DOMContentLoaded', function() {{
            const ctx = document.getElementById('portfolioEquityChart').getContext('2d');

            new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: {equity_labels},
                    datasets: [{{
                        label: 'Total Portfolio Value ($)',
                        data: {equity_values},
                        borderColor: '#667eea',
                        backgroundColor: 'rgba(102, 126, 234, 0.1)',
                        fill: true,
                        tension: 0.2,
                        pointRadius: 2,
                        pointHoverRadius: 5
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {{
                        mode: 'index',
                        intersect: false,
                    }},
                    plugins: {{
                        title: {{
                            display: true,
                            text: 'Total Portfolio Equity (Realized)',
                            color: '#eee',
                            font: {{ size: 16 }}
                        }},
                        legend: {{
                            labels: {{ color: '#eee' }}
                        }}
                    }},
                    scales: {{
                        x: {{
                            title: {{ display: true, text: 'Time', color: '#888' }},
                            ticks: {{ color: '#888', maxTicksLimit: 12 }},
                            grid: {{ color: 'rgba(255,255,255,0.05)' }}
                        }},
                        y: {{
                            title: {{ display: true, text: 'Equity ($)', color: '#888' }},
                            ticks: {{ color: '#888' }},
                            grid: {{ color: 'rgba(255,255,255,0.05)' }}
                        }}
                    }}
                }}
            }});
        }});
    </script>
</body>
</html>
        """
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(full_html)
        print(f"\nBatch Report Saved: {filename}")


def main():
    # Parse CLI arguments
    parser = argparse.ArgumentParser(description="Run batch backtest analysis")
    parser.add_argument(
        "--strategy", 
        type=str, 
        default=None,
        choices=list(STRATEGY_MAP.keys()),
        help="Strategy to use (default: from config.yaml)"
    )
    args = parser.parse_args()
    
    if not os.path.exists(SYMBOLS_PATH):
        print(f"Error: {SYMBOLS_PATH} not found.")
        return

    # Load Config
    config = load_config()
    timeframe = config.get("timeframe", "15m")
    balance = config.get("backtest", {}).get("initial_balance", 1000)
    
    # Get strategy from config or CLI override
    strategy_name = args.strategy or config.get("strategy", "rsi_wma_retest")
    if strategy_name not in STRATEGY_MAP:
        print(f"Error: Unknown strategy '{strategy_name}'. Available: {list(STRATEGY_MAP.keys())}")
        return
    strategy_class = STRATEGY_MAP[strategy_name]
    
    print(f"\n{'='*50}")
    print(f"  Strategy: {strategy_name}")
    print(f"  Balance: ${balance:,.2f}")
    print(f"{'='*50}\n")

    # Read Symbols
    with open(SYMBOLS_PATH, "r") as f:
        symbols = [line.strip() for line in f if line.strip()]

    print(f"Found {len(symbols)} symbols to process.")
    
    # Create reports directory
    os.makedirs(REPORT_DIR, exist_ok=True)
    print(f"Reports will be saved to: {REPORT_DIR}")
    
    batch_results = []
    
    for symbol in symbols:
        print(f"\nProcessing {symbol}...")
        safe_symbol = symbol.replace('/', '')
        data_file = os.path.join(DATA_DIR, f"{safe_symbol}_{timeframe}.csv")
        
        # Download if missing
        if not os.path.exists(data_file):
            print(f"Data not found for {symbol}. Downloading...")
            try:
                # Default limit 10000 candles
                # Use safe_symbol (no slash) for binanceusdm
                download_data(safe_symbol, timeframe, 10000, DATA_DIR)
                
                if not os.path.exists(data_file):
                    print(f"Download failed for {symbol}. Skipping.")
                    continue
            except Exception as e:
                print(f"Error downloading {symbol}: {e}")
                continue

        # Run Backtest
        try:
            # Create a run-specific config with the correct symbol
            run_config = copy.deepcopy(config)
            run_config['symbols'] = [symbol]
            
            engine = BacktestEngine(data_file, strategy_class, run_config)
            # Re-init exchange with correct balance (engine uses config default)
            engine.exchange.initial_balance = Decimal(str(balance))
            engine.exchange.balance = Decimal(str(balance))
            
            engine.run()
            
            # Generate Report (Content Only)
            # Fix BacktestReporter init: (exchange, config, initial_balance, symbol, timeframe, strategy_name)
            reporter = BacktestReporter(
                engine.exchange, 
                config, 
                initial_balance=float(balance),
                symbol=symbol,
                timeframe=timeframe,
                strategy_name=strategy_name
            )
            
            # We need to access internal result generation logic
            df = pd.DataFrame(engine.exchange.trade_history)
            round_trips = reporter._build_round_trips(df)
            metrics = reporter._calculate_metrics(round_trips)
            drawdown = reporter._calculate_drawdown(round_trips)
            risk_metrics = reporter._calculate_risk_metrics(round_trips, drawdown)
            monthly_returns = reporter._calculate_monthly_returns(round_trips)
            
            final_bal = engine.exchange.get_balance()
            # Use sum of round_trips PnL for consistency with equity curve
            # This ensures realized P&L matches the equity chart 
            realized_pnl = float(round_trips['pnl'].sum()) if not round_trips.empty else 0.0
            profit = realized_pnl
            profit_pct = (profit / float(balance)) * 100
            
            html_content = reporter._generate_html_report(
                metrics, drawdown, risk_metrics, monthly_returns, 
                final_bal, profit, profit_pct, round_trips, 
                return_only=True,
                output_dir=REPORT_DIR
            )
            
            # Export CSVs to reports folder
            reporter._export_csv(df, round_trips, output_dir=REPORT_DIR)
            
            batch_results.append({
                'symbol': symbol,
                'metrics': metrics,
                'html': html_content,
                'profit': profit,
                'profit_pct': profit_pct,
                'initial_balance': float(balance),
                'final_balance': float(final_bal),
                'total_fees': float(engine.exchange.total_fees_paid) if hasattr(engine.exchange, 'total_fees_paid') else 0,
                'total_volume': float(engine.exchange.total_volume) if hasattr(engine.exchange, 'total_volume') else 0,
                'drawdown': drawdown.get('avg_drawdown_pct', 0),
                'trades': metrics.get('total_trades', 0),
                'round_trips': round_trips
            })
            
        except Exception as e:
            print(f"Error backtesting {symbol}: {e}")
            import traceback
            traceback.print_exc()

    # Generate Master Report
    if batch_results:
        generator = BatchHtmlGenerator(batch_results)
        report_path = os.path.join(REPORT_DIR, "batch_report.html")
        generator.generate(filename=report_path)
        
        print(f"Opening batch report: {report_path}")
        try:
            webbrowser.open('file://' + os.path.abspath(report_path))
        except:
            print("Could not open browser automatically.")
    else:
        print("No results to generate report.")

if __name__ == "__main__":
    main()
