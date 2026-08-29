import React from "react";
import { useBacktestStore } from "../../stores/backtestStore";
import { useResultsStore } from "../../stores/resultsStore";
import { useBatchResultsStore } from "../../stores/batchResultsStore";
import {
  LayoutDashboard,
  Settings,
  Play,
  History,
  Menu,
  Flame,
  TrendingUp,
  Wind,
  ListChecks,
} from "lucide-react";
import { cn } from "../../lib/utils";

/**
 * Mobile Bottom Navigation
 * Appears only on xs/sm breakpoints (<768px)
 * Provides quick access to main sections
 */
export const MobileNav: React.FC = () => {
  const { mode, setMode, setSidebarOpen } = useBacktestStore();
  const { hasResults } = useResultsStore();
  const { hasBatchResults } = useBatchResultsStore();

  const showDashboard = (mode === "single" && hasResults) || (mode === "batch" && hasBatchResults);

  const navItems = [
    {
      id: "dashboard",
      label: "Dashboard",
      icon: LayoutDashboard,
      onClick: () => {
        if (hasResults) setMode("single");
        else if (hasBatchResults) setMode("batch");
      },
      isActive: showDashboard,
    },
    {
      id: "optimize",
      label: "Optimize",
      icon: Flame,
      onClick: () => setMode("grid-search"),
      isActive: mode === "grid-search",
    },
    {
      id: "run",
      label: "Run",
      icon: Play,
      onClick: () => {
        setMode("single");
        setSidebarOpen(true);
      },
      isActive: mode === "single" && !hasResults,
      highlight: true,
    },
    {
      id: "history",
      label: "History",
      icon: History,
      onClick: () => setMode("history"),
      isActive: mode === "history",
    },
    {
      id: "signals",
      label: "Signals",
      icon: ListChecks,
      onClick: () => setMode("signal-review"),
      isActive: mode === "signal-review",
    },
    {
      id: "more",
      label: "More",
      icon: Menu,
      onClick: () => setSidebarOpen(true),
      isActive: false,
    },
  ];

  return (
    <nav
      className="lg:hidden fixed bottom-0 left-0 right-0 z-50 bg-bg-surface/95 backdrop-blur-md border-t border-border-main"
      style={{
        paddingBottom: "env(safe-area-inset-bottom, 0px)",
      }}
    >
      <div className="flex items-stretch justify-around h-14">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              onClick={item.onClick}
              className={cn(
                "flex-1 flex flex-col items-center justify-center gap-1 transition-colors relative min-w-[44px] min-h-[44px]",
                item.isActive
                  ? "text-accent-main"
                  : "text-text-secondary hover:text-text-primary"
              )}
            >
              {/* Active indicator */}
              {item.isActive && (
                <div className="absolute top-0 left-1/2 -translate-x-1/2 w-12 h-0.5 bg-accent-main rounded-b-full" />
              )}

              {/* Highlight for Run button */}
              {item.highlight && !item.isActive && (
                <div className="absolute inset-0 bg-accent-main/5" />
              )}

              <Icon size={20} className={cn(item.highlight && "fill-current")} />
              <span className="text-[10px] font-medium">{item.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
};
