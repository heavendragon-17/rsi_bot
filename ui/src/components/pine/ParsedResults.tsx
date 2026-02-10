import React from "react";
import { usePineStore } from "../../stores/pineStore";
import { ArrowLeft, Save, AlertTriangle, XCircle, CheckCircle, Info } from "lucide-react";
import { cn } from "../../lib/utils";

export const ParsedResults: React.FC = () => {
  const { 
      parsedIndicator, 
      parameterOverrides, 
      updateParameterOverride, 
      saveIndicator,
      reset 
  } = usePineStore();

  if (!parsedIndicator) return null;

  const { name, type, version, parameters, warnings, errors } = parsedIndicator;
  const hasErrors = errors.length > 0;

  return (
    <div className="flex flex-col h-full space-y-4">
        {/* Header Summary */}
        <div className="p-4 bg-bg-surface border border-border-main rounded-xl flex items-start gap-4 shadow-sm">
            <div className={cn(
                "w-12 h-12 rounded-full flex items-center justify-center shrink-0",
                hasErrors ? "bg-danger/10 text-danger" : "bg-success/10 text-success"
            )}>
                {hasErrors ? <XCircle size={24} /> : <CheckCircle size={24} />}
            </div>
            <div>
                <h2 className="text-lg font-bold text-text-primary">{name || "Untitled"}</h2>
                <div className="flex items-center gap-3 mt-1 text-xs text-text-secondary">
                    <span className="px-2 py-0.5 bg-bg-elevated rounded border border-border-main capitalize">{type}</span>
                    <span className="px-2 py-0.5 bg-bg-elevated rounded border border-border-main font-mono">{version}</span>
                    <span>{parameters.length} Parameters</span>
                </div>
            </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 flex-1 min-h-0">
            {/* Parameters Column */}
            <div className="lg:col-span-2 flex flex-col bg-bg-surface border border-border-main rounded-xl overflow-hidden shadow-sm">
                <div className="p-3 border-b border-border-main bg-bg-elevated/20">
                    <h3 className="text-sm font-semibold text-text-primary">Extracted Parameters</h3>
                </div>
                
                <div className="overflow-y-auto p-4 flex-1 custom-scrollbar">
                    {parameters.length === 0 ? (
                        <div className="flex flex-col items-center justify-center h-full text-text-muted text-sm italic">
                            No adjustable input parameters found.
                        </div>
                    ) : (
                        <table className="w-full text-sm">
                            <thead className="text-xs text-text-secondary text-left uppercase tracking-wide border-b border-border-main/50">
                                <tr>
                                    <th className="pb-2 font-medium w-1/3">Parameter</th>
                                    <th className="pb-2 font-medium w-1/3">Default Value</th>
                                    <th className="pb-2 font-medium w-1/3">Source</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-border-main/30">
                                {parameters.map((param) => (
                                    <tr key={param.id} className="group">
                                        <td className="py-3 pr-4 font-medium text-text-primary">{param.name}</td>
                                        <td className="py-3 pr-4">
                                            {/* Input Control based on type */}
                                            {param.type === "bool" ? (
                                                <input 
                                                    type="checkbox"
                                                    checked={parameterOverrides[param.id] ?? param.defaultValue}
                                                    onChange={(e) => updateParameterOverride(param.id, e.target.checked)}
                                                    className="rounded border-border-main bg-bg-elevated text-accent-main focus:ring-accent-main"
                                                />
                                            ) : param.type === "source" ? (
                                                <select
                                                    value={parameterOverrides[param.id] ?? param.defaultValue}
                                                    onChange={(e) => updateParameterOverride(param.id, e.target.value)}
                                                    className="w-full px-2 py-1 bg-input/50 border border-border-main rounded text-xs focus:ring-1 focus:ring-accent-main"
                                                >
                                                    {["close", "open", "high", "low", "hl2", "hlc3", "ohlc4"].map(o => (
                                                        <option key={o} value={o}>{o}</option>
                                                    ))}
                                                </select>
                                            ) : (
                                                <input 
                                                    type={param.type === "int" || param.type === "float" ? "number" : "text"}
                                                    value={parameterOverrides[param.id] ?? param.defaultValue}
                                                    step={param.type === "float" ? "0.01" : "1"}
                                                    onChange={(e) => updateParameterOverride(param.id, param.type === 'int' ? parseInt(e.target.value) : param.type === 'float' ? parseFloat(e.target.value) : e.target.value)}
                                                    className="w-full px-2 py-1 bg-input/50 border border-border-main rounded text-xs focus:ring-1 focus:ring-accent-main font-mono"
                                                />
                                            )}
                                        </td>
                                        <td className="py-3 text-xs text-text-muted font-mono truncate max-w-[150px]" title={param.pineSource}>
                                            {param.pineSource}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>
            </div>

            {/* Warnings & Errors Column */}
            <div className="flex flex-col gap-4">
                {/* Warnings Panel */}
                <div className="bg-bg-surface border border-border-main rounded-xl overflow-hidden shadow-sm flex-1 flex flex-col">
                     <div className="p-3 border-b border-border-main bg-bg-elevated/20 flex justify-between items-center">
                        <h3 className="text-sm font-semibold text-text-primary">Validation</h3>
                        <span className={cn("text-xs font-bold px-2 py-0.5 rounded-full", hasErrors ? "bg-danger/20 text-danger" : warnings.length > 0 ? "bg-warning/20 text-warning" : "bg-success/20 text-success")}>
                            {hasErrors ? `${errors.length} Errors` : warnings.length > 0 ? `${warnings.length} Warnings` : "OK"}
                        </span>
                    </div>
                    <div className="p-4 overflow-y-auto custom-scrollbar flex-1 space-y-3">
                        {errors.map((err, i) => (
                            <div key={`err-${i}`} className="flex gap-2 text-xs text-danger bg-danger/5 p-2 rounded border border-danger/20">
                                <XCircle size={14} className="shrink-0 mt-0.5" />
                                <span>{err.message}</span>
                            </div>
                        ))}
                        {warnings.map((warn, i) => (
                             <div key={`warn-${i}`} className="flex gap-2 text-xs text-warning bg-warning/5 p-2 rounded border border-warning/20">
                                <AlertTriangle size={14} className="shrink-0 mt-0.5" />
                                <span>{warn.message}</span>
                            </div>
                        ))}
                        {!hasErrors && warnings.length === 0 && (
                            <div className="flex flex-col items-center justify-center h-20 text-text-muted text-xs text-center">
                                <CheckCircle className="mb-2 text-success opacity-50" size={20} />
                                No issues detected.
                            </div>
                        )}
                    </div>
                </div>

                {/* Actions */}
                <div className="bg-bg-surface border border-border-main rounded-xl p-4 shadow-sm space-y-3">
                     <button 
                        onClick={() => reset()}
                        className="w-full px-4 py-2 border border-border-main hover:bg-bg-elevated text-text-secondary text-sm font-medium rounded-lg flex items-center justify-center gap-2 transition-colors"
                     >
                        <ArrowLeft size={16} /> Edit Code
                    </button>
                    <button 
                        onClick={saveIndicator}
                        disabled={hasErrors}
                        className="w-full px-4 py-2 bg-accent-main hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg flex items-center justify-center gap-2 transition-colors shadow-lg shadow-accent-main/20"
                    >
                        <Save size={16} /> Save Indicator
                    </button>
                </div>
            </div>
        </div>
    </div>
  );
};
