import React from "react";
import { WalkForwardWindow } from "../../stores/walkForwardStore";
import { cn } from "../../lib/utils";
import { Check, X, AlertTriangle, Ban } from "lucide-react";
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

export const WindowBlock: React.FC<WindowBlockProps> = ({
  window,
  paramName,
  isCompact = false,
}) => {
  const getStatusIcon = () => {
    if (window.status === "failed")
      return <X className="w-3 h-3 text-danger" />;
    if (window.status === "skipped")
      return <Ban className="w-3 h-3 text-text-secondary" />;

    if (window.oosReturnPct > 0.5) {
      return <Check className="w-3 h-3 text-success" />;
    } else if (window.oosReturnPct < -0.5) {
      return <X className="w-3 h-3 text-danger" />;
    } else {
      return <AlertTriangle className="w-3 h-3 text-warning" />;
    }
  };

  const getReturnColor = () => {
    if (window.status === "failed") return "text-danger";
    if (window.status === "skipped") return "text-text-secondary";
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
              <div className="text-xs font-medium text-text-secondary">
                W{window.index}
              </div>

              {/* Visual IS/OOS blocks */}
              <div className="flex items-center gap-0.5">
                <div
                  className={cn(
                    "w-12 h-6 rounded-l flex items-center justify-center border",
                    window.status === "skipped"
                      ? "bg-bg-elevated border-border-main text-text-secondary"
                      : window.status === "failed"
                      ? "bg-danger/10 border-danger/30 text-danger"
                      : "bg-accent-main/20 border-accent-main/40 text-accent-main"
                  )}
                >
                  <span className="text-[10px] font-medium">IS</span>
                </div>
                <div
                  className={cn(
                    "w-6 h-6 border rounded-r flex items-center justify-center",
                    window.status === "failed"
                      ? "bg-danger/20 border-danger/60"
                      : window.status === "skipped"
                      ? "bg-bg-elevated border-border-main"
                      : window.isPositive
                      ? "bg-success/10 border-success/40"
                      : "bg-danger/10 border-danger/40"
                  )}
                >
                  <span className="text-[10px] font-medium">
                    {window.status === "failed"
                      ? "✗"
                      : window.status === "skipped"
                      ? "-"
                      : window.isPositive
                      ? "✓"
                      : "✗"}
                  </span>
                </div>
              </div>

              <div className="text-xs font-medium text-text-primary">
                {window.status === "skipped" || window.status === "failed"
                  ? "—"
                  : `${paramName}=${window.bestParam}`}
              </div>

              <div className={cn("text-xs font-semibold", getReturnColor())}>
                {window.status === "skipped"
                  ? "Skipped"
                  : window.status === "failed"
                  ? "Failed"
                  : `${
                      window.oosReturnPct > 0 ? "+" : ""
                    }${window.oosReturnPct.toFixed(1)}%`}
              </div>

              <div className="flex items-center justify-center">
                {getStatusIcon()}
              </div>
            </div>
          </TooltipTrigger>
          <TooltipContent side="top" className="max-w-xs">
            <div className="space-y-1 text-xs">
              <div className="font-semibold border-b border-border-main pb-1 flex items-center justify-between">
                <span>Window {window.index}</span>
                {window.status === "skipped" && (
                  <span className="text-text-secondary ml-2">SKIPPED</span>
                )}
                {window.status === "failed" && (
                  <span className="text-danger ml-2">FAILED</span>
                )}
              </div>
              <div>
                <strong>IS Period:</strong> {window.isStartDate} to{" "}
                {window.isEndDate}
              </div>
              <div>
                <strong>OOS Period:</strong> {window.oosStartDate} to{" "}
                {window.oosEndDate}
              </div>
              {window.status === "success" || !window.status ? (
                <>
                  <div>
                    <strong>Best {paramName}:</strong> {window.bestParam}
                  </div>
                  <div>
                    <strong>IS Metric:</strong> {window.isMetricValue}
                  </div>
                  <div>
                    <strong>OOS Return:</strong>{" "}
                    {window.oosReturnPct > 0 ? "+" : ""}
                    {window.oosReturnPct}%
                  </div>
                </>
              ) : (
                <div
                  className={
                    window.status === "failed"
                      ? "text-danger"
                      : "text-text-secondary"
                  }
                >
                  {window.error ||
                    (window.status === "skipped"
                      ? "Insufficient data density."
                      : "Run failed execution.")}
                </div>
              )}
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
        <h4 className="text-sm font-semibold text-text-primary">
          Window {window.index}
        </h4>
        {getStatusIcon()}
      </div>

      {/* Timeline visualization */}
      <div className="flex items-center gap-1">
        <div
          className={cn(
            "flex-1 border rounded px-3 py-2",
            window.status === "skipped"
              ? "bg-bg-elevated border-border-main"
              : window.status === "failed"
              ? "bg-danger/5 border-danger/20"
              : "bg-accent-main/20 border-accent-main/40"
          )}
        >
          <div
            className={cn(
              "text-[10px] font-medium mb-0.5",
              window.status === "skipped"
                ? "text-text-secondary"
                : window.status === "failed"
                ? "text-danger"
                : "text-accent-main"
            )}
          >
            IN-SAMPLE
          </div>
          <div className="text-xs text-text-secondary">
            {window.isStartDate}
          </div>
          <div className="text-xs text-text-secondary">{window.isEndDate}</div>
        </div>
        <div
          className={cn(
            "w-24 border rounded px-2 py-2",
            window.status === "skipped"
              ? "bg-bg-elevated border-border-main"
              : window.status === "failed"
              ? "bg-danger/5 border-danger/20"
              : window.isPositive
              ? "bg-success/10 border-success/40"
              : "bg-danger/10 border-danger/40"
          )}
        >
          <div
            className={cn(
              "text-[10px] font-medium mb-0.5",
              window.status === "skipped"
                ? "text-text-secondary"
                : window.status === "failed"
                ? "text-danger"
                : window.isPositive
                ? "text-success"
                : "text-danger"
            )}
          >
            OOS
          </div>
          <div className="text-xs text-text-secondary">
            {window.oosStartDate}
          </div>
          <div className="text-xs text-text-secondary">{window.oosEndDate}</div>
        </div>
      </div>

      {/* Results */}
      {window.status === "success" || !window.status ? (
        <div className="grid grid-cols-2 gap-3 text-xs">
          <div>
            <div className="text-text-secondary">Best {paramName}:</div>
            <div className="text-text-primary font-medium">
              {window.bestParam}
            </div>
          </div>
          <div>
            <div className="text-text-secondary">IS Metric:</div>
            <div className="text-text-primary font-medium">
              {window.isMetricValue}
            </div>
          </div>
          <div className="col-span-2">
            <div className="text-text-secondary">OOS Return:</div>
            <div className={cn("text-lg font-bold", getReturnColor())}>
              {window.oosReturnPct > 0 ? "+" : ""}
              {window.oosReturnPct}%
            </div>
          </div>
        </div>
      ) : (
        <div
          className={cn(
            "p-3 rounded border text-xs",
            window.status === "failed"
              ? "bg-danger/10 border-danger/30 text-danger"
              : "bg-bg-subtle border-border-main text-text-secondary"
          )}
        >
          {window.error ||
            (window.status === "skipped"
              ? "Insufficient data density for this period. Skipped safely."
              : "Run failed execution.")}
        </div>
      )}
    </div>
  );
};
