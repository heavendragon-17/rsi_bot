import json
import re
import os

filepath = "d:/GitHub/rsi_bot/app/backtest/reporting.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Make sure json is imported
if "import json" not in content:
    content = "import json\n" + content

# 1. Update Metrics
metrics_target = """            <div class="metric-card">
                <h3>Volatility</h3>
                <div class="value">{risk_metrics.get('volatility', 0):.2f}%</div>
                <div style="color:#888; font-size:0.75rem; margin-top:4px;">Trade return std dev</div>
            </div>
            <div class="metric-card">
                <h3>VaR (95%)</h3>
                <div class="value negative">{risk_metrics.get('var_95', 0):.2f}%</div>
                <div style="color:#888; font-size:0.75rem; margin-top:4px;">Max loss at 95% confidence</div>
            </div>
        </div>"""

metrics_replacement = """            <div class="metric-card">
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
        </div>"""

if metrics_target in content:
    content = content.replace(metrics_target, metrics_replacement)
else:
    print("Could not find metrics_target")

# 2. Table Logic
table_logic_target = '''        # Build trades table HTML
        if not round_trips_df.empty:
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
            for i, row in round_trips_df.iterrows():
                pnl_class = "positive" if row["pnl"] > 0 else "negative"
                hold_hours = row.get("hold_duration_hours")
                exit_reason = str(row.get("exit_reason", "UNKNOWN"))
                trades_table_html += f"""
                    <tr>
                        <td>{i + 1}</td>
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
            trades_table_html += "</tbody></table>"
        else:'''

table_logic_replacement = '''        unique_symbols = []
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
        else:'''

if table_logic_target in content:
    content = content.replace(table_logic_target, table_logic_replacement)
else:
    print("Could not find table_logic_target")

# 3. CSS
css_target = '''        .chart-wrapper {
            max-width: 300px;
            width: 100%;
            margin: 0 auto;
        }'''
css_replacement = '''        .trades-layout {
            display: flex;
            gap: 20px;
            align-items: flex-start;
        }
        .trades-table-container {
            flex: 1;
            overflow-x: auto;
        }
        .side-panel {
            width: 300px;
            background: rgba(255,255,255,0.02);
            border-radius: 12px;
            padding: 16px;
            border: 1px solid rgba(255,255,255,0.05);
            flex-shrink: 0;
            max-height: 800px;
            overflow-y: auto;
        }
        .side-panel::-webkit-scrollbar {
            width: 8px;
        }
        .side-panel::-webkit-scrollbar-thumb {
            background-color: rgba(255,255,255,0.1);
            border-radius: 4px;
        }
        .side-panel h3 {
            margin-bottom: 16px;
            padding-bottom: 10px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        .sym-stat-card {
            background: rgba(255,255,255,0.03);
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 12px;
        }
        .ticker-badge {
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: bold;
            color: white;
            display: inline-block;
        }
        .filter-bar {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 16px;
        }
        .filter-pill {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            color: #ccc;
            padding: 6px 16px;
            border-radius: 20px;
            cursor: pointer;
            transition: all 0.2s;
            font-size: 0.85rem;
        }
        .filter-pill:hover {
            background: rgba(255,255,255,0.1);
            color: white;
        }
        .filter-pill.active {
            background: #3B82F6;
            color: white;
            border-color: #3B82F6;
        }
        .chart-wrapper {
            width: 100%;
            margin: 0 auto;
        }
        .chart-wrapper-pie {
            max-width: 300px;
            width: 100%;
            margin: 0 auto;
        }
        @media (max-width: 1000px) {
            .trades-layout { flex-direction: column; }
            .side-panel { width: 100%; }
        }'''
if css_target in content:
    content = content.replace(css_target, css_replacement)
else:
    print("Could not find css_target")

content = content.replace('<div class="chart-wrapper">', '<div class="chart-wrapper-pie">')


# 4. JS
js_target = '''        });
        })();
    </script>'''

js_replacement = '''        });

        // Ticker filter logic
        document.querySelectorAll('.filter-pill').forEach(pill => {
            pill.addEventListener('click', (e) => {
                // Update active state
                document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
                e.target.classList.add('active');
                
                const selectedSym = e.target.getAttribute('data-symbol');
                const rows = document.querySelectorAll('#tradesTable tbody tr');
                
                rows.forEach(row => {
                    if (selectedSym === 'ALL' || row.getAttribute('data-symbol') === selectedSym) {
                        row.style.display = '';
                    } else {
                        row.style.display = 'none';
                    }
                });

                // Also dim the non-selected stats in the side panel
                const cards = document.querySelectorAll('.sym-stat-card');
                cards.forEach(card => {
                    if (selectedSym === 'ALL' || card.getAttribute('data-symbol') === selectedSym) {
                        card.style.opacity = '1';
                    } else {
                        card.style.opacity = '0.3';
                    }
                });
            });
        });

        // Ticker PnL Bar Chart
        const tickerPnlData = {json.dumps(pnl_by_ticker)};
        if (Object.keys(tickerPnlData).length > 0) {
            // Sort by PnL
            const sortedTickers = Object.entries(tickerPnlData).sort((a, b) => b[1] - a[1]);
            const tLabels = sortedTickers.map(t => t[0]);
            const tData = sortedTickers.map(t => t[1]);
            const tColors = tData.map(v => v >= 0 ? 'rgba(76, 175, 80, 0.7)' : 'rgba(244, 67, 54, 0.7)');
            const tBorder = tData.map(v => v >= 0 ? '#4CAF50' : '#F44336');

            const barCtx = document.getElementById('tickerPnlChart_{safe_symbol}').getContext('2d');
            new Chart(barCtx, {
                type: 'bar',
                data: {
                    labels: tLabels,
                    datasets: [{
                        label: 'Net PnL ($)',
                        data: tData,
                        backgroundColor: tColors,
                        borderColor: tBorder,
                        borderWidth: 1
                    }]
                },
                options: {
                    indexAxis: 'y',
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        title: {
                            display: true,
                            text: 'PnL by Ticker',
                            color: '#eee',
                            font: { size: 16 }
                        }
                    },
                    scales: {
                        x: {
                            title: { display: true, text: 'PnL ($)', color: '#888' },
                            ticks: { color: '#888' },
                            grid: { color: 'rgba(255,255,255,0.05)' }
                        },
                        y: {
                            ticks: { color: '#888' },
                            grid: { display: false }
                        }
                    }
                }
            });
        }
        })();
    </script>'''

if js_target in content:
    content = content.replace(js_target, js_replacement)
else:
    print("Could not find js_target")

# 5. PnL Chart HTML injection
pnl_chart_target = '''        <h2 class="section-title">Trade Details</h2>'''
pnl_chart_replacement = '''        <h2 class="section-title">Per-Symbol PnL</h2>
        <div class="chart-container" style="height: {math.max(300, len(unique_symbols) * 30)}px;">
            <canvas id="tickerPnlChart_{safe_symbol}"></canvas>
        </div>

        <h2 class="section-title">Trade Details</h2>'''
# Need import math for the height calculation above
content = "import math\n" + content

if pnl_chart_target in content:
    content = content.replace(pnl_chart_target, pnl_chart_replacement)
else:
    print("Could not find pnl_chart_target")


with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("Saved successfully.")
