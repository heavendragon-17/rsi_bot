import os
import sys
import yaml
import pandas as pd
import re
import webbrowser
import argparse
from decimal import Decimal
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
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
from app.core.logging import setup_logging
import logging

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


def debug_trade_structure(engine, symbol: str):
    """Debug function to inspect trade history structure."""
    print(f"\n{'='*60}")
    print(f"DEBUG: Trade History for {symbol}")
    print(f"{'='*60}")
    
    if hasattr(engine.exchange, 'trade_history'):
        history = engine.exchange.trade_history
        print(f"Number of trades: {len(history)}")
        
        if history:
            print(f"\n📋 First trade:")
            first = history[0]
            if isinstance(first, dict):
                for key, value in first.items():
                    value_str = str(value)[:50]  # Truncate long values
                    print(f"  {key:20s} = {value_str}")
            else:
                print(f"  Type: {type(first)}")
                print(f"  Value: {first}")
        else:
            print("⚠ Trade history is empty")
    else:
        print("⚠ No trade_history attribute")
    
    print(f"{'='*60}\n")


def export_signals_to_csv(engine, symbol: str, output_dir: str, debug: bool = False):
    """
    Export signals with robust timestamp handling.
    
    Args:
        engine: BacktestEngine instance
        symbol: Trading pair symbol
        output_dir: Output directory
        debug: Whether to print debug info
    
    Returns:
        str: Path to CSV file, or None if failed
    """
    if debug:
        debug_trade_structure(engine, symbol)
    
    signals = []
    
    # Method 1: Strategy has signal_history
    if hasattr(engine.strategy, 'signal_history'):
        signals = engine.strategy.signal_history
        if debug:
            print(f"[{symbol}] Using strategy.signal_history: {len(signals)} signals")
    
    # Method 2: Reconstruct from trade history
    elif hasattr(engine.exchange, 'trade_history'):
        trade_history = engine.exchange.trade_history
        
        if not trade_history:
            print(f"[{symbol}] ⚠ Trade history is empty")
            return None
        
        # Check what fields are available
        sample_trade = trade_history[0] if trade_history else {}
        available_fields = list(sample_trade.keys()) if isinstance(sample_trade, dict) else []
        
        if debug:
            print(f"[{symbol}] Available fields: {available_fields}")
        
        # Find timestamp field
        timestamp_field = None
        for field in ['timestamp', 'datetime', 'time', 'date', 'created_at', 'entry_time', 'exit_time']:
            if field in available_fields:
                timestamp_field = field
                break
        
        if debug and timestamp_field:
            print(f"[{symbol}] Using timestamp field: '{timestamp_field}'")
        elif debug:
            print(f"[{symbol}] ⚠ No timestamp field found!")
        
        # Process each trade
        for idx, trade in enumerate(trade_history):
            # Extract timestamp
            if timestamp_field and timestamp_field in trade:
                timestamp = trade[timestamp_field]
            elif 'id' in trade:
                timestamp = f"trade_{trade['id']}"
            else:
                timestamp = f"trade_{idx:04d}"
            
            # Convert datetime to string
            if isinstance(timestamp, datetime):
                timestamp = timestamp.strftime('%Y-%m-%d %H:%M:%S')
            elif isinstance(timestamp, pd.Timestamp):
                timestamp = timestamp.strftime('%Y-%m-%d %H:%M:%S')
            elif timestamp is None:
                timestamp = f"trade_{idx:04d}"
            
            # Build signal
            signal = {
                'timestamp': timestamp,
                'symbol': symbol,
                'trade_index': idx,  # Add index for reference
                'side': trade.get('side', 'unknown'),
                'signal_type': 'ENTRY' if trade.get('side') == 'buy' else 'EXIT',
                'price': float(trade.get('price', 0.0)),
                'amount': float(trade.get('amount', 0.0)),
                'order_type': trade.get('type', 'market'),
                'reason': trade.get('reason', 'unknown'),
            }
            
            # Add all other available fields
            for key, value in trade.items():
                if key not in signal and key != timestamp_field:
                    # Convert Decimal and complex types to string
                    if isinstance(value, Decimal):
                        signal[key] = float(value)
                    elif isinstance(value, (datetime, pd.Timestamp)):
                        signal[key] = value.strftime('%Y-%m-%d %H:%M:%S')
                    elif isinstance(value, (int, float, str, bool)):
                        signal[key] = value
                    else:
                        signal[key] = str(value)
            
            signals.append(signal)
        
        if debug:
            print(f"[{symbol}] Reconstructed {len(signals)} signals")
    
    else:
        print(f"[{symbol}] ⚠ No trade history found")
        return None
    
    # Export to CSV
    if signals:
        try:
            df = pd.DataFrame(signals)
            
            # Sort by timestamp or trade_index
            if 'timestamp' in df.columns:
                try:
                    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
                    df = df.sort_values('timestamp')
                except:
                    pass
            elif 'trade_index' in df.columns:
                df = df.sort_values('trade_index')
            
            # Save to CSV
            safe_symbol = symbol.replace('/', '_')
            csv_path = os.path.join(output_dir, f"signals_{safe_symbol}.csv")
            df.to_csv(csv_path, index=False)
            
            print(f"[{symbol}] [DONE] Signals exported: {csv_path}")
            print(f"[{symbol}]   -> {len(df)} signals, {len(df.columns)} columns")
            
            if debug:
                print(f"\n[{symbol}] Sample data (first 3 rows):")
                print(df.head(3).to_string(index=False, max_colwidth=40))
                print()
            
            return csv_path
            
        except Exception as e:
            print(f"[{symbol}] [ERROR] Export error: {e}")
            import traceback
            if debug:
                traceback.print_exc()
            return None
    
    return None

def run_single_backtest(symbol: str, config: dict, timeframe: str, balance: float, 
                         strategy_name: str, data_dir: str, report_dir: str) -> dict:
    """
    Run backtest for a single symbol. Designed to be called in a separate process.
    
    Returns a dict with results or None if failed.
    """
    # Configure logger for worker process
    setup_logging(level="INFO")
    
    try:
        # Import strategy class here to avoid pickling issues
        from app.strategies.rsi_wma_retest import RsiWmaRetestStrategy
        from app.strategies.rsi_no_retest import RsiNoRetestStrategy
        
        strategy_map = {
            "rsi_wma_retest": RsiWmaRetestStrategy,
            "rsi_no_retest": RsiNoRetestStrategy,
        }
        strategy_class = strategy_map.get(strategy_name)
        if not strategy_class:
            return {"symbol": symbol, "error": f"Unknown strategy: {strategy_name}"}
        
        safe_symbol = symbol.replace('/', '')
        data_file = os.path.join(data_dir, f"{safe_symbol}_{timeframe}.csv")
        
        # Download if missing
        if not os.path.exists(data_file):
            print(f"[{symbol}] Data not found. Downloading...")
            try:
                download_data(safe_symbol, timeframe, 8832, data_dir)
                if not os.path.exists(data_file):
                    return {"symbol": symbol, "error": "Download failed"}
            except Exception as e:
                return {"symbol": symbol, "error": f"Download error: {e}"}
        
        # Create run-specific config
        run_config = copy.deepcopy(config)
        run_config['symbols'] = [symbol]
        
        # Run backtest — returns pre-computed results dict
        engine = BacktestEngine(data_file, strategy_class, run_config)
        engine.exchange.initial_balance = Decimal(str(balance))
        engine.exchange.balance = Decimal(str(balance))
        results = engine.run()

        # **EXPORT SIGNALS TO CSV**
        export_signals_to_csv(engine, symbol, report_dir, debug=False)

        # Generate HTML and CSV reports via thin formatter
        leverage = run_config.get("risk", {}).get("leverage", 1)
        reporter = BacktestReporter(
            results,
            symbol=symbol,
            timeframe=timeframe,
            strategy_name=strategy_name,
            leverage=leverage,
        )

        html_content = reporter._generate_html_report(
            return_only=True,
            output_dir=report_dir,
        )

        # Export CSVs
        reporter._export_csv(output_dir=report_dir)

        metrics = results.get("metrics", {})
        profit = results.get("net_profit", 0.0)
        profit_pct = results.get("net_profit_pct", 0.0)
        drawdown_avg = results.get("drawdown", {}).get("avg_drawdown_pct", 0)

        print(f"[{symbol}] [OK] Completed - PnL: ${profit:.2f} ({profit_pct:+.1f}%)")

        # Convert round_trips list to DataFrame for BatchHtmlGenerator compatibility
        rt_list = results.get("round_trips", [])
        round_trips_df = pd.DataFrame(rt_list) if rt_list else pd.DataFrame()

        return {
            "symbol": symbol,
            "metrics": metrics,
            "html": html_content,
            "profit": profit,
            "profit_pct": profit_pct,
            "initial_balance": results.get("initial_balance", float(balance)),
            "final_balance": results.get("final_balance", float(balance)),
            "drawdown": drawdown_avg,
            "trades": metrics.get("total_trades", 0),
            "round_trips": round_trips_df,
        }
        
    except Exception as e:
        import traceback
        print(f"[{symbol}] ✗ Error: {e}")
        traceback.print_exc()
        return {"symbol": symbol, "error": str(e)}


def export_combined_signals(batch_results: list, output_dir: str):
    """
    Combine all individual signal CSV files into one master CSV.
    """
    all_signals = []
    
    for result in batch_results:
        symbol = result['symbol']
        safe_symbol = symbol.replace('/', '_')
        csv_path = os.path.join(output_dir, f"signals_{safe_symbol}.csv")
        
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            all_signals.append(df)
    
    if all_signals:
        combined_df = pd.concat(all_signals, ignore_index=True)
        
        # Sort by timestamp if available
        if 'timestamp' in combined_df.columns:
            combined_df = combined_df.sort_values('timestamp')
        
        master_path = os.path.join(output_dir, "all_signals_combined.csv")
        combined_df.to_csv(master_path, index=False)
        print(f"\n[DONE] Combined signals exported to: {master_path}")
        print(f"  Total signals: {len(combined_df)}")
        
        return master_path
    
    return None


# ... [Rest of BatchHtmlGenerator class remains the same] ...

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
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of parallel workers (default: CPU count)"
    )
    parser.add_argument(
        "--sequential",
        action="store_true",
        help="Run sequentially (disable parallelism)"
    )
    args = parser.parse_args()
    
    if not os.path.exists(SYMBOLS_PATH):
        print(f"Error: {SYMBOLS_PATH} not found.")
        return

    # Configure global logger for main process
    setup_logging(level="INFO")

    # Load Config
    config = load_config()
    timeframe = config.get("timeframe", "15m")
    balance = config.get("backtest", {}).get("initial_balance", 1000)
    
    # Get strategy from config or CLI override
    strategy_name = args.strategy or config.get("strategy", "rsi_wma_retest")
    if strategy_name not in STRATEGY_MAP:
        print(f"Error: Unknown strategy '{strategy_name}'. Available: {list(STRATEGY_MAP.keys())}")
        return
    
    # Read Symbols
    with open(SYMBOLS_PATH, "r") as f:
        symbols = [line.strip() for line in f if line.strip()]

    # Determine worker count
    max_workers = args.workers or min(os.cpu_count() or 4, len(symbols))
    if args.sequential:
        max_workers = 1
    
    print(f"\n{'='*50}")
    print(f"  Strategy: {strategy_name}")
    print(f"  Balance: ${balance:,.2f}")
    print(f"  Symbols: {len(symbols)}")
    print(f"  Workers: {max_workers} {'(sequential)' if max_workers == 1 else '(parallel)'}")
    print(f"{'='*50}\n")
    
    # Create reports directory
    os.makedirs(REPORT_DIR, exist_ok=True)
    print(f"Reports will be saved to: {REPORT_DIR}")
    
    batch_results = []
    
    import time
    start_time = time.time()
    
    if max_workers == 1:
        # Sequential execution (original behavior)
        for symbol in symbols:
            print(f"\nProcessing {symbol}...")
            result = run_single_backtest(
                symbol=symbol,
                config=config,
                timeframe=timeframe,
                balance=balance,
                strategy_name=strategy_name,
                data_dir=DATA_DIR,
                report_dir=REPORT_DIR
            )
            if result and "error" not in result:
                batch_results.append(result)
            elif result and "error" in result:
                print(f"[{symbol}] Error: {result['error']}")
    else:
        # Parallel execution using ProcessPoolExecutor
        print(f"\nStarting parallel backtest with {max_workers} workers...")
        
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            futures = {
                executor.submit(
                    run_single_backtest,
                    symbol=symbol,
                    config=config,
                    timeframe=timeframe,
                    balance=balance,
                    strategy_name=strategy_name,
                    data_dir=DATA_DIR,
                    report_dir=REPORT_DIR
                ): symbol
                for symbol in symbols
            }
            
            # Collect results as they complete
            completed = 0
            for future in as_completed(futures):
                symbol = futures[future]
                completed += 1
                try:
                    result = future.result()
                    if result and "error" not in result:
                        batch_results.append(result)
                        print(f"  [{completed}/{len(symbols)}] {symbol} completed")
                    elif result and "error" in result:
                        print(f"  [{completed}/{len(symbols)}] {symbol} failed: {result['error']}")
                except Exception as e:
                    print(f"  [{completed}/{len(symbols)}] {symbol} exception: {e}")
    
    elapsed = time.time() - start_time
    print(f"\nTotal time: {elapsed:.1f}s ({elapsed/len(symbols):.1f}s per symbol)")

    # **EXPORT COMBINED SIGNALS CSV**
    if batch_results:
        export_combined_signals(batch_results, REPORT_DIR)
    
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