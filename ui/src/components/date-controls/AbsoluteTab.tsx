// @ts-nocheck
import React from "react";
import { useBacktestStore } from "../../stores/backtestStore";
import { DateTextInput } from "./DateTextInput";

export const AbsoluteTab: React.FC = () => {
  const { startDate, setStartDate, endDate, setEndDate } = useBacktestStore();

  return (
    <div className="flex gap-2 animate-in fade-in slide-in-from-top-1 duration-200">
      <DateTextInput 
        label="Start Date" 
        value={startDate} 
        onChange={setStartDate} 
        shortcut="g" // Go to date
      />
      <DateTextInput 
        label="End Date" 
        value={endDate} 
        onChange={setEndDate} 
      />
    </div>
  );
};
