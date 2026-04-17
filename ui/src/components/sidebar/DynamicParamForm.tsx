import React from "react";
import { useBacktestStore } from "../../stores/backtestStore";
import { CollapsibleSection } from "../ui/CollapsibleSection";
import { ValidatedInput } from "../ui/ValidatedInput";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { Switch } from "../ui/switch";
import { RotateCcw } from "lucide-react";

export const DynamicParamForm: React.FC = () => {
  const { currentParamSchema, params, setParam, resetParams } = useBacktestStore();

  // Loading skeleton while schema loads
  if (!currentParamSchema?.properties) {
    return (
      <div className="space-y-3 p-4">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="space-y-1.5 animate-pulse">
            <div className="h-3 w-24 bg-bg-elevated rounded" />
            <div className="h-8 w-full bg-bg-elevated rounded" />
          </div>
        ))}
      </div>
    );
  }

  const schema = currentParamSchema;
  const groups = schema.ui_groups || {};
  const properties = schema.properties;

  // Group params
  const groupedParams: Record<string, [string, any][]> = {};

  for (const [key, prop] of Object.entries(properties)) {
    if (prop.ui_hidden) continue;
    const group = prop.ui_group || "__ungrouped__";
    if (!groupedParams[group]) groupedParams[group] = [];
    groupedParams[group].push([key, prop]);
  }

  // Sort groups by order
  const sortedGroupKeys = Object.keys(groups).sort(
    (a, b) => (groups[a].order || 0) - (groups[b].order || 0)
  );

  // Add ungrouped at end
  if (groupedParams["__ungrouped__"]) {
    sortedGroupKeys.push("__ungrouped__");
  }

  return (
    <>
      {sortedGroupKeys.map((groupKey) => {
        const groupMeta = groups[groupKey] || { title: "Other", order: 999 };
        const groupParams = (groupedParams[groupKey] || [])
          .sort(([, a], [, b]) => (a.ui_order || 0) - (b.ui_order || 0));

        if (groupParams.length === 0) return null;

        return (
          <CollapsibleSection
            key={groupKey}
            title={groupMeta.title}
            headerAction={
              groupKey === sortedGroupKeys[0] ? (
                <button
                  onClick={(e) => { e.stopPropagation(); resetParams(); }}
                  className="p-1 hover:bg-bg-elevated rounded text-text-muted hover:text-text-primary transition-colors"
                  title="Reset to Defaults"
                >
                  <RotateCcw size={12} />
                </button>
              ) : undefined
            }
          >
            <div className="space-y-3">
              {groupParams.map(([paramName, prop]) => (
                <ParamInput
                  key={paramName}
                  name={paramName}
                  prop={prop}
                  value={params[paramName]}
                  onChange={(v) => setParam(paramName, v)}
                />
              ))}
            </div>
          </CollapsibleSection>
        );
      })}
    </>
  );
};

// Individual param input renderer
const ParamInput: React.FC<{
  name: string;
  prop: any;
  value: unknown;
  onChange: (value: unknown) => void;
}> = ({ name, prop, value, onChange }) => {
  if (prop.type === "boolean") {
    return (
      <div className="flex items-center justify-between">
        <label className="text-xs font-medium text-text-secondary">
          {prop.title}
        </label>
        <Switch
          checked={Boolean(value)}
          onCheckedChange={onChange}
        />
      </div>
    );
  }

  if (prop.enum) {
    return (
      <div className="space-y-1.5">
        <label className="text-xs font-medium text-text-secondary">
          {prop.title}
        </label>
        <Select value={String(value)} onValueChange={onChange}>
          <SelectTrigger className="w-full bg-input/50 border-border-main">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {prop.enum.map((opt: string) => (
              <SelectItem key={opt} value={opt}>{opt}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    );
  }

  // Number / Integer input
  return (
    <ValidatedInput
      label={prop.title}
      paramKey={name}
      value={String(value ?? prop.default ?? "")}
      onChangeValue={(v) => {
        const num = prop.type === "integer" ? parseInt(v) : parseFloat(v);
        if (!isNaN(num)) onChange(num);
        else onChange(v);
      }}
      suffix={prop.ui_suffix}
    />
  );
};
