import React from "react";
import { useBacktestStore } from "../../stores/backtestStore";
import { ChevronDown, Globe } from "lucide-react";

const TIMEZONES = [
  { value: "UTC", label: "UTC" },
  { value: "America/New_York", label: "New York (EST)" },
  { value: "Europe/London", label: "London (GMT)" },
  { value: "Asia/Tokyo", label: "Tokyo (JST)" },
  { value: "Asia/Singapore", label: "Singapore (SGT)" },
];

export const TimezoneSelector: React.FC = () => {
  const { timezone, setTimezone } = useBacktestStore();

  return (
    <div className="relative group">
      <div className="flex items-center gap-1 cursor-pointer text-text-muted hover:text-text-primary transition-colors">
        <Globe size={10} />
        <span className="text-[10px] font-medium">{timezone}</span>
        <ChevronDown size={10} />
      </div>
      
      <select
        value={timezone}
        onChange={(e) => setTimezone(e.target.value)}
        className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"
      >
        {TIMEZONES.map((tz) => (
          <option key={tz.value} value={tz.value}>
            {tz.label}
          </option>
        ))}
      </select>
    </div>
  );
};
