// @ts-nocheck
import React, { useState } from "react";
import { useBatchResultsStore, BatchSymbolResult } from "../../../stores/batchResultsStore";
import { cn } from "../../../lib/utils";
import { ChevronDown, ChevronUp, Eye, Check } from "lucide-react";

export const SymbolPerformanceTable: React.FC = () => {
  const { symbolResults, pinnedSymbols, togglePin, selectSymbol } = useBatchResultsStore();
  const [sortField, setSortField] = useState<keyof BatchSymbolResult>("netPnLPct");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");

  const sortedData = [...symbolResults].sort((a, b) => {
      // @ts-ignore
      const aVal = a[sortField];
      // @ts-ignore
      const bVal = b[sortField];

      if (typeof aVal === "string" && typeof bVal === "string") {
          return sortDirection === "asc" ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
      }
      // @ts-ignore
      return sortDirection === "asc" ? aVal - bVal : bVal - aVal;
  });

  const handleHeaderClick = (field: keyof BatchSymbolResult) => {
      if (sortField === field) {
          setSortDirection(prev => prev === "asc" ? "desc" : "asc");
      } else {
          setSortField(field);
          setSortDirection("desc");
      }
  };

  const SortIcon = ({ field }: { field: keyof BatchSymbolResult }) => {
      if (sortField !== field) return <div className="w-3 h-3" />;
      return sortDirection === "asc" ? <ChevronUp size={12} /> : <ChevronDown size={12} />;
  };

  return (
    <div className="flex flex-col h-full border border-border-main rounded-xl bg-bg-surface overflow-hidden">
        <div className="p-3 border-b border-border-main bg-bg-elevated/20">
             <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">Symbol Performance</h3>
        </div>
        <div className="overflow-auto flex-1 custom-scrollbar">
            <table className="w-full text-left border-collapse">
                <thead className="bg-bg-elevated sticky top-0 z-10 text-[10px] font-semibold text-text-secondary uppercase tracking-wider">
                    <tr>
                        {[
                            { key: "symbol", label: "Symbol", w: "w-24 pl-4" },
                            { key: "contribution", label: "Contrib ($)", w: "w-24 text-right" },
                            { key: "netPnLPct", label: "Net PnL %", w: "w-24 text-right" },
                            { key: "winRate", label: "Win %", w: "w-20 text-right" },
                            { key: "tradeCount", label: "# Trades", w: "w-20 text-right" },
                            { key: "sharpe", label: "Sharpe", w: "w-20 text-right" },
                            { key: "maxDrawdownPct", label: "Max DD %", w: "w-24 text-right" },
                            { key: "isPinned", label: "Pin", w: "w-16 text-center" },
                            { key: "actions", label: "Action", w: "w-20 text-center pr-4" }
                        ].map(col => (
                            <th
                                key={col.key}
                                onClick={() => col.key !== "actions" && handleHeaderClick(col.key as keyof BatchSymbolResult)}
                                className={cn(
                                    "py-3 cursor-pointer hover:bg-bg-elevated/80 transition-colors select-none",
                                    col.w
                                )}
                            >
                                <div className={cn("flex items-center gap-1", col.w.includes("right") && "justify-end", col.w.includes("center") && "justify-center")}>
                                    {col.label}
                                    {col.key !== "actions" && <SortIcon field={col.key as keyof BatchSymbolResult} />}
                                </div>
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody className="text-sm font-mono text-text-primary divide-y divide-border-main/30">
                    {sortedData.map((res) => {
                        const isWin = res.netPnL >= 0;
                        const isPinned = pinnedSymbols.includes(res.symbol);

                        return (
                            <tr key={res.symbol} onClick={() => selectSymbol(res.symbol)} className="group hover:bg-bg-elevated/30 transition-colors cursor-pointer">
                                <td className="py-2.5 pl-4 font-medium">{res.symbol}</td>
                                <td className={cn("py-2.5 text-right font-medium", isWin ? "text-success" : "text-danger")}>
                                    {isWin ? "+" : ""}{Math.round(res.contribution).toLocaleString()}
                                </td>
                                <td className={cn("py-2.5 text-right font-bold", isWin ? "text-success" : "text-danger")}>
                                    {isWin ? "+" : ""}{res.netPnLPct.toFixed(1)}%
                                </td>
                                <td className="py-2.5 text-right text-text-secondary">{res.winRate.toFixed(1)}%</td>
                                <td className="py-2.5 text-right text-text-secondary">{res.tradeCount}</td>
                                <td className={cn("py-2.5 text-right", res.sharpe > 1 ? "text-success" : res.sharpe < 0 ? "text-danger" : "text-warning")}>
                                    {res.sharpe.toFixed(2)}
                                </td>
                                <td className="py-2.5 text-right text-danger">{res.maxDrawdownPct.toFixed(1)}%</td>
                                <td className="py-2.5 text-center">
                                    <button
                                        onClick={(e) => { e.stopPropagation(); togglePin(res.symbol); }}
                                        className={cn(
                                            "w-5 h-5 rounded border flex items-center justify-center transition-all mx-auto",
                                            isPinned
                                                ? "bg-accent-main border-accent-main text-white"
                                                : "border-border-main text-transparent hover:border-accent-main/50"
                                        )}
                                    >
                                        <Check size={12} />
                                    </button>
                                </td>
                                <td className="py-2.5 text-center pr-4">
                                    <button
                                        onClick={() => selectSymbol(res.symbol)}
                                        className="px-2 py-1 rounded bg-bg-elevated hover:bg-bg-secondary text-text-secondary hover:text-text-primary text-xs font-medium transition-colors flex items-center gap-1 mx-auto border border-border-main"
                                    >
                                        View <Eye size={10} />
                                    </button>
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    </div>
  );
};
