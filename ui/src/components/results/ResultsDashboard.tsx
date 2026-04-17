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

        <div className="p-6 max-w-[1600px] w-full mx-auto space-y-6 pb-20">
            {/* Top Section: Hero Stats */}
            <HeroStats />

            {/* Mid Section: Charts & Metrics Grid */}
            <div className="grid grid-cols-12 gap-6">
                {/* Left Col: Metrics + Exit Reasons */}
                <div className="col-span-12 lg:col-span-4 flex flex-col gap-6">
                     <MetricsGrid />
                     <div className="flex-1 min-h-[250px] border border-border-main rounded-xl bg-bg-surface p-4 shadow-sm">
                         <ExitReasonsChart />
                     </div>
                </div>

                {/* Right Col: Main Equity Chart */}
                <div className="col-span-12 lg:col-span-8">
                     <EquityUnderwaterChart />
                </div>
            </div>

            {/* Bottom Section: Trades Table */}
            <div className="h-[500px]">
                <h3 className="text-sm font-semibold text-text-secondary mb-3 uppercase tracking-wider">Trade Journal</h3>
                <TradesTable />
            </div>
        </div>
    </div>
  );
};
