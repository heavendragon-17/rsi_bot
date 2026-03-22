"""
CSS styles and chart JS builders for backtest HTML reports.
"""

import json

REPORT_CSS = """
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee;
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 {
            text-align: center;
            font-size: 2.5rem;
            margin-bottom: 30px;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .metric-card {
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            padding: 24px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.1);
        }
        .metric-card h3 {
            color: #888;
            font-size: 0.9rem;
            text-transform: uppercase;
            margin-bottom: 8px;
        }
        .metric-card .value {
            font-size: 2rem;
            font-weight: bold;
        }
        .positive { color: #4CAF50; }
        .negative { color: #F44336; }
        .chart-container {
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 30px;
            display: flex;
            justify-content: center;
        }
        .chart-wrapper-pie {
            max-width: 300px;
            width: 100%;
            margin: 0 auto;
        }
        .trades-layout {
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
            transition: opacity 0.2s;
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
        @media (max-width: 1000px) {
            .trades-layout { flex-direction: column; }
            .side-panel { width: 100%; }
        }
        .section-title {
            font-size: 1.5rem;
            margin: 30px 0 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid rgba(255,255,255,0.1);
        }
        .trades-table {
            width: 100%;
            border-collapse: collapse;
            background: rgba(255,255,255,0.02);
            border-radius: 12px;
            overflow: hidden;
        }
        .trades-table th, .trades-table td {
            padding: 12px 16px;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        .trades-table th {
            background: rgba(255,255,255,0.05);
            font-weight: 600;
            color: #888;
            text-transform: uppercase;
            font-size: 0.8rem;
        }
        .trades-table tr:hover {
            background: rgba(255,255,255,0.03);
        }
        .badge {
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
        }
        .badge-tp1 { background: #4CAF50; color: white; }
        .badge-tp2 { background: #8BC34A; color: white; }
        .badge-tp3 { background: #CDDC39; color: #333; }
        .badge-full_tp { background: #10B981; color: white; }
        .badge-sl, .badge-stop_loss { background: #F44336; color: white; }
        .badge-breakeven { background: #F59E0B; color: white; }
        .badge-manual { background: #9E9E9E; color: white; }
        .badge-tp1-sl { background: #FF9800; color: white; }
        .badge-tp2-sl { background: #06B6D4; color: white; }
        .badge-tp3-sl { background: #EC4899; color: white; }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
        }
        .stat-item {
            background: rgba(255,255,255,0.03);
            padding: 16px;
            border-radius: 8px;
        }
        .stat-item .label { color: #888; font-size: 0.85rem; }
        .stat-item .val { font-size: 1.25rem; font-weight: 600; margin-top: 4px; }
        .report-time {
            text-align: center;
            color: #666;
            margin-top: 30px;
            font-size: 0.85rem;
        }
"""


def build_chart_js(
    safe_symbol: str,
    labels: list,
    values: list,
    pie_colors: list,
    chart_dates: list,
    chart_balances: list,
    pnl_by_ticker: dict,
) -> str:
    """Build the Chart.js JavaScript for pie, equity, and ticker PnL charts."""
    return f"""
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

        document.querySelectorAll('.filter-pill').forEach(pill => {{
            pill.addEventListener('click', (e) => {{
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

        const tickerPnlData = {json.dumps(pnl_by_ticker)};
        if (Object.keys(tickerPnlData).length > 0) {{
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
"""
