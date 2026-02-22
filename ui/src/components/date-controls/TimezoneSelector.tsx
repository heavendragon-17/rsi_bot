// @ts-nocheck
import React from "react";
import { useBacktestStore } from "../../stores/backtestStore";
import { Globe } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger } from "../ui/select";

const TIMEZONES = [
  { value: "UTC", label: "UTC" },
  { value: "America/New_York", label: "New York (EST)" },
  { value: "Europe/London", label: "London (GMT)" },
  { value: "Asia/Tokyo", label: "Tokyo (JST)" },
  { value: "Asia/Singapore", label: "Singapore (SGT)" },
];

export const TimezoneSelector: React.FC = () => {
  const { timezone, setTimezone } = useBacktestStore();

  const selectedLabel =
    TIMEZONES.find((tz) => tz.value === timezone)?.label || timezone;

  return (
    <Select value={timezone} onValueChange={setTimezone}>
      <SelectTrigger className="h-6 py-0 px-2 border-none bg-transparent shadow-none hover:bg-bg-elevated text-text-muted hover:text-text-primary gap-1.5 transition-colors focus:ring-0 focus-visible:ring-0 data-[state=open]:bg-bg-elevated [&>svg]:size-3 w-auto mx-0 my-0">
        <div className="flex items-center gap-1.5">
          <Globe className="size-3.5 opacity-75" />
          <span className="text-xs font-medium">{selectedLabel}</span>
        </div>
      </SelectTrigger>
      <SelectContent
        align="end"
        className="min-w-[140px] border-border-main bg-bg-surface backdrop-blur-xl shadow-xl"
      >
        {TIMEZONES.map((tz) => (
          <SelectItem
            key={tz.value}
            value={tz.value}
            className="text-xs cursor-pointer text-text-secondary hover:text-text-primary"
          >
            {tz.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
};
