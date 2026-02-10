import React from "react";
import { useBacktestStore } from "../../stores/backtestStore";
import { DateTextInput } from "./DateTextInput";

export const AbsoluteTab: React.FC = () => {
  const { startDate, endDate, setDateRange } = useBacktestStore();

  const handleStartChange = (dateStr: string) => {
    // Only update if valuable string
    const newStart = dateStr ? new Date(dateStr) : null;
    setDateRange(newStart, endDate);
  };

  const handleEndChange = (dateStr: string) => {
     const newEnd = dateStr ? new Date(dateStr) : null;
     setDateRange(startDate, newEnd);
  };

  const formatDate = (date: Date | string | null): string => {
      if (!date) return "";
      try {
          const d = new Date(date);
          return d.toISOString().split('T')[0];
      } catch (e) {
          return "";
      }
  };

  return (
    <div className="flex gap-2 animate-in fade-in slide-in-from-top-1 duration-200">
      <DateTextInput 
        label="Start Date" 
        value={formatDate(startDate)} 
        onChange={handleStartChange} 
        shortcut="g" // Go to date
      />
      <DateTextInput 
        label="End Date" 
        value={formatDate(endDate)} 
        onChange={handleEndChange} 
      />
    </div>
  );
};
