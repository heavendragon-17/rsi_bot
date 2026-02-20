// @ts-nocheck
import React from "react";
import { useBatchResultsStore } from "../../../stores/batchResultsStore";
import { cn } from "../../../lib/utils";

export const CorrelationMatrix: React.FC = () => {
  const { symbols, correlationMatrix } = useBatchResultsStore();

  const getCorrelation = (a: string, b: string) => {
      if (a === b) return 1;
      const entry = correlationMatrix.find(
          x => (x.symbolA === a && x.symbolB === b) || (x.symbolA === b && x.symbolB === a)
      );
      return entry ? entry.correlation : 0;
  };

  const getColor = (val: number) => {
      if (val === 1) return "bg-bg-elevated text-text-muted"; // Diagonal
      if (val > 0.7) return "bg-danger/20 text-danger"; // High Risk
      if (val < 0.3 && val >= 0) return "bg-success/20 text-success"; // Diversified
      if (val < 0) return "bg-success/40 text-success font-bold"; // Hedge
      return "bg-warning/20 text-warning"; // Moderate
  };

  return (
    <div className="flex flex-col h-full border border-border-main rounded-xl bg-bg-surface overflow-hidden">
        <div className="p-3 border-b border-border-main bg-bg-elevated/20">
            <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">Correlation Matrix</h3>
        </div>
        <div className="overflow-auto p-4 flex-1 flex items-center justify-center custom-scrollbar">
            <div 
                className="grid gap-1" 
                style={{ 
                    gridTemplateColumns: `auto repeat(${symbols.length}, minmax(30px, 1fr))` 
                }}
            >
                {/* Header Row */}
                <div className="h-8 w-8"></div> {/* Corner */}
                {symbols.map(sym => (
                    <div key={`h-${sym}`} className="flex items-center justify-center text-[10px] font-bold text-text-secondary -rotate-45 h-8">
                        {sym.split('/')[0]}
                    </div>
                ))}

                {/* Rows */}
                {symbols.map(rowSym => (
                    <React.Fragment key={`row-${rowSym}`}>
                        {/* Row Label */}
                        <div className="flex items-center justify-end pr-2 text-[10px] font-bold text-text-secondary">
                            {rowSym.split('/')[0]}
                        </div>
                        {/* Cells */}
                        {symbols.map(colSym => {
                            const val = getCorrelation(rowSym, colSym);
                            return (
                                <div 
                                    key={`${rowSym}-${colSym}`}
                                    className={cn(
                                        "h-8 flex items-center justify-center text-[10px] font-mono rounded-sm transition-colors hover:ring-1 hover:ring-text-primary/50 relative group",
                                        getColor(val)
                                    )}
                                    title={`${rowSym} vs ${colSym}: ${val.toFixed(2)}`}
                                >
                                    {val === 1 ? "1.0" : val.toFixed(2).replace("0.", ".")}
                                </div>
                            );
                        })}
                    </React.Fragment>
                ))}
            </div>
        </div>
    </div>
  );
};
