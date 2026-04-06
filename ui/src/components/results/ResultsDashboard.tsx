import React from "react";
import { HeaderBar } from "./HeaderBar";
import { HeroStats } from "./HeroStats";
import { MetricsGrid } from "./MetricsGrid";
import { EquityUnderwaterChart } from "./EquityUnderwaterChart";
import { ExitReasonsChart } from "./ExitReasonsChart";
import { TradesTable } from "./TradesTable";

export const ResultsDashboard: React.FC = () => {
  return (
    <div className="flex flex-col h-full bg-bg-surface overflow-y-auto overflow-x-hidden custom-scrollbar">
      {/* Sticky Header */}
      <HeaderBar />

      <div className="p-4 lg:p-6 max-w-[1800px] w-full mx-auto space-y-5 pb-20">

        {/* Row 1: Hero Stats — 4 full-width cards */}
        <HeroStats />

        {/* Row 2: Equity + Underwater charts, full width */}
        <EquityUnderwaterChart />

        {/* Row 3: Metrics Grid, full width */}
        <MetricsGrid />

        {/* Row 4: Exit Reasons (left) + Trades Table (right) */}
        <div className="grid grid-cols-12 gap-5">
          <div className="col-span-12 lg:col-span-4 min-h-[300px] border border-border-main rounded-xl bg-bg-surface p-4 shadow-sm">
            <ExitReasonsChart />
          </div>
          <div className="col-span-12 lg:col-span-8">
            <h3 className="text-xs font-semibold text-text-secondary mb-3 uppercase tracking-wider">
              Trade Journal
            </h3>
            <TradesTable />
          </div>
        </div>

      </div>
    </div>
  );
};
