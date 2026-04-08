import React from "react";
import { HeaderBar } from "./HeaderBar";
import { NetProfitHero } from "./NetProfitHero";
import { MetricGroupCards } from "./MetricGroupCards";
import { EquityUnderwaterChart } from "./EquityUnderwaterChart";
import { ExitReasonsBar } from "./ExitReasonsBar";
import { TradesTable } from "./TradesTable";

export const ResultsDashboard: React.FC = () => {
  return (
    <div className="flex flex-col h-full bg-bg-surface">
      {/* Header — outside scroll context so scrollbar doesn't overlap */}
      <HeaderBar />

      <div className="flex-1 overflow-y-auto overflow-x-hidden custom-scrollbar">
        <div className="p-4 lg:p-5 max-w-[1800px] w-full mx-auto space-y-4 pb-20">

          {/* 1. Net Profit Hero */}
          <NetProfitHero />

          {/* 2. Three Metric Group Cards */}
          <MetricGroupCards />

          {/* 3. Equity + Underwater charts */}
          <EquityUnderwaterChart />

          {/* 4. Exit Reasons Bar */}
          <ExitReasonsBar />

          {/* 5. Trade Journal */}
          <div>
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
