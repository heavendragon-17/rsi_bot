import React from "react";
import { Label } from "../ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import { GridMetric } from "../../stores/gridSearchStore";

interface MetricSelectorProps {
  value: GridMetric;
  onChange: (value: GridMetric) => void;
  disabled?: boolean;
}

export const MetricSelector: React.FC<MetricSelectorProps> = ({
  value,
  onChange,
  disabled = false,
}) => {
  return (
    <div className="space-y-2">
      <Label className="text-sm font-medium text-text-primary">Optimize For</Label>
      <Select value={value} onValueChange={(v: GridMetric) => onChange(v)} disabled={disabled}>
        <SelectTrigger className="bg-bg-secondary border-border-main">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="net_pnl">Net PnL</SelectItem>
          <SelectItem value="sharpe">Sharpe Ratio</SelectItem>
          <SelectItem value="profit_factor">Profit Factor</SelectItem>
          <SelectItem value="win_rate">Win Rate</SelectItem>
          <SelectItem value="max_dd">Max Drawdown (minimize)</SelectItem>
          <SelectItem value="calmar">Calmar Ratio</SelectItem>
          <SelectItem value="sortino">Sortino Ratio</SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
};
