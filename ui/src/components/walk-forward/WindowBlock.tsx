import React from "react";
import { WalkForwardWindow } from "../../stores/walkForwardStore";
import { cn } from "../../lib/utils";
import { Check, X, AlertTriangle } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "../ui/tooltip";

interface WindowBlockProps {
  window: WalkForwardWindow;
  paramName: string;
  isCompact?: boolean;
}

export const WindowBlock: React.FC<WindowBlockProps> = ({ window, paramName, isCompact = false }) => {
  const getStatusIcon = () => {
    if (window.oosReturnPct > 0.5) {
      return <Check className="w-3 h-3 text-success" />;
    } else if (window.oosReturnPct < -0.5) {
      return <X className="w-3 h-3 text-danger" />;
    } else {
      return <AlertTriangle className="w-3 h-3 text-warning" />;
    }
  };

  const getReturnColor = () => {
    if (window.oosReturnPct > 0.5) return "text-success";
    if (window.oosReturnPct < -0.5) return "text-danger";
    return "text-warning";
  };

  if (isCompact) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <div className="flex flex-col items-center gap-1 p-2 rounded-lg bg-bg-elevated border border-border-main hover:border-accent-main/50 transition-all cursor-pointer">
              <div className="text-xs font-medium text-text-secondary">W{window.index}</div>
              
              {/* Visual IS/OOS blocks */}
              <div className="flex items-center gap-0.5">
                <div className="w-12 h-6 bg-accent-main/20 border border-accent-main/40 rounded-l flex items-center justify-center">
                  <span className="text-[10px] font-medium text-accent-main">IS</span>
                </div>
                <div className={cn(
                  "w-6 h-6 border rounded-r flex items-center justify-center",
                  window.isPositive ? "bg-success/10 border-success/40" : "bg-danger/10 border-danger/40"
                )}>
                  <span className="text-[10px] font-medium">{window.isPositive ? "✓" : "✗"}</span>
                </div>
              </div>

              <div className="text-xs font-medium text-text-primary">
                {paramName}={window.bestParam}
              </div>
              
              <div className={cn("text-xs font-semibold", getReturnColor())}>
                {window.oosReturnPct > 0 ? "+" : ""}{window.oosReturnPct.toFixed(1)}%
              </div>

              <div className="flex items-center justify-center">
                {getStatusIcon()}
              </div>
            </div>
          </TooltipTrigger>
          <TooltipContent side="top" className="max-w-xs">
            <div className="space-y-1 text-xs">
              <div className="font-semibold border-b border-border-main pb-1">Window {window.index}</div>
              <div><strong>IS Period:</strong> {window.isStartDate} to {window.isEndDate}</div>
              <div><strong>OOS Period:</strong> {window.oosStartDate} to {window.oosEndDate}</div>
              <div><strong>Best {paramName}:</strong> {window.bestParam}</div>
              <div><strong>IS Metric:</strong> {window.isMetricValue}</div>
              <div><strong>OOS Return:</strong> {window.oosReturnPct > 0 ? "+" : ""}{window.oosReturnPct}%</div>
            </div>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  // Full view
  return (
    <div className="p-4 rounded-lg bg-bg-elevated border border-border-main space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-text-primary">Window {window.index}</h4>
        {getStatusIcon()}
      </div>

      {/* Timeline visualization */}
      <div className="flex items-center gap-1">
        <div className="flex-1 bg-accent-main/20 border border-accent-main/40 rounded px-3 py-2">
          <div className="text-[10px] font-medium text-accent-main mb-0.5">IN-SAMPLE</div>
          <div className="text-xs text-text-secondary">{window.isStartDate}</div>
          <div className="text-xs text-text-secondary">{window.isEndDate}</div>
        </div>
        <div className={cn(
          "w-24 border rounded px-2 py-2",
          window.isPositive ? "bg-success/10 border-success/40" : "bg-danger/10 border-danger/40"
        )}>
          <div className={cn(
            "text-[10px] font-medium mb-0.5",
            window.isPositive ? "text-success" : "text-danger"
          )}>
            OOS
          </div>
          <div className="text-xs text-text-secondary">{window.oosStartDate}</div>
          <div className="text-xs text-text-secondary">{window.oosEndDate}</div>
        </div>
      </div>

      {/* Results */}
      <div className="grid grid-cols-2 gap-3 text-xs">
        <div>
          <div className="text-text-secondary">Best {paramName}:</div>
          <div className="text-text-primary font-medium">{window.bestParam}</div>
        </div>
        <div>
          <div className="text-text-secondary">IS Metric:</div>
          <div className="text-text-primary font-medium">{window.isMetricValue}</div>
        </div>
        <div className="col-span-2">
          <div className="text-text-secondary">OOS Return:</div>
          <div className={cn("text-lg font-bold", getReturnColor())}>
            {window.oosReturnPct > 0 ? "+" : ""}{window.oosReturnPct}%
          </div>
        </div>
      </div>
    </div>
  );
};
