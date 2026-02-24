import { Trade } from '../stores/resultsStore';

export const exportTradesToCSV = (trades: Trade[], strategyName: string) => {
    if (!trades.length) return;

    const headers = [
        "Trade ID",
        "Symbol",
        "Side",
        "Entry Time",
        "Exit Time",
        "Entry Price",
        "Exit Price",
        "Size",
        "PnL",
        "PnL %",
        "Fees",
        "Exit Reason"
    ];

    const rows = trades.map(t => [
        t.id,
        t.symbol,
        t.side,
        t.entryTime,
        t.exitTime,
        t.entryPrice,
        t.exitPrice,
        t.size,
        t.pnl.toFixed(2),
        t.pnlPct.toFixed(2),
        t.fees.toFixed(2),
        t.exitReason
    ]);

    const csvContent = [
        headers.join(","),
        ...rows.map(row => row.join(","))
    ].join("\n");

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `${strategyName}_backtest_results.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
};
