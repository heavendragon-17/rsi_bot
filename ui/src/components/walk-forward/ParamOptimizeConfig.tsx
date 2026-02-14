import React from "react";
import { useWalkForwardStore } from "../../stores/walkForwardStore";
import { AVAILABLE_PARAMETERS } from "../../stores/gridSearchStore";
import { Label } from "../ui/label";
import { Input } from "../ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";

export const ParamOptimizeConfig: React.FC = () => {
  const {
    paramToOptimize,
    paramMin,
    paramMax,
    paramStep,
    optimizeMetric,
    setParamToOptimize,
    setParamRange,
    setOptimizeMetric,
  } = useWalkForwardStore();

  const selectedParam = AVAILABLE_PARAMETERS.find(
    (p) => p.value === paramToOptimize
  );

  return (
    <div className="space-y-4 pl-0 lg:pl-4">
      <h3 className="text-sm font-semibold text-text-primary mb-3">
        Optimization Target
      </h3>

      <div className="space-y-2">
        <Label
          htmlFor="param"
          className="text-xs text-text-secondary min-h-[2.5rem] flex items-end pb-1"
        >
          Parameter to Optimize
        </Label>
        <Select value={paramToOptimize} onValueChange={setParamToOptimize}>
          <SelectTrigger id="param" className="h-9">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {AVAILABLE_PARAMETERS.map((param) => (
              <SelectItem key={param.value} value={param.value}>
                {param.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="space-y-2">
          <Label
            htmlFor="param-min"
            className="text-xs text-text-secondary min-h-[2.5rem] flex items-end pb-1"
          >
            Min
          </Label>
          <Input
            id="param-min"
            type="number"
            value={paramMin}
            onChange={(e) =>
              setParamRange(Number(e.target.value), paramMax, paramStep)
            }
            className="h-9 text-sm"
            step={selectedParam?.type === "float" ? 0.1 : 1}
          />
        </div>

        <div className="space-y-2">
          <Label
            htmlFor="param-max"
            className="text-xs text-text-secondary min-h-[2.5rem] flex items-end pb-1"
          >
            Max
          </Label>
          <Input
            id="param-max"
            type="number"
            value={paramMax}
            onChange={(e) =>
              setParamRange(paramMin, Number(e.target.value), paramStep)
            }
            className="h-9 text-sm"
            step={selectedParam?.type === "float" ? 0.1 : 1}
          />
        </div>

        <div className="space-y-2">
          <Label
            htmlFor="param-step"
            className="text-xs text-text-secondary min-h-[2.5rem] flex items-end pb-1"
          >
            Step
          </Label>
          <Input
            id="param-step"
            type="number"
            value={paramStep}
            onChange={(e) =>
              setParamRange(paramMin, paramMax, Number(e.target.value))
            }
            className="h-9 text-sm"
            step={selectedParam?.type === "float" ? 0.1 : 1}
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label
          htmlFor="metric"
          className="text-xs text-text-secondary min-h-[2.5rem] flex items-end pb-1"
        >
          Optimize For
        </Label>
        <Select
          value={optimizeMetric}
          onValueChange={(v: any) => setOptimizeMetric(v)}
        >
          <SelectTrigger id="metric" className="h-9">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="sharpe">Sharpe Ratio</SelectItem>
            <SelectItem value="net_pnl">Net PnL</SelectItem>
            <SelectItem value="profit_factor">Profit Factor</SelectItem>
            <SelectItem value="sortino">Sortino Ratio</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>
  );
};
