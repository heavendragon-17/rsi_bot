"""
Batch HTML report generator.

Extracted from run_batch_analysis.py — generates a combined multi-symbol
HTML report with portfolio overview, equity curve, and per-symbol tabs.
"""
from __future__ import annotations

import re

import pandas as pd


class BatchHtmlGenerator:
    """Generate a combined batch backtest HTML report with portfolio overview."""

    def __init__(self, batch_results: list[dict]):
        """
        Parameters
        ----------
        batch_results : list[dict]
            Each dict must contain keys: symbol, metrics, html, profit,
            profit_pct, initial_balance, final_balance, drawdown, trades,
            round_trips (pd.DataFrame).
        """
        self.results = batch_results

    def _extract_body_content(self, html_doc: str) -> str:
        match = re.search(r"<body.*?>(.*?)</body>", html_doc, re.DOTALL)
        return match.group(1) if match else html_doc

    def generate(self, filename: str = "batch_report.html") -> None:
        total_pnl = sum(r["profit"] for r in self.results)
        total_initial = sum(r["initial_balance"] for r in self.results)
        total_final = sum(r["final_balance"] for r in self.results)
        portfolio_return = (
            ((total_final - total_initial) / total_initial) * 100 if total_initial > 0 else 0
        )
        avg_drawdown = (
            sum(r["drawdown"] for r in self.results) / len(self.results) if self.results else 0
        )
        total_trades = sum(r["trades"] for r in self.results)

        equity_values, equity_labels = self._build_equity_data(total_initial)
        nav_html = self._build_nav()
        content_html = self._build_overview(
            total_pnl, portfolio_return, avg_drawdown, total_trades, equity_values, equity_labels,
        )
        content_html += self._build_symbol_tabs()

        full_html = _HTML_TEMPLATE.format(
            nav_html=nav_html,
            content_html=content_html,
            equity_labels=equity_labels,
            equity_values=equity_values,
        )

        with open(filename, "w", encoding="utf-8") as f:
            f.write(full_html)

    # ── helpers ─────────────────────────────────────────────────────────

    def _build_equity_data(self, total_initial: float):
        all_trades: list[pd.DataFrame] = []
        for r in self.results:
            if "round_trips" in r and not r["round_trips"].empty:
                t = r["round_trips"].copy()
                t["symbol"] = r["symbol"]
                t["exit_time"] = pd.to_datetime(t["exit_time"])
                all_trades.append(t)

        equity_values = [total_initial]
        equity_labels = ["Start"]

        if all_trades:
            combined = pd.concat(all_trades).sort_values("exit_time")
            current = total_initial
            for _, row in combined.iterrows():
                current += row["pnl"]
                equity_values.append(current)
                equity_labels.append(row["exit_time"].strftime("%Y-%m-%d %H:%M"))

        return equity_values, equity_labels

    def _build_nav(self) -> str:
        parts = [
            '<div class="nav-sidebar">',
            '  <div class="nav-brand">RSI Bot Batch</div>',
            '  <button class="nav-item active" onclick="openTab(event, \'Overview\')">',
            '    <span class="icon">📊</span> Overview',
            "  </button>",
        ]
        for res in self.results:
            clean = res["symbol"].replace("/", "")
            cls = "positive" if res["profit"] >= 0 else "negative"
            parts.append(
                f'  <button class="nav-item" onclick="openTab(event, \'{clean}\')">'
                f'    <span class="icon">📈</span> {res["symbol"]}'
                f'    <span class="nav-badge {cls}">{res["profit_pct"]:+.1f}%</span>'
                f"  </button>"
            )
        parts.append("</div>")
        return "\n".join(parts)

    def _build_overview(
        self, total_pnl, portfolio_return, avg_drawdown, total_trades,
        equity_values, equity_labels,
    ) -> str:
        pnl_cls = "positive" if total_pnl >= 0 else "negative"
        ret_cls = "positive" if portfolio_return >= 0 else "negative"

        rows = ""
        for res in self.results:
            c = "positive" if res["profit"] >= 0 else "negative"
            rows += (
                f"<tr>"
                f'<td><strong>{res["symbol"]}</strong></td>'
                f'<td class="{c}">${res["profit"]:.2f}</td>'
                f'<td class="{c}">{res["profit_pct"]:+.2f}%</td>'
                f'<td>{res["drawdown"]:.2f}%</td>'
                f'<td>{res["trades"]}</td>'
                f'<td>{res["metrics"].get("win_rate", 0.0):.1f}%</td>'
                f"</tr>"
            )

        return (
            f'<div id="Overview" class="tab-content active" style="display:block;">'
            f"<div class=\"header-section\"><h1>Portfolio Overview</h1>"
            f'<p>Aggregated performance across {len(self.results)} pairs</p></div>'
            f'<div class="metrics-grid">'
            f'<div class="metric-card"><h3>Total Net Profit</h3>'
            f'<div class="value {pnl_cls}">${total_pnl:,.2f}</div></div>'
            f'<div class="metric-card"><h3>Portfolio Return</h3>'
            f'<div class="value {ret_cls}">{portfolio_return:+.2f}%</div></div>'
            f'<div class="metric-card"><h3>Avg Drawdown</h3>'
            f'<div class="value negative">{avg_drawdown:.2f}%</div></div>'
            f'<div class="metric-card"><h3>Total Trades</h3>'
            f'<div class="value">{total_trades}</div></div>'
            f"</div>"
            f'<h2 class="section-title">Portfolio Equity Curve</h2>'
            f'<div class="chart-container" style="height:400px;position:relative;">'
            f'<canvas id="portfolioEquityChart"></canvas></div>'
            f'<h2 class="section-title">Performance Comparison</h2>'
            f'<div class="table-container"><table class="trades-table">'
            f"<thead><tr><th>Symbol</th><th>PnL ($)</th><th>Return (%)</th>"
            f"<th>Drawdown</th><th>Trades</th><th>Win Rate</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div></div>"
        )

    def _build_symbol_tabs(self) -> str:
        parts: list[str] = []
        for res in self.results:
            clean = res["symbol"].replace("/", "")
            body = self._extract_body_content(res["html"])
            parts.append(
                f'<div id="{clean}" class="tab-content" style="display:none;">{body}</div>'
            )
        return "\n".join(parts)


# ── HTML template ───────────────────────────────────────────────────────────

_HTML_TEMPLATE = """<!DOCTYPE html>
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
    font-size: 1.2rem; font-weight: bold;
    margin-bottom: 30px; color: var(--accent); text-align: center;
}}
.nav-item {{
    display: flex; align-items: center; width: 100%;
    padding: 12px 15px; background: transparent; border: none;
    color: var(--text-muted); cursor: pointer; text-align: left;
    border-radius: 8px; margin-bottom: 5px; transition: all 0.2s;
}}
.nav-item:hover, .nav-item.active {{
    background: var(--bg-card); color: var(--text-main);
}}
.nav-item .icon {{ margin-right: 10px; }}
.nav-badge {{
    margin-left: auto; font-size: 0.75rem;
    padding: 2px 6px; border-radius: 4px;
}}
.main-content {{
    margin-left: 250px; flex: 1; padding: 40px; overflow-x: hidden;
}}
.container {{ max-width: 1200px; margin: 0 auto; }}
.metrics-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 20px; margin-bottom: 30px;
}}
.metric-card {{
    background: var(--bg-card); border-radius: 16px;
    padding: 24px; border: 1px solid rgba(255,255,255,0.1);
}}
.metric-card h3 {{ color: var(--text-muted); font-size: 0.9rem; margin-bottom: 10px; }}
.metric-card .value {{ font-size: 1.8rem; font-weight: bold; }}
.positive {{ color: #4CAF50 !important; }}
.negative {{ color: #F44336 !important; }}
.section-title {{
    font-size: 1.5rem; margin: 40px 0 20px;
    padding-bottom: 10px; border-bottom: 1px solid rgba(255,255,255,0.1);
}}
.trades-table {{
    width: 100%; border-collapse: collapse;
    background: var(--bg-card); border-radius: 12px; overflow: hidden;
}}
.trades-table th, .trades-table td {{
    padding: 15px; text-align: left;
    border-bottom: 1px solid rgba(255,255,255,0.05);
}}
.trades-table th {{ background: rgba(255,255,255,0.05); color: var(--text-muted); }}
.tab-content {{ animation: fadeIn 0.3s ease; }}
@keyframes fadeIn {{
    from {{ opacity: 0; transform: translateY(10px); }}
    to {{ opacity: 1; transform: translateY(0); }}
}}
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
    background: var(--bg-card); padding: 20px;
    border-radius: 16px; margin-bottom: 30px; min-height: 300px;
}}
.header-section {{ margin-bottom: 40px; }}
.chart-wrapper {{ max-width: 300px; width: 100%; margin: 0 auto; }}
</style>
</head>
<body>
{nav_html}
<div class="main-content">
{content_html}
</div>
<script>
function openTab(evt, tabName) {{
    var i, tc, tl;
    tc = document.getElementsByClassName("tab-content");
    for (i = 0; i < tc.length; i++) {{ tc[i].style.display = "none"; tc[i].classList.remove("active"); }}
    tl = document.getElementsByClassName("nav-item");
    for (i = 0; i < tl.length; i++) {{ tl[i].className = tl[i].className.replace(" active", ""); }}
    document.getElementById(tabName).style.display = "block";
    document.getElementById(tabName).classList.add("active");
    evt.currentTarget.className += " active";
}}
document.addEventListener('DOMContentLoaded', function() {{
    var ctx = document.getElementById('portfolioEquityChart').getContext('2d');
    new Chart(ctx, {{
        type: 'line',
        data: {{
            labels: {equity_labels},
            datasets: [{{
                label: 'Total Portfolio Value ($)',
                data: {equity_values},
                borderColor: '#667eea',
                backgroundColor: 'rgba(102, 126, 234, 0.1)',
                fill: true, tension: 0.2, pointRadius: 2, pointHoverRadius: 5
            }}]
        }},
        options: {{
            responsive: true, maintainAspectRatio: false,
            interaction: {{ mode: 'index', intersect: false }},
            plugins: {{
                title: {{ display: true, text: 'Total Portfolio Equity (Realized)', color: '#eee', font: {{ size: 16 }} }},
                legend: {{ labels: {{ color: '#eee' }} }}
            }},
            scales: {{
                x: {{ title: {{ display: true, text: 'Time', color: '#888' }}, ticks: {{ color: '#888', maxTicksLimit: 12 }}, grid: {{ color: 'rgba(255,255,255,0.05)' }} }},
                y: {{ title: {{ display: true, text: 'Equity ($)', color: '#888' }}, ticks: {{ color: '#888' }}, grid: {{ color: 'rgba(255,255,255,0.05)' }} }}
            }}
        }}
    }});
}});
</script>
</body>
</html>"""
