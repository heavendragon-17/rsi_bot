"""
HTML report generation for backtest results.
Extracted from BacktestReporter._generate_html_report().
"""
import os
import numpy as np
import pandas as pd
import structlog
from datetime import datetime

from app.backtest.reporting_styles import REPORT_CSS, build_chart_js

logger = structlog.get_logger()

EXIT_REASON_COLORS = {
    "TP1": "#22C55E", "TP2": "#3B82F6", "TP3": "#8B5CF6",
    "FULL_TP": "#10B981", "SL": "#EF4444", "STOP_LOSS": "#EF4444",
    "BREAKEVEN": "#F59E0B", "MANUAL": "#6B7280", "TP1+SL": "#F59E0B",
    "TP2+SL": "#06B6D4", "TP3+SL": "#EC4899", "UNKNOWN": "#64748B",
    "No Trades": "#9CA3AF",
}

TICKER_PALETTE = [
    "#3B82F6", "#EF4444", "#10B981", "#F59E0B", "#8B5CF6",
    "#EC4899", "#06B6D4", "#F97316", "#14B8A6", "#84CC16",
]


def format_duration(hours: float) -> str:
    """Format hours into human-readable duration."""
    if hours is None or (isinstance(hours, float) and np.isnan(hours)):
        return "N/A"
    if hours < 1:
        return f"{hours * 60:.0f}m"
    if hours < 24:
        return f"{hours:.1f}h"
    return f"{hours / 24:.1f}d"


def _render_params_badges(strategy_params: dict) -> str:
    """Render key strategy params as small info badges."""
    p = strategy_params
    items = []
    if "nr_max_above_ema21" in p:
        items.append(
            f'<span style="background:rgba(251,146,60,0.15); color:#fb923c; border:1px solid rgba(251,146,60,0.35); '
            f'padding:4px 12px; border-radius:20px; font-size:0.8rem; font-weight:600;">'
            f'max_above_ema21: {p["nr_max_above_ema21"]}</span>'
        )
    if "nr_rsi_spread_min" in p:
        items.append(
            f'<span style="background:rgba(34,211,238,0.12); color:#22d3ee; border:1px solid rgba(34,211,238,0.3); '
            f'padding:4px 12px; border-radius:20px; font-size:0.8rem; font-weight:600;">'
            f'rsi_spread_min: {p["nr_rsi_spread_min"]}</span>'
        )
    if not items:
        return '<p style="margin-bottom:20px;"></p>'
    badges = " ".join(items)
    return (
        f'<p style="text-align:center; margin-bottom:24px; display:flex; '
        f'gap:8px; justify-content:center; flex-wrap:wrap;">{badges}</p>'
    )


def _build_ticker_data(round_trips_df):
    """Build per-ticker statistics, filter pills, and side panel HTML."""
    if round_trips_df.empty or "symbol" not in round_trips_df.columns:
        return [], {}, "N/A", "$0.00", "N/A", "$0.00", "", ""

    unique_symbols = sorted(round_trips_df["symbol"].unique().tolist())
    ticker_colors = {sym: TICKER_PALETTE[hash(sym) % len(TICKER_PALETTE)] for sym in unique_symbols}
    pnl_series = round_trips_df.groupby("symbol")["pnl"].sum()
    pnl_by_ticker = pnl_series.to_dict()

    best_ticker_name, best_ticker_pnl = "N/A", "$0.00"
    worst_ticker_name, worst_ticker_pnl = "N/A", "$0.00"
    if len(pnl_series) > 0:
        best_sym = pnl_series.idxmax()
        worst_sym = pnl_series.idxmin()
        best_ticker_name, best_ticker_pnl = best_sym, f"${pnl_series[best_sym]:+.2f}"
        worst_ticker_name, worst_ticker_pnl = worst_sym, f"${pnl_series[worst_sym]:+.2f}"

    per_symbol_html = '<div class="side-panel"><h3>Stats by Ticker</h3><div class="side-panel-inner">'
    for sym in unique_symbols:
        sym_df = round_trips_df[round_trips_df["symbol"] == sym]
        sym_trades = len(sym_df)
        sym_wins = len(sym_df[sym_df["pnl"] > 0])
        sym_wr = (sym_wins / sym_trades * 100) if sym_trades > 0 else 0
        sym_pnl = sym_df["pnl"].sum()
        sym_hold = sym_df["hold_duration_hours"].mean()
        pnl_class = "positive" if sym_pnl >= 0 else "negative"
        per_symbol_html += f"""
            <div class="sym-stat-card" data-symbol="{sym}">
                <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                    <span class="ticker-badge" style="background-color: {ticker_colors[sym]}">{sym}</span>
                    <span class="{pnl_class}" style="font-weight:bold;">${sym_pnl:.2f}</span>
                </div>
                <div style="color:#888; font-size:0.8rem;">
                    {sym_trades} trades | {sym_wr:.1f}% WR | {format_duration(sym_hold)} avg hold
                </div>
            </div>"""
    per_symbol_html += '</div></div>'

    pills = '<div class="filter-bar"><button class="filter-pill active" data-symbol="ALL">All Tickers</button>'
    for sym in unique_symbols:
        pills += f'<button class="filter-pill" data-symbol="{sym}">{sym}</button>'
    pills += '</div>'

    return unique_symbols, pnl_by_ticker, best_ticker_name, best_ticker_pnl, worst_ticker_name, worst_ticker_pnl, per_symbol_html, pills


def _build_trades_table(round_trips_df, ticker_colors, ticker_pills_html, per_symbol_stats_html):
    """Build the HTML trades table."""
    if round_trips_df.empty:
        return "<p>No completed trades.</p>"

    has_rsi_ema9 = "entry_rsi_ema9" in round_trips_df.columns
    has_rsi_wma45 = "entry_rsi_wma45" in round_trips_df.columns
    has_spread = "entry_spread" in round_trips_df.columns
    has_above = "above_count" in round_trips_df.columns

    html = f"""{ticker_pills_html}
        <div class="trades-layout"><div class="trades-table-container">
        <table class="trades-table" id="tradesTable"><thead><tr>
            <th>#</th>{"<th>Symbol</th>" if "symbol" in round_trips_df.columns else ""}
            <th>Entry Time</th><th>Exit Time</th><th>Entry $</th><th>Exit $</th><th>Avg Exit $</th>
            <th>PnL</th><th>PnL %</th><th>Hold Time</th><th>Exit Reason</th>
            {"<th title='RSI EMA9 value at entry'>RSI EMA9</th>" if has_rsi_ema9 else ""}
            {"<th title='RSI WMA45 value at entry'>RSI WMA45</th>" if has_rsi_wma45 else ""}
            {"<th title='RSI EMA9 - RSI WMA45 at entry'>Spread</th>" if has_spread else ""}
            {"<th title='Candles above EMA21 in lookback at entry'>Above EMA21</th>" if has_above else ""}
        </tr></thead><tbody>"""

    for i, row in round_trips_df.iterrows():
        pnl_class = "positive" if row["pnl"] > 0 else "negative"
        hold_hours = row.get("hold_duration_hours")
        exit_reason = str(row.get("exit_reason", "UNKNOWN"))
        sym_col, row_attr = "", ""
        if "symbol" in row:
            sym = row['symbol']
            sym_col = f'<td><span class="ticker-badge" style="background-color: {ticker_colors.get(sym, "#666")}">{sym}</span></td>'
            row_attr = f'data-symbol="{sym}"'

        def _opt_col(key, fmt, has_flag):
            val = row.get(key)
            if not has_flag:
                return ""
            if val is not None:
                return f'<td>{fmt.format(val)}</td>'
            return "<td>-</td>"

        html += f"""<tr {row_attr}>
            <td>{i + 1}</td>{sym_col}
            <td>{row['entry_time']}</td><td>{row['exit_time']}</td>
            <td>${row['entry_price']:.6f}</td><td>${row['exit_price']:.6f}</td><td>${row['avg_exit_price']:.6f}</td>
            <td class="{pnl_class}">${row['pnl']:.2f}</td>
            <td class="{pnl_class}">{row['pnl_pct']:.2f}%</td>
            <td>{format_duration(hold_hours)}</td>
            <td><span class="badge badge-{exit_reason.lower().replace('+', '-')}">{exit_reason}</span></td>
            {_opt_col("entry_rsi_ema9", "{:.2f}", has_rsi_ema9)}
            {_opt_col("entry_rsi_wma45", "{:.2f}", has_rsi_wma45)}
            {_opt_col("entry_spread", "{:.2f}", has_spread)}
            {_opt_col("above_count", "{:.0f}", has_above)}
        </tr>"""

    html += "</tbody></table></div>" + per_symbol_stats_html + "</div>"
    return html


def generate_html_report(
    results: dict,
    symbol: str,
    timeframe: str,
    strategy_name: str,
    leverage: int = 1,
    strategy_params: dict | None = None,
    return_only: bool = False,
    output_dir: str = ".",
) -> str | None:
    """Generate a full HTML backtest report. Returns path or HTML string."""
    strategy_params = strategy_params or {}
    metrics = results.get("metrics", {})
    drawdown = results.get("drawdown", {})
    risk_metrics = results.get("risk_metrics", {})
    monthly_returns = results.get("monthly_returns", {})
    initial_balance = results.get("initial_balance", 0.0)
    final_balance = results.get("final_balance", 0.0)
    profit = results.get("net_profit", 0.0)
    profit_pct = results.get("net_profit_pct", 0.0)

    equity_pts = results.get("equity_curve", [{"date": "", "balance": initial_balance}])
    chart_dates = [pt["date"] for pt in equity_pts]
    chart_balances = [pt["balance"] for pt in equity_pts]

    rt_list = results.get("round_trips", [])
    round_trips_df = pd.DataFrame(rt_list) if rt_list else pd.DataFrame()
    safe_symbol = symbol.replace("/", "")

    pf_display = f"{metrics['profit_factor']:.2f}" if metrics and metrics.get("profit_factor") != float("inf") else "INF"
    rr_display = f"{metrics['risk_reward']:.2f}" if metrics and metrics.get("risk_reward") != float("inf") else "INF"

    exit_data = metrics.get("exit_reason_counts", {}) if metrics else {}
    labels = list(exit_data.keys()) if exit_data else ["No Trades"]
    values = list(exit_data.values()) if exit_data else [1]
    pie_colors = [EXIT_REASON_COLORS.get(lbl, "#64748B") for lbl in labels]

    (unique_symbols, pnl_by_ticker, best_name, best_pnl,
     worst_name, worst_pnl, per_sym_html, ticker_pills) = _build_ticker_data(round_trips_df)

    ticker_colors = {sym: TICKER_PALETTE[hash(sym) % len(TICKER_PALETTE)] for sym in unique_symbols}
    trades_table = _build_trades_table(round_trips_df, ticker_colors, ticker_pills, per_sym_html)

    monthly_rows = ""
    if monthly_returns:
        for month, data in monthly_returns.items():
            cls = "positive" if data["pnl"] >= 0 else "negative"
            monthly_rows += f'<tr><td>{month}</td><td>{data["trades"]}</td><td class="{cls}">${data["pnl"]:.2f}</td><td class="{cls}">{data["pnl_pct"]:+.2f}%</td></tr>'
    else:
        monthly_rows = '<tr><td colspan="4" style="text-align:center;color:#888;">No monthly data</td></tr>'

    chart_js = build_chart_js(safe_symbol, labels, values, pie_colors, chart_dates, chart_balances, pnl_by_ticker)
    params_badges = _render_params_badges(strategy_params)

    win_metrics_block = ""
    if metrics:
        win_metrics_block = f"""<div class="metrics-grid">
            <div class="metric-card"><h3>Win Rate</h3><div class="value">{metrics['win_rate']:.1f}%</div><div style="color:#888; margin-top:4px;">{metrics['win_count']}W / {metrics['loss_count']}L</div></div>
            <div class="metric-card"><h3>Profit Factor</h3><div class="value">{pf_display}</div></div>
            <div class="metric-card"><h3>Expectancy</h3><div class="value">${metrics['expectancy']:.2f}</div></div>
            <div class="metric-card"><h3>Avg Hold Time</h3><div class="value">{format_duration(metrics['avg_hold_hours'])}</div></div>
        </div>"""

    additional_block = ""
    if metrics:
        additional_block = f"""<h2 class="section-title">Additional Stats</h2><div class="metrics-grid">
            <div class="metric-card"><h3>Average Win</h3><div class="value positive">${metrics['avg_win']:.2f}</div></div>
            <div class="metric-card"><h3>Average Loss</h3><div class="value negative">${metrics['avg_loss']:.2f}</div></div>
            <div class="metric-card"><h3>Largest Win</h3><div class="value positive">${metrics['largest_win']:.2f}</div></div>
            <div class="metric-card"><h3>Largest Loss</h3><div class="value negative">${metrics['largest_loss']:.2f}</div></div>
            <div class="metric-card"><h3>Risk/Reward</h3><div class="value">{rr_display}</div></div>
            <div class="metric-card"><h3>Max Consec. Wins</h3><div class="value">{metrics['max_consec_wins']}</div></div>
            <div class="metric-card"><h3>Max Consec. Losses</h3><div class="value">{metrics['max_consec_losses']}</div></div>
            <div class="metric-card"><h3>Gross Profit</h3><div class="value positive">${metrics['gross_profit']:.2f}</div></div>
            <div class="metric-card"><h3>Gross Loss</h3><div class="value negative">${metrics['gross_loss']:.2f}</div></div>
        </div>"""

    avg_trades_sym = f"{metrics.get('total_trades', 0) / len(unique_symbols):.1f}" if unique_symbols else "0"

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Backtest Report</title><script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>{REPORT_CSS}</style></head>
<body><div class="container">
    <h1>{symbol} ({timeframe})</h1>
    <p style="text-align:center; color:#888; margin-top:-20px; margin-bottom:10px;">Backtest Report</p>
    <p style="text-align:center; margin-bottom:10px;">
        <span style="background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); padding: 6px 16px; border-radius: 20px; font-size: 0.9rem; font-weight: 600; margin-right: 10px;">Strategy: {strategy_name}</span>
        <span style="background: linear-gradient(90deg, #f093fb 0%, #f5576c 100%); padding: 6px 16px; border-radius: 20px; font-size: 0.9rem; font-weight: 600;">Leverage: {leverage}x</span>
    </p>
    {params_badges}
    <div class="metrics-grid">
        <div class="metric-card"><h3>Initial Balance</h3><div class="value">${initial_balance:,.2f}</div></div>
        <div class="metric-card"><h3>Final Balance</h3><div class="value">${final_balance:,.2f}</div></div>
        <div class="metric-card"><h3>Net Profit/Loss</h3><div class="value {'positive' if profit >= 0 else 'negative'}">${profit:+,.2f} ({profit_pct:+.1f}%)</div></div>
        <div class="metric-card"><h3>Max Drawdown</h3><div class="value negative">{drawdown.get('max_drawdown_pct', 0):.2f}%</div></div>
        <div class="metric-card"><h3>Avg Drawdown</h3><div class="value negative">{drawdown.get('avg_drawdown_pct', 0):.2f}%</div></div>
        <div class="metric-card"><h3>Max DD Duration</h3><div class="value">{drawdown.get('max_dd_duration', 0)} trades</div></div>
    </div>
    <h2 class="section-title">Risk-Adjusted Metrics</h2>
    <div class="metrics-grid">
        <div class="metric-card"><h3>Sharpe Ratio</h3><div class="value">{risk_metrics.get('sharpe_ratio', 0):.2f}</div><div style="color:#888; font-size:0.75rem; margin-top:4px;">Risk-adjusted return</div></div>
        <div class="metric-card"><h3>Sortino Ratio</h3><div class="value">{risk_metrics.get('sortino_ratio', 0):.2f}</div><div style="color:#888; font-size:0.75rem; margin-top:4px;">Downside risk-adjusted</div></div>
        <div class="metric-card"><h3>Calmar Ratio</h3><div class="value">{risk_metrics.get('calmar_ratio', 0):.2f}</div><div style="color:#888; font-size:0.75rem; margin-top:4px;">Return vs max drawdown</div></div>
        <div class="metric-card"><h3>Volatility</h3><div class="value">{risk_metrics.get('volatility', 0):.2f}%</div><div style="color:#888; font-size:0.75rem; margin-top:4px;">Trade return std dev</div></div>
        <div class="metric-card"><h3>Total Symbols</h3><div class="value">{len(unique_symbols)}</div><div style="color:#888; font-size:0.75rem; margin-top:4px;">Traded in period</div></div>
        <div class="metric-card"><h3>Avg Trades/Symbol</h3><div class="value">{avg_trades_sym}</div><div style="color:#888; font-size:0.75rem; margin-top:4px;">Activity balance</div></div>
    </div>
    <div class="metrics-grid">
        <div class="metric-card"><h3>Total Trades</h3><div class="value">{metrics.get('total_trades', 0)}</div><div style="color:#888; font-size:0.75rem; margin-top:4px;">Period volume</div></div>
        <div class="metric-card"><h3>Best Ticker</h3><div class="value positive">{best_name}</div><div style="color:#888; font-size:0.75rem; margin-top:4px;">{best_pnl}</div></div>
        <div class="metric-card"><h3>Worst Ticker</h3><div class="value negative">{worst_name}</div><div style="color:#888; font-size:0.75rem; margin-top:4px;">{worst_pnl}</div></div>
    </div>
    {win_metrics_block}
    <h2 class="section-title">Exit Distribution</h2>
    <div class="chart-container"><div class="chart-wrapper-pie"><canvas id="exitPieChart_{safe_symbol}"></canvas></div></div>
    <h2 class="section-title">Equity Curve</h2>
    <div class="chart-container" style="height: 300px;"><canvas id="equityChart_{safe_symbol}"></canvas></div>
    <h2 class="section-title">Monthly Returns</h2>
    <div style="overflow-x: auto;"><table class="trades-table"><thead><tr><th>Month</th><th>Trades</th><th>PnL ($)</th><th>Return (%)</th></tr></thead><tbody>{monthly_rows}</tbody></table></div>
    {additional_block}
    <h2 class="section-title">Per-Symbol PnL</h2>
    <div class="chart-container" style="height: {max(300, len(unique_symbols) * 30)}px;"><canvas id="tickerPnlChart_{safe_symbol}"></canvas></div>
    <h2 class="section-title">Trade Details</h2>
    <div style="overflow-x: auto;">{trades_table}</div>
    <p class="report-time">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
</div>{chart_js}</body></html>"""

    if return_only:
        return html

    html_dir = os.path.join(output_dir, "html")
    os.makedirs(html_dir, exist_ok=True)
    report_path = os.path.join(html_dir, f"backtest_report_{safe_symbol}_{timeframe}.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info("html_report_saved", path=report_path)
    return report_path
