import React from "react";
import { useHistoryStore } from "../../stores/historyStore";
import { Search } from "lucide-react";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import { Switch } from "../ui/switch";

export const HistoryFilters: React.FC = () => {
  const { filters, setFilter, runs } = useHistoryStore();

  // Extract unique strategies and symbols from runs
  const strategies = Array.from(new Set(runs.map((r) => r.strategyName))).sort();
  const symbols = Array.from(new Set(runs.map((r) => r.symbol))).sort();

  return (
    <div className="px-6 py-4 border-b border-border-main/50 bg-bg-surface/30">
      <div className="grid grid-cols-12 gap-4">
        {/* Strategy Filter */}
        <div className="col-span-3">
          <Label className="text-xs text-text-secondary mb-1.5 block">Strategy</Label>
          <Select
            value={filters.strategy || "all"}
            onValueChange={(value) => setFilter("strategy", value === "all" ? null : value)}
          >
            <SelectTrigger className="bg-bg-elevated border-border-main text-text-primary">
              <SelectValue placeholder="All Strategies" />
            </SelectTrigger>
            <SelectContent className="bg-bg-secondary border-border-main">
              <SelectItem value="all" className="text-text-primary">
                All Strategies
              </SelectItem>
              {strategies.map((strategy) => (
                <SelectItem key={strategy} value={strategy} className="text-text-primary">
                  {strategy}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Symbol Filter */}
        <div className="col-span-2">
          <Label className="text-xs text-text-secondary mb-1.5 block">Symbol</Label>
          <Select
            value={filters.symbol || "all"}
            onValueChange={(value) => setFilter("symbol", value === "all" ? null : value)}
          >
            <SelectTrigger className="bg-bg-elevated border-border-main text-text-primary">
              <SelectValue placeholder="All Symbols" />
            </SelectTrigger>
            <SelectContent className="bg-bg-secondary border-border-main">
              <SelectItem value="all" className="text-text-primary">
                All Symbols
              </SelectItem>
              {symbols.map((symbol) => (
                <SelectItem key={symbol} value={symbol} className="text-text-primary">
                  {symbol}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Date Range Filter */}
        <div className="col-span-2">
          <Label className="text-xs text-text-secondary mb-1.5 block">Date Range</Label>
          <Select
            value={filters.dateRange}
            onValueChange={(value) => setFilter("dateRange", value)}
          >
            <SelectTrigger className="bg-bg-elevated border-border-main text-text-primary">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-bg-secondary border-border-main">
              <SelectItem value="today" className="text-text-primary">
                Today
              </SelectItem>
              <SelectItem value="7days" className="text-text-primary">
                Last 7 Days
              </SelectItem>
              <SelectItem value="30days" className="text-text-primary">
                Last 30 Days
              </SelectItem>
              <SelectItem value="all" className="text-text-primary">
                All Time
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Search */}
        <div className="col-span-3">
          <Label className="text-xs text-text-secondary mb-1.5 block">Search</Label>
          <div className="relative">
            <Search
              className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted"
              size={14}
            />
            <Input
              type="text"
              placeholder="Search runs..."
              value={filters.searchQuery}
              onChange={(e) => setFilter("searchQuery", e.target.value)}
              className="pl-9 bg-bg-elevated border-border-main text-text-primary placeholder:text-text-muted"
            />
          </div>
        </div>

        {/* Toggle Filters */}
        <div className="col-span-2 flex flex-col gap-2">
          <div className="flex items-center justify-between h-[34px]">
            <Label className="text-xs text-text-secondary cursor-pointer" htmlFor="profitable">
              Profitable Only
            </Label>
            <Switch
              id="profitable"
              checked={filters.profitableOnly}
              onCheckedChange={(checked) => setFilter("profitableOnly", checked)}
            />
          </div>
          <div className="flex items-center justify-between h-[34px]">
            <Label className="text-xs text-text-secondary cursor-pointer" htmlFor="batch">
              Show Batch Runs
            </Label>
            <Switch
              id="batch"
              checked={filters.showBatchRuns}
              onCheckedChange={(checked) => setFilter("showBatchRuns", checked)}
            />
          </div>
        </div>
      </div>
    </div>
  );
};
