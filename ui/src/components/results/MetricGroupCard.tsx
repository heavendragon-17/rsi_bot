import React from "react";
import { cn } from "../../lib/utils";

interface MetricRow {
  label: string;
  value: string;
  subValue?: string;
  highlight?: "success" | "danger" | "neutral";
}

interface MetricGroupCardProps {
  title: string;
  icon: React.ReactNode;
  metrics: MetricRow[];
}

export const MetricGroupCard: React.FC<MetricGroupCardProps> = ({
  title,
  icon,
  metrics,
}) => (
  <div className="border border-border-main rounded-xl bg-bg-elevated/40 shadow-sm overflow-hidden hover:border-accent-main/30 transition-colors">
    {/* Header */}
    <div className="flex items-center gap-2 px-4 py-3 border-b border-border-main/40 bg-bg-elevated/20">
      <div className="text-text-muted/60">{icon}</div>
      <h4 className="text-[11px] font-semibold uppercase tracking-widest text-text-muted">
        {title}
      </h4>
    </div>

    {/* Metric rows */}
    <div className="divide-y divide-border-main/20">
      {metrics.map((m) => (
        <div
          key={m.label}
          className="flex items-baseline justify-between px-4 py-2.5"
        >
          <span className="text-xs text-text-secondary">{m.label}</span>
          <div className="flex items-baseline gap-1">
            <span
              className={cn(
                "text-sm font-bold font-mono",
                m.highlight === "success" && "text-success",
                m.highlight === "danger" && "text-danger"
              )}
            >
              {m.value}
            </span>
            {m.subValue && (
              <span className="text-[10px] text-text-muted">{m.subValue}</span>
            )}
          </div>
        </div>
      ))}
    </div>
  </div>
);
