import React, { useEffect, useState } from "react";
import { useBacktestStore } from "../../stores/backtestStore";
import { DateTextInput } from "./DateTextInput";
import { checkDataStatus } from "../../api/data";

export const AbsoluteTab: React.FC = () => {
  const { symbol, timeframe, startDate, setStartDate, endDate, setEndDate } =
    useBacktestStore();
  const [dataRange, setDataRange] = useState<{
    start: string;
    end: string;
  } | null>(null);

  useEffect(() => {
    const fetchRange = async () => {
      try {
        const res = await checkDataStatus(symbol, timeframe);
        if (res.available && res.date_range) {
          const s = res.date_range.start.split("T")[0];
          const e = res.date_range.end.split("T")[0];
          setDataRange({ start: s, end: e });

          // Auto-adjust if current dates are out of bounds or just default
          const currentStore = useBacktestStore.getState();
          if (
            currentStore.startDate === "2024-01-01" &&
            currentStore.endDate === "2024-12-31"
          ) {
            currentStore.setStartDate(s);
            currentStore.setEndDate(e);
          }
        } else {
          setDataRange(null);
        }
      } catch (err) {
        setDataRange(null);
      }
    };
    fetchRange();
  }, [symbol, timeframe]);

  return (
    <div className="flex flex-col gap-2 animate-in fade-in slide-in-from-top-1 duration-200">
      <div className="flex gap-2 w-full">
        <DateTextInput
          label="Start Date"
          value={startDate}
          onChange={setStartDate}
          shortcut="g" // Go to date
        />
        <DateTextInput label="End Date" value={endDate} onChange={setEndDate} />
      </div>
      {dataRange && (
        <div className="text-[10px] text-accent-main/80 text-right px-1 mt-[-2px]">
          Available: {dataRange.start} to {dataRange.end}
        </div>
      )}
    </div>
  );
};
